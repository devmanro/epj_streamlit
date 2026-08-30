"""
infrastructure/database/db_importer.py
────────────────────────────────────────
Bridges the old Excel/CSV manifest files → SQLite database.

Usage (from any module or from main.py):
    from infrastructure.database.db_importer import import_manifest_to_db, load_all_manifest_lines

Public functions:
    import_manifest_to_db(df, vessel_name, escale, imo)   → (inserted, skipped, errors)
    load_all_manifest_lines()                              → pd.DataFrame  (all rows from DB)
    load_manifest_for_vessel(vessel_name)                  → pd.DataFrame  (rows for one vessel)
    list_vessels()                                         → list[dict]
    delete_vessel(vessel_id)                               → None
"""

import pandas as pd
from datetime import datetime, timezone

from infrastructure.database.session import get_session, init_db
from infrastructure.database.models import Vessel, ManifestLine

# Ensure tables exist on first import
init_db()


# ─────────────────────────────────────────────────────────────────────────────
#  COLUMN MAP  (Excel column name -> ManifestLine field)
#  Add or rename entries here if your Excel headers change.
# ─────────────────────────────────────────────────────────────────────────────
_COL_MAP = {
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


def _safe_float(val) -> float:
    try:
        return float(val) if pd.notna(val) else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val):
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "nat") else None


def _safe_date(val):
    if pd.isna(val):
        return None
    try:
        dt = pd.to_datetime(val)
        if dt is pd.NaT:
            return None
        return dt.to_pydatetime().replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN IMPORT FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def import_manifest_to_db(
    df: pd.DataFrame,
    vessel_name: str,
    escale=None,
    imo=None,
    arrival_date=None,
):
    """
    Import a manifest DataFrame into SQLite.

    Parameters
    ----------
    df           : pandas DataFrame with manifest rows (from Excel / CSV)
    vessel_name  : name of the vessel  (e.g. "MING ZHOU 8")
    escale       : escale/stopover reference (optional)
    imo          : IMO number (optional)
    arrival_date : arrival datetime (optional, defaults to now)

    Returns
    -------
    (inserted, skipped, errors)
        inserted  - number of new rows added
        skipped   - number of duplicate rows skipped (vessel+BL already exists)
        errors    - list of error strings for rows that failed
    """
    inserted, skipped = 0, 0
    errors = []

    # Normalise column names
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    with get_session() as session:
        # 1. Find or create the Vessel record
        vessel = (
            session.query(Vessel)
            .filter_by(name=vessel_name.strip())
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
            session.flush()  # get vessel.id

        # 2. Import each row
        for idx, row in df.iterrows():
            try:
                fields = {}
                for excel_col, orm_field in _COL_MAP.items():
                    if excel_col not in df.columns:
                        continue
                    val = row[excel_col]
                    if orm_field in ("manifested_qty", "manifested_tonnage",
                                     "reste_tp", "surface"):
                        fields[orm_field] = _safe_float(val)
                    elif orm_field in ("manifested_date", "date_enlevement"):
                        fields[orm_field] = _safe_date(val)
                    else:
                        fields[orm_field] = _safe_str(val)

                bl_code = fields.get("bl_code")
                if not bl_code:
                    errors.append(f"Row {idx}: missing B/L code — skipped.")
                    continue

                chassis = fields.get("chassis_serial")
                article = fields.get("article")
                
                # Skip exact duplicates (same vessel + BL + chassis + article)
                exists = (
                    session.query(ManifestLine)
                    .filter_by(vessel_id=vessel.id, bl_code=bl_code, 
                               chassis_serial=chassis, article=article)
                    .first()
                )
                if exists:
                    skipped += 1
                    continue

                line = ManifestLine(vessel_id=vessel.id, **fields)
                session.add(line)
                inserted += 1

            except Exception as exc:
                errors.append(f"Row {idx}: {exc}")

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
            .all()
        )
        return _rows_to_df(rows)


def list_vessels():
    """Return a list of all vessels stored in the DB."""
    with get_session() as session:
        vessels = session.query(Vessel).order_by(Vessel.arrival_date.desc()).all()
        return [
            {
                "id":           v.id,
                "name":         v.name,
                "escale":       v.escale,
                "imo":          v.imo,
                "arrival_date": v.arrival_date,
                "line_count":   len(v.manifest_lines),
            }
            for v in vessels
        ]


def delete_vessel(vessel_id: int):
    """Delete a vessel and all its manifest lines (cascade)."""
    with get_session() as session:
        vessel = session.query(Vessel).filter_by(id=vessel_id).first()
        if vessel:
            session.delete(vessel)


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL: ORM rows -> DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def _rows_to_df(rows) -> pd.DataFrame:
    """Convert a list of (ManifestLine, Vessel) tuples to a DataFrame."""
    if not rows:
        return pd.DataFrame()

    records = []
    for line, vessel in rows:
        records.append({
            # Vessel info
            "NAVIRE":          vessel.name,
            "ESCALE":          vessel.escale,
            "IMO_NAVIRE":      vessel.imo,
            "ARRIVAL_DATE":    vessel.arrival_date,
            # ManifestLine fields (mapped back to app column names)
            "B/L":             line.bl_code,
            "ARTICLE":         line.article,
            "CLIENT":          line.client,
            "DESIGNATION":     line.designation,
            "PRODUIT":         line.produit,
            "MODELE":          line.modele,
            "TYPE":            line.type_,
            "CARGO_TYPE":      line.cargo_type,
            "CHASSIS/SERIAL":  line.chassis_serial,
            "QUANTITE":        line.manifested_qty,
            "TONAGE":          line.manifested_tonnage,
            "RESTE T/P":       line.reste_tp,
            "SURFACE":         line.surface,
            "SITUATION":       line.situation,
            "OBSERVATION":     line.observation,
            "POSITION":        line.position,
            "TRANSIT":         line.transit,
            "CLES":            line.cles,
            "DAEMO BREAKER (DRB) TOP BOX TYPE": line.daemo_breaker_type,
            "DATE":            line.manifested_date,
            "DATE ENLEV":      line.date_enlevement,
            # Operational counters
            "landed_qty":      line.landed_qty,
            "received_qty":    line.received_qty,
            # DB primary key (useful for updates)
            "_db_id":          line.id,
        })

    return pd.DataFrame(records)
