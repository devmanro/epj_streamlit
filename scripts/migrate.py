import os
import sys
import pandas as pd
import math

# Add project root to python path so imports work correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from infrastructure.database.session import get_session, init_db
from infrastructure.database.models import Vessel, ManifestLine

def safe_str(val) -> str:
    if pd.isna(val) or val == "nan": return None
    v_str = str(val).strip()
    return v_str if v_str else None

def safe_float(val) -> float:
    if pd.isna(val): return 0.0
    try:
        f = float(val)
        return 0.0 if math.isnan(f) else f
    except (ValueError, TypeError):
        return 0.0

def safe_date(val):
    """Parse a date value from Excel, tolerating various formats."""
    try:
        if pd.isna(val): return None
    except (TypeError, ValueError):
        pass
    try:
        return pd.to_datetime(val, dayfirst=True).to_pydatetime()
    except Exception:
        return None

def find_column(df_cols, possible_names):
    for name in possible_names:
        if name in df_cols: return name
    return None

def run_migration(excel_path: str):
    print(f"Initializing database and migrating {excel_path}...")
    init_db()

    with get_session() as session:
        df = pd.read_excel(excel_path)
        cols = df.columns.tolist()

        # ── Column resolution ────────────────────────────────────────────────
        # Vessel-level
        col_navire  = find_column(cols, ["NAVIRE", "VESSEL", "SHIP"]) or cols[0]
        col_escale  = find_column(cols, ["ESCALE"])
        col_imo     = find_column(cols, ["IMO_NAVIRE", "IMO"])

        # ManifestLine identification
        col_bl          = find_column(cols, ["B/L", "BL", "BL_CODE", "N° BL"])
        col_article     = find_column(cols, ["ARTICLE"])
        col_client      = find_column(cols, ["CLIENT"])
        col_designation = find_column(cols, ["DESIGNATION", "MARCHANDISE", "produits"])

        # Classification
        col_produit       = find_column(cols, ["PRODUIT"])
        col_modele        = find_column(cols, ["MODELE"])
        col_chassis       = find_column(cols, ["CHASSIS/SERIAL", "CHASSIS", "SERIAL"])
        col_type          = find_column(cols, ["TYPE"])
        col_cargo_type    = find_column(cols, ["CARGO_TYPE"])

        # Quantities
        col_qty           = find_column(cols, ["QUANTITE", "QTY", "nombre colis"])
        col_tonnage       = find_column(cols, ["TONAGE", "TONNAGE", "Poids brute"])
        col_reste_tp      = find_column(cols, ["RESTE T/P", "RESTE"])
        col_surface       = find_column(cols, ["SURFACE"])

        # Operational
        col_situation     = find_column(cols, ["SITUATION"])
        col_observation   = find_column(cols, ["OBSERVATION"])
        col_position      = find_column(cols, ["POSITION"])
        col_transit       = find_column(cols, ["TRANSIT"])
        col_cles          = find_column(cols, ["CLES"])
        col_daemo         = find_column(cols, ["DAEMO BREAKER (DRB) TOP BOX TYPE", "DAEMO BREAKER"])

        # Dates
        col_date          = find_column(cols, ["DATE"])
        col_date_enlev    = find_column(cols, ["DATE ENLEV", "DATE_ENLEV"])

        # ── 1. Map Vessels — dedup by (NAVIRE, ESCALE) pair (Idempotent) ────
        vessel_map = {}
        for _, row in df.iterrows():
            name_str   = safe_str(row.get(col_navire))
            escale_str = safe_str(row.get(col_escale)) if col_escale else None
            imo_str    = safe_str(row.get(col_imo))    if col_imo    else None

            if not name_str:
                continue

            key = (name_str, escale_str)
            if key in vessel_map:
                continue

            vessel = session.query(Vessel).filter_by(
                name=name_str, escale=escale_str
            ).first()

            if not vessel:
                vessel = Vessel(
                    name=name_str,
                    escale=escale_str,
                    imo=imo_str,
                )
                session.add(vessel)
                session.flush()

            vessel_map[key] = vessel.id

        # ── 2. Map Manifest Lines (Idempotent) ───────────────────────────────
        for _, row in df.iterrows():
            name_str   = safe_str(row.get(col_navire))
            escale_str = safe_str(row.get(col_escale)) if col_escale else None
            if not name_str:
                continue

            vessel_id = vessel_map.get((name_str, escale_str))
            if vessel_id is None:
                continue

            bl_code = safe_str(row.get(col_bl)) if col_bl else None
            if not bl_code:
                continue

            existing = session.query(ManifestLine).filter_by(
                vessel_id=vessel_id, bl_code=bl_code
            ).first()

            if not existing:
                line = ManifestLine(
                    vessel_id         = vessel_id,
                    bl_code           = bl_code,
                    article           = safe_str(row.get(col_article))    if col_article    else None,
                    client            = safe_str(row.get(col_client))     if col_client     else None,
                    designation       = safe_str(row.get(col_designation))if col_designation else None,
                    produit           = safe_str(row.get(col_produit))    if col_produit    else None,
                    modele            = safe_str(row.get(col_modele))     if col_modele     else None,
                    type_             = safe_str(row.get(col_type))       if col_type       else None,
                    cargo_type        = safe_str(row.get(col_cargo_type)) if col_cargo_type else None,
                    chassis_serial    = safe_str(row.get(col_chassis))    if col_chassis    else None,
                    manifested_qty    = safe_float(row.get(col_qty))      if col_qty        else 0.0,
                    manifested_tonnage= safe_float(row.get(col_tonnage))  if col_tonnage    else 0.0,
                    reste_tp          = safe_float(row.get(col_reste_tp)) if col_reste_tp   else 0.0,
                    surface           = safe_float(row.get(col_surface))  if col_surface    else 0.0,
                    situation         = safe_str(row.get(col_situation))  if col_situation  else None,
                    observation       = safe_str(row.get(col_observation))if col_observation else None,
                    position          = safe_str(row.get(col_position))   if col_position   else None,
                    transit           = safe_str(row.get(col_transit))    if col_transit    else None,
                    cles              = safe_str(row.get(col_cles))       if col_cles       else None,
                    daemo_breaker_type= safe_str(row.get(col_daemo))      if col_daemo      else None,
                    manifested_date   = safe_date(row.get(col_date))      if col_date       else None,
                    date_enlevement   = safe_date(row.get(col_date_enlev))if col_date_enlev else None,
                )
                session.add(line)

        print("Migration complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate Excel manifest to SQLite")
    parser.add_argument("file", help="Path to the Excel file to migrate")
    args = parser.parse_args()

    if os.path.exists(args.file):
        run_migration(args.file)
    else:
        print(f"Error: File {args.file} not found.")
