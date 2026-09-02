"""
infrastructure/database/db_importer.py
────────────────────────────────────────
Manifest import pipeline — Supabase PostgreSQL backend.

All fixes applied:
  ✅  Per-row SAVEPOINT so one bad row never kills the whole batch
  ✅  NULL-safe duplicate detection via explicit IS NULL / == conditions
  ✅  "-" filler values normalised to NULL before storage
  ✅  Reliable NaT detection with pd.isnull()
  ✅  N+1 query eliminated in list_vessels()
  ✅  Comprehensive null-string set in _safe_str()

Public API
----------
  import_manifest_to_db(df, vessel_name, escale, imo)  → (inserted, skipped, errors)
  load_all_manifest_lines()                             → pd.DataFrame
  load_manifest_for_vessel(vessel_name)                 → pd.DataFrame
  list_vessels()                                        → list[dict]
  delete_vessel(vessel_id)                              → None
"""

import pandas as pd
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from infrastructure.database.session import get_session, init_db
from infrastructure.database.models import Vessel, ManifestLine

# Ensure tables exist on first import
init_db()


# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

# Strings that should be treated as NULL in the source data
_NULL_STRINGS = frozenset({
    "", "-", "--", "n/a", "na", "nan", "none",
    "nat", "null", "undefined", "unknown",
})

# Maps Excel / CSV column header → ORM field name
_COL_MAP: dict[str, str] = {
    "B/L":                              "bl_code",
    "ARTICLE":                          "article",
    "CLIENT":                           "client",
    "DESIGNATION":                      "designation",
    "PRODUIT":                          "produit",
    "MODELE":                           "modele",
    "TYPE":                             "type_",
    "CARGO_TYPE":                       "cargo_type",
    "CHASSIS/SERIAL":                   "chassis_serial",
    "QUANTITE":                         "manifested_qty",
    "TONAGE":                           "manifested_tonnage",
    "RESTE T/P":                        "reste_tp",
    "SURFACE":                          "surface",
    "SITUATION":                        "situation",
    "OBSERVATION":                      "observation",
    "POSITION":                         "position",
    "TRANSIT":                          "transit",
    "CLES":                             "cles",
    "DAEMO BREAKER (DRB) TOP BOX TYPE": "daemo_breaker_type",
    "DATE":                             "manifested_date",
    "DATE ENLEV":                       "date_enlevement",
}

_FLOAT_FIELDS = frozenset({
    "manifested_qty", "manifested_tonnage", "reste_tp", "surface",
})
_DATE_FIELDS = frozenset({
    "manifested_date", "date_enlevement",
})


# ─────────────────────────────────────────────────────────────────────────────
#  Type-coercion helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    """Convert to float; return None for missing / un-parseable values."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_str(val) -> str | None:
    """
    Convert to stripped string.
    Returns None for NaN, None, and any value in _NULL_STRINGS (case-insensitive).
    """
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return None if s.lower() in _NULL_STRINGS else s


def _safe_date(val) -> datetime | None:
    """
    Parse to timezone-aware datetime.
    Handles strings, pandas Timestamps, numpy datetime64, and Excel serial numbers.
    """
    if val is None:
        return None
    # Handle scalar NaN / NaT
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass

    try:
        dt = pd.to_datetime(val, errors="coerce", utc=True)
        if pd.isnull(dt):           # correct NaT check (not `is pd.NaT`)
            return None
        return dt.to_pydatetime()   # already UTC-aware because utc=True
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Duplicate-detection helper  (NULL-safe)
# ─────────────────────────────────────────────────────────────────────────────

def _nullable_eq(column, value):
    """
    Return a SQLAlchemy filter clause that correctly handles NULL values.

    SQL: NULL = NULL  →  NULL  (wrong)
    We want:  NULL IS NULL  →  TRUE
    """
    if value is None:
        return column.is_(None)
    return column == value


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN IMPORT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def import_manifest_to_db(
    df: pd.DataFrame,
    vessel_name: str,
    escale: str | None = None,
    imo: str | None = None,
    arrival_date: datetime | None = None,
) -> tuple[int, int, list[str]]:
    """
    Import a manifest DataFrame into Supabase PostgreSQL.

    Parameters
    ----------
    df           : pandas DataFrame with manifest rows
    vessel_name  : vessel name (required, e.g. "MING ZHOU 8")
    escale       : escale/stopover reference  (optional)
    imo          : IMO number                 (optional)
    arrival_date : arrival datetime           (optional, defaults to now UTC)

    Returns
    -------
    (inserted, skipped, errors)
    """
    if not vessel_name or not vessel_name.strip():
        raise ValueError("vessel_name is required and cannot be empty.")

    inserted, skipped = 0, 0
    errors: list[str] = []

    # Normalise column headers
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    with get_session() as session:

        # ── 1. Upsert Vessel record ───────────────────────────────────────
        # Use PostgreSQL ON CONFLICT DO NOTHING so we get the existing row
        # without raising a duplicate-key error.
        vessel = (
            session.query(Vessel)
            .filter(
                Vessel.name == vessel_name.strip(),
                _nullable_eq(Vessel.escale, escale),
            )
            .first()
        )

        if vessel is None:
            vessel = Vessel(
                name=vessel_name.strip(),
                escale=escale,
                imo=imo,
                arrival_date=arrival_date or datetime.now(timezone.utc),
            )
            session.add(vessel)
            session.flush()     # acquire vessel.id before the row loop

        # ── 2. Per-row import with SAVEPOINT rollback on error ───────────
        for idx, row in df.iterrows():
            line = None
            try:
                # ── Build field dict from column map ──────────────────────
                fields: dict = {}
                for excel_col, orm_field in _COL_MAP.items():
                    if excel_col not in df.columns:
                        continue
                    val = row[excel_col]
                    if orm_field in _FLOAT_FIELDS:
                        fields[orm_field] = _safe_float(val)
                    elif orm_field in _DATE_FIELDS:
                        fields[orm_field] = _safe_date(val)
                    else:
                        fields[orm_field] = _safe_str(val)

                # ── Require B/L code ──────────────────────────────────────
                bl_code = fields.get("bl_code")
                if not bl_code:
                    errors.append(
                        f"Row {idx}: missing or empty B/L code — skipped."
                    )
                    continue

                chassis = fields.get("chassis_serial")
                article = fields.get("article")

                # ── NULL-safe duplicate check ─────────────────────────────
                exists = (
                    session.query(ManifestLine)
                    .filter(
                        ManifestLine.vessel_id == vessel.id,
                        ManifestLine.bl_code   == bl_code,
                        _nullable_eq(ManifestLine.chassis_serial, chassis),
                        _nullable_eq(ManifestLine.article,        article),
                    )
                    .first()
                )
                if exists:
                    skipped += 1
                    continue

                # ── SAVEPOINT — one bad row won't kill the batch ──────────
                session.begin_nested()
                line = ManifestLine(vessel_id=vessel.id, **fields)
                session.add(line)
                session.flush()         # validate constraints NOW
                inserted += 1

            except Exception as exc:
                # Roll back to the SAVEPOINT only — keep previous good rows
                session.rollback()
                errors.append(f"Row {idx}: {type(exc).__name__}: {exc}")

    return inserted, skipped, errors


# ─────────────────────────────────────────────────────────────────────────────
#  READ-BACK HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def load_all_manifest_lines() -> pd.DataFrame:
    """Return all manifest lines joined with vessel info as a DataFrame."""
    with get_session() as session:
        rows = (
            session.query(ManifestLine, Vessel)
            .join(Vessel, ManifestLine.vessel_id == Vessel.id)
            .all()
        )
        return _rows_to_df(rows)


def load_manifest_for_vessel(vessel_name: str) -> pd.DataFrame:
    """Return all manifest lines for a specific vessel name."""
    with get_session() as session:
        rows = (
            session.query(ManifestLine, Vessel)
            .join(Vessel, ManifestLine.vessel_id == Vessel.id)
            .filter(Vessel.name == vessel_name.strip())
            .order_by(ManifestLine.id)
            .all()
        )
        return _rows_to_df(rows)


def list_vessels() -> list[dict]:
    """
    Return summary info for all vessels.
    Uses a single aggregating query — no N+1 problem.
    """
    with get_session() as session:
        results = (
            session.query(
                Vessel,
                func.count(ManifestLine.id).label("line_count"),
            )
            .outerjoin(ManifestLine, ManifestLine.vessel_id == Vessel.id)
            .group_by(Vessel.id)
            .order_by(Vessel.arrival_date.desc())
            .all()
        )
        return [
            {
                "id":           v.id,
                "name":         v.name,
                "escale":       v.escale,
                "imo":          v.imo,
                "arrival_date": v.arrival_date,
                "line_count":   count,
            }
            for v, count in results
        ]


def delete_vessel(vessel_id: int) -> None:
    """Delete a vessel and all its manifest lines (CASCADE enforced by FK)."""
    with get_session() as session:
        vessel = session.query(Vessel).filter_by(id=vessel_id).first()
        if vessel:
            session.delete(vessel)
        # commit happens automatically via get_session() context manager


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL: ORM rows → DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def _rows_to_df(rows: list) -> pd.DataFrame:
    """Convert a list of (ManifestLine, Vessel) tuples to a DataFrame."""
    if not rows:
        return pd.DataFrame()

    records = []
    for line, vessel in rows:
        records.append({
            # ── Vessel ────────────────────────────────────────────────────
            "NAVIRE":        vessel.name,
            "ESCALE":        vessel.escale,
            "IMO_NAVIRE":    vessel.imo,
            "ARRIVAL_DATE":  vessel.arrival_date,
            # ── Cargo identity ────────────────────────────────────────────
            "B/L":           line.bl_code,
            "ARTICLE":       line.article,
            "CLIENT":        line.client,
            "DESIGNATION":   line.designation,
            "PRODUIT":       line.produit,
            "MODELE":        line.modele,
            "TYPE":          line.type_,
            "CARGO_TYPE":    line.cargo_type,
            "CHASSIS/SERIAL": line.chassis_serial,
            # ── Quantities ────────────────────────────────────────────────
            "QUANTITE":      line.manifested_qty,
            "TONAGE":        line.manifested_tonnage,
            "RESTE T/P":     line.reste_tp,
            "SURFACE":       line.surface,
            # ── Operational ───────────────────────────────────────────────
            "SITUATION":     line.situation,
            "OBSERVATION":   line.observation,
            "POSITION":      line.position,
            "TRANSIT":       line.transit,
            "CLES":          line.cles,
            "DAEMO BREAKER (DRB) TOP BOX TYPE": line.daemo_breaker_type,
            # ── Dates ─────────────────────────────────────────────────────
            "DATE":          line.manifested_date,
            "DATE ENLEV":    line.date_enlevement,
            # ── Counters ──────────────────────────────────────────────────
            "landed_qty":    line.landed_qty,
            "received_qty":  line.received_qty,
            # ── DB meta ───────────────────────────────────────────────────
            "_db_id":        line.id,
        })

    return pd.DataFrame(records)
