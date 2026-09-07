import streamlit as st
import re
import os
import unicodedata
import pandas as pd
from pyarrow import null
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from pathlib import Path
from openpyxl.formatting.rule import FormulaRule

from openpyxl.styles import  PatternFill
from openpyxl.utils import get_column_letter

from assets.constants.constants import (
    COL_CLIENT,
    COL_QUANTITE,
    COL_TONAGE,
    COL_BL,
    DB_PATH, 
    COLUMNS,
    # add COL_VALUES here if you have such a column name
    COL_TYPE,
    COL_PRODUIT,
    COMMODITY_TYPES,
    GOODS__TYPES, 
    UNITS_TYPES,
    PACKAGES_TYPES,
    KEYWORD_RULES,
    UNIT_CARGO_TYPES,
    PACKAGE_CARGO_TYPES,
    COL_DESIGNATION,
    numeric_cols,
    date_cols,
    category_cols,
    text_cols,
    LIST_OF_PATHS
)


import httpx
import asyncio

BASE = "https://devmanro-my-fastapi-app.hf.space"

# ══════════════════════════════════════════════════════════════════════════════
# Wake + Poll server
# ══════════════════════════════════════════════════════════════════════════════
async def wait_for_server(set_msg=print):
    set_msg("Waking up prediction server…")

    # Fire initial wake ping
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{BASE}/health", timeout=3.0)
    except Exception:
        pass

    MAX_ATTEMPTS = 10
    for attempt in range(MAX_ATTEMPTS):
        await asyncio.sleep(3)
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{BASE}/health", timeout=5.0)
                if res.status_code == 200:
                    json_data = res.json()
                    if json_data.get("status") == "ok":
                        print(f"✅ Server ready after ~{(attempt + 1) * 3}s")
                        set_msg("Server is ready — running predictions…")
                        return True
        except Exception:
            pass

        waited = (attempt + 1) * 3
        set_msg(f"Server is starting… ({waited}s elapsed, please wait)")
        print(f"⏳ Waiting for server... attempt {attempt + 1}/{MAX_ATTEMPTS}")

    raise Exception("Server did not respond after 30 seconds. Please try again.")



# ══════════════════════════════════════════════════════════════════════════════
# Bulk prediction
# ══════════════════════════════════════════════════════════════════════════════
async def predict_rows(rows, set_msg=print):
    """
    rows: list of dicts with 'marchandise' key
    returns: list of predictions
    """
    await wait_for_server(set_msg)

    set_msg("Sending data to prediction API…")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BASE}/predict",
                json={"rows": [{"marchandise": r["marchandise"]} for r in rows]},
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            json_data = response.json()
            print("RAW PREDICTION RESPONSE:", json_data)
            return json_data.get("predictions", [])

    except httpx.TimeoutException:
        raise Exception("Prediction request timed out after 1 minute.")





# ══════════════════════════════════════════════════════════════════════════════
# Updated align_data using predictions instead of find_type_and_produit
# ══════════════════════════════════════════════════════════════════════════════
def align_data(uploaded_df, mapping):
    try:
        valid_mappings_count = sum(
            1 for value in mapping.values() if value is not None
        )

        if valid_mappings_count <= 2:
            return uploaded_df, False

        # Rename columns based on the mapping
        df_mapped = uploaded_df.rename(columns=mapping)

        final_cols = [value for key, value in mapping.items() if value is not None]

        # Keep only the required columns
        df_aligned = df_mapped[final_cols].copy()

        if COL_DESIGNATION in df_aligned.columns:

            # --- 1. BYPASS: Save existing values before overwriting ---
            orig_type    = df_aligned[COL_TYPE].copy()    if COL_TYPE    in df_aligned.columns else None
            orig_produit = df_aligned[COL_PRODUIT].copy() if COL_PRODUIT in df_aligned.columns else None

            # --- 2. BUILD rows for prediction API ---
            rows = [
                {"marchandise": val if isinstance(val, str) else ""}
                for val in df_aligned[COL_DESIGNATION]
            ]

            # --- 3. CALL prediction API ---
            predictions = asyncio.run(predict_rows(rows))

            # --- 4. APPLY predictions ---
            # predictions is expected to be a list of dicts:
            # [{"cargo_type": "COIL", "produit": "UNIT"}, ...]
            df_aligned[COL_TYPE]    = [p.get("Produits", None) for p in predictions]
            df_aligned[COL_PRODUIT] = [p.get("Details", None)    for p in predictions]

            # --- 5. REINSERT: Put back original values where they were not null ---
            if orig_type is not None:
                mask = orig_type.notna() & (orig_type != '')
                df_aligned.loc[mask, COL_TYPE] = orig_type[mask]

            if orig_produit is not None:
                mask = orig_produit.notna() & (orig_produit != '')
                df_aligned.loc[mask, COL_PRODUIT] = orig_produit[mask]

        else:
            for col in [COL_TYPE, COL_PRODUIT]:
                if col not in df_aligned.columns:
                    df_aligned[col] = 'None'
                else:
                    df_aligned[col] = df_aligned[col].fillna('None')

        return df_aligned, True

    except Exception as e:
        print(f"Error during alignment: {e}")
        return uploaded_df, False

def get_manual_color(product_name):
    """Maps product names to specific hex colors as requested."""
    name = str(product_name).upper()
    
    # Group products by color
    color_groups = {
        "92D050": ["CTP", "PLYWOOD", "MDF", "FFP", "MDF + PLYWOOD"],                      # Greenish
        "538DD5": ["BIG BAG", "BAG", "PIPE", "CORNIERE", "CORNIERS"],                      # Blue
        "C65911": ["TUBE", "FORMWORK", "POUTRELLE"],                                       # Brown/Orange
        "948A54": ["BOB", "BOBINE", "COIL", "METAL SHEET", "STEEL BEAMS"],                 # Tan/Gold
        "DDD9C4": ["BEAMS", "FIL", "FIL M"],                                              # Grey/Beige
        "FFDC6B": ["COLI", "COLIS", "UNIT", "BUS", "MINI BUS", "CAMIONS", "CAMION POMPE A BETON", "REMORQUES", "EXCAVATEUR", "BULLDOZER", "CHARGEUR", "COMPACTEUR", "FINISSEUR", "CAMION GRUE", "CHARIOT ELEVATEUR", "NIVELEUSE"], # GOLD
    }

    
    # Find which group the product belongs to
    for color, products in color_groups.items():
        if name in products:
            return color
    
    # Returns None (White) if not found or for 'Others'
    return None


def apply_summary_conditional_formatting(ws, summary_rows, start_col, clients):
    red_fill = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")

    total_row = summary_rows[0]      # total decharger
    manifest_row = summary_rows[1]   # total quantite manifest
    reste_row = summary_rows[2]      # reste

    first_client_col = get_column_letter(start_col + 2)
    last_client_col = get_column_letter(start_col + 1 + len(clients))

    total_range = f"{first_client_col}{total_row}:{last_client_col}{total_row}"
    manifest_range = f"{first_client_col}{manifest_row}:{last_client_col}{manifest_row}"
    reste_range = f"{first_client_col}{reste_row}:{last_client_col}{reste_row}"

    # total decharger row
    ws.conditional_formatting.add(
        total_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}>{first_client_col}{manifest_row}"],
            fill=red_fill,
            stopIfTrue=True
        )
    )
    ws.conditional_formatting.add(
        total_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}={first_client_col}{manifest_row}"],
            fill=yellow_fill
        )
    )

    # total quantite manifest row
    ws.conditional_formatting.add(
        manifest_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}>{first_client_col}{manifest_row}"],
            fill=red_fill,
            stopIfTrue=True
        )
    )
    ws.conditional_formatting.add(
        manifest_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}={first_client_col}{manifest_row}"],
            fill=yellow_fill
        )
    )

    # reste row
    ws.conditional_formatting.add(
        reste_range,
        FormulaRule(
            formula=[f"={first_client_col}{reste_row}<0"],
            fill=red_fill,
            stopIfTrue=True
        )
    )
    ws.conditional_formatting.add(
        reste_range,
        FormulaRule(
            formula=[f"={first_client_col}{reste_row}=0"],
            fill=yellow_fill
        )
    )


# @st.cache_resource
def ensure_directories():
    """Creates folders if they don't exist. Cached to run only once."""
    for p in LIST_OF_PATHS:
        Path(p).mkdir(parents=True, exist_ok=True)

 # Helper function to get display name without extension
# ============================================================
def get_display_name(filename: str) -> str:
    """Remove file extension for display"""
    from pathlib import Path
    return Path(filename).stem

def clean_dataframe_types(datasource , only_cols=None):
    """
    Loops through columns and applies appropriate types and handles None/NaN.
    """
    # 1. Define Column Groups
    # numeric_cols = ["QUANTITE", "TONAGE", "RESTE T/P", "SURFACE"]
    # text_cols = ["NAVIRE", "B/L", "DESIGNATION", "CLIENT","DATE" ]
    # category_cols = ["TYPE", "SITUATION", "CLES"]

    cols_to_process = only_cols if only_cols is not None else datasource.columns
    for col in cols_to_process:
        if col not in datasource.columns:
            continue
        # --- Handle Text Columns (The "FLOAT" Error Fix) ---
        if col in text_cols:
            # Force to string first, then clean up the 'nan' strings
            datasource[col] = datasource[col].astype(str).replace(['nan', 'None', 'NaN', 'null'], '')
            datasource[col] = datasource[col].str.replace(r'\.0$', '', regex=True) # Removes .0 from IDs
            
        # --- Handle Numeric Columns ---
        elif col in numeric_cols:
            datasource[col] = pd.to_numeric(datasource[col], errors='coerce').fillna(0.0)
            if col == "QUANTITE":
                datasource[col] = datasource[col].astype(int)

        # --- Handle Date Columns ---
        elif col in date_cols:
            # Convert to datetime; errors='coerce' turns bad dates into NaT (Accepted by DateColumn)
            datasource[col] = pd.to_datetime(datasource[col], errors='coerce')

        # --- Handle Category Columns ---
        elif col in category_cols:
            default_val = "En attente" if col == "SITUATION" else "N/A" 
            datasource[col] = datasource[col].astype(str).replace(['nan', 'None', 'NaN'], default_val)

    return datasource


def getDB():
    # 1. Check if the database file exists
    dir_name = os.path.dirname(DB_PATH)
    if not os.path.exists(dir_name):
        st.info(f"Database file creation at: {DB_PATH}")
        os.makedirs(dir_name)

    # 2. Create empty Excel file if it doesn't exist
    if not os.path.exists(DB_PATH):
        # Create a basic dataframe with columns
        df_new = pd.DataFrame(columns=COLUMNS)
        df_new.to_excel(DB_PATH, index=False)
        st.info(f"Created new database at: {DB_PATH}")

    # 2. Load the Master Data
    try:
        # We read from the single constant path now
        df = pd.read_excel(DB_PATH)
        return df
    except Exception as e:
        st.error(f"Error reading database: {e}")
        return null


def create_mapping_ui(uploaded_df, required_columns=COLUMNS):
    st.write("### Map Imported Columns to Database Columns")
    mapping = {}

    # Create a dropdown for every required column
    for req_col in required_columns:
        mapping[req_col] = st.selectbox(
            f"Select the source for: **{req_col}**",
            options=[None] + list(uploaded_df.columns),
            key=f"map_{req_col}"
        )
    return mapping


def find_type_and_produit(designation):
    """
    Return (CARGO_TYPE, PRODUIT_CATEGORY) by matching keywords against the designation.
    Rules are checked in order — first match wins for cargo_type.
    PRODUIT scans the full designation against UNIT and PACKAGE sets.
    """
    if not isinstance(designation, str):
        return pd.Series([None, None])

    designation_upper = designation.upper()

    # Step 1: Find cargo_type from KEYWORD_RULES (first match wins)
    cargo_type = None
    for keywords, ctype in KEYWORD_RULES:
        for keyword in keywords:
            if keyword.upper() in designation_upper:
                cargo_type = ctype
                break
        if cargo_type is not None:
            break

    # Step 2: Check designation directly against BOTH category sets
    is_unit = any(
        constant.upper() in designation_upper
        for constant in UNIT_CARGO_TYPES
    )
    is_package = any(
        constant.upper() in designation_upper
        for constant in PACKAGE_CARGO_TYPES
    )

    # Step 3: Also check cargo_type itself against category sets
    if cargo_type is not None:
        if not is_unit:
            is_unit = matches_any_constant(cargo_type, UNIT_CARGO_TYPES)
        if not is_package:
            is_package = matches_any_constant(cargo_type, PACKAGE_CARGO_TYPES)

    # Step 4: Determine PRODUIT
    if is_package and is_unit:
        produit = "UNIT + PACKAGE"
    elif is_package:
        produit = "PACKAGE"
    elif is_unit:
        produit = "UNIT"
    else:
        produit = cargo_type  # Unknown → flag for manual review

    return pd.Series([cargo_type, produit])



@st.dialog("Map Your Columns", width="large")
def show_mapping_dialog(uploaded_df):
    st.write("Match your file columns to the database headings:")
    # st.info(list(uploaded_df.columns))
    st.session_state.trigger_mapping = False
    mapping = {}
    uploaded_cols = list(uploaded_df.columns)
    COLS_PER_ROW = 4

    for i in range(0, len(COLUMNS), COLS_PER_ROW):
        row_cols = st.columns(COLS_PER_ROW)
        batch = COLUMNS[i: i + COLS_PER_ROW]

        for j, req_col in enumerate(batch):
            with row_cols[j]:
                with st.container(border=True):
                    st.markdown(f"**{req_col}**")

                    # --- AUTO-MATCH LOGIC ---
                    # Find first uploaded col that contains the required name (e.g., 'date' in 'date_manifeste')
                    default_index = 0  # Default to None
                    for idx, col in enumerate(uploaded_cols):
                        if req_col.lower() in col.lower():
                            default_index = idx + 1 # +1 because [None] is at index 0
                            break
                    # ------------------------

                    selected_source_column = st.selectbox(
                        f"Source for {req_col}:",
                        options=[None] + uploaded_cols,
                        index=default_index,
                        key=f"map_{req_col}",
                        label_visibility="collapsed"
                    )
                    
                    if selected_source_column:
                        mapping[selected_source_column] = req_col
        
        st.session_state.final_mapping = mapping

    if st.button("Confirm and Import", type="primary", width='stretch'):
        # 1. Clear the trigger immediately so it doesn't re-open
        st.session_state.final_mapping = mapping
        # st.session_state.mapping_shown = True
        st.session_state.uploaded_file = None
        # Print to the terminal window

        # 2. Force a rerun to close the dialog and update the main app
        st.rerun()


# ---------------------------------------------------------------------------
# Commodity / received-lines helpers.
# ---------------------------------------------------------------------------

def _normalize_commodity_text(value):
    """Normalize a commodity cell value for deterministic matching."""
    if value is None:
        return ""
    # Strip accents / diacritics (e.g. unité -> unite)
    text = str(value)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


def _normalize_match_text(value):
    """
    Normalize text for delimiter-insensitive matching. Underscores and hyphens
    are treated as spaces so e.g. 'DUMP_TRUCK' matches 'DUMP TRUCK'.
    """
    if value is None:
        return ""
    text = _normalize_commodity_text(value)
    text = re.sub(r"[-_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_package_type(text):
    """
    Check if text denotes a package/colis in French or English, singular or plural.
    e.g. COLIS, COLI, PACKAGE, PACKAGES, PKG, PKGS, CAISSE, CAISSES, CARTON, CARTONS, BOX, BOXES.
    """
    norm = _normalize_match_text(text)
    if not norm:
        return False
    words = norm.split()
    package_keywords = {
        "COLIS", "COLI", "PACKAGE", "PACKAGES", "PKG", "PKGS",
        "CAISSE", "CAISSES", "CARTON", "CARTONS", "BOX", "BOXES",
        "SPARE_PARTS", "SPARE PART", "SPARE PARTS"
    }
    for w in words:
        if w in package_keywords:
            return True
    return False


def _is_unit_type(text):
    """
    Check if text denotes a unit/unite in French or English, singular or plural,
    or matches unit machinery/vehicles.
    e.g. UNIT, UNITS, UNITE, UNITES, or machinery categories.
    """
    norm = _normalize_match_text(text)
    if not norm:
        return False
    words = norm.split()
    unit_keywords = {"UNIT", "UNITS", "UNITE", "UNITES"}
    for w in words:
        if w in unit_keywords:
            return True
    return False


def _is_unit_package_combined(value):
    """Return True when a value explicitly denotes a combined unit+package group."""
    text = _normalize_commodity_text(value)
    if not text:
        return False
    # Normalise '+' spacing so 'UNITS + PACKAGES' and 'UNITS+PACKAGES' both work.
    text = re.sub(r"\s*\+\s*", " + ", text)
    text = re.sub(r"\s+", " ", text).strip()
    has_unit = ("UNIT" in text or "UNITE" in text)
    has_pkg = ("PACKAGE" in text or "COLI" in text or "CAISSE" in text or "PKG" in text)
    return has_unit and has_pkg


def _matches_keyword(text, keyword):
    """Case-insensitive substring / regex-word match after normalizing both sides."""
    if not text:
        return False
    kw = _normalize_commodity_text(keyword)
    if not kw:
        return False
    # Exact or word boundary match
    pattern = r"\b" + re.escape(kw) + r"(S|ES)?\b"
    return bool(re.search(pattern, text)) or kw in text


def _classify_commodity(raw_commodity):
    """
    Return (family, source) where family is the normalized commodity type and
    source is 'family' (direct GOODS__TYPES/COMMODITY_TYPES match) or 'rule'
    (KEYWORD_RULES match). More specific labels are tried first.
    """
    text = _normalize_commodity_text(raw_commodity)
    if not text:
        return None, None

    # Direct known structural families.
    known_families = [
        "BIG BAG",
        "PLYWOOD",
        "PIPE",
        "TUBE",
        "BEAMS",
        "METAL SHEET",
        "STEEL BEAMS",
        "FORMWORK",
        "FIL M",
        "COIL",
        "BOBINE",
        "BOB",
        "POUTRELLE",
        "CORNIERE",
        "CTP",
        "MDF",
        "FFP",
        "MDF + PLYWOOD",
        "WHITE WOOD",
        "BEECH WOOD",
        "RED WOOD",
        "BRIDGE COMP",
    ]
    # Sort by normalized length so compound entries are checked first
    known_families.sort(key=lambda family: len(_normalize_commodity_text(family)), reverse=True)

    for family in known_families:
        if _matches_keyword(text, family):
            return family.upper(), "family"

    # Canonical KEYWORD_RULES fallback.
    keyword_rules = [
        (keyword, cargo_type)
        for keywords, cargo_type in KEYWORD_RULES
        for keyword in keywords
    ]
    keyword_rules.sort(
        key=lambda item: len(_normalize_commodity_text(item[0])),
        reverse=True,
    )
    for keyword, cargo_type in keyword_rules:
        if _matches_keyword(text, keyword):
            return cargo_type, "rule"

    return None, None


def _big_bags_received_template(rec_str):
    commodity = "BIG BAGS"
    received_lines = [
        "BIG BAGS FOUND TORN ON BOARD",
        "BIG BAGS FOUND BROKEN ON BOARD",
        "EMPTY BAG ON BOARD",
    ]
    total_rec_str = f"{rec_str}  Big Bags"
    return commodity, received_lines, total_rec_str


def _crates_received_template(display_name, rec_str):
    commodity = display_name or "CRATES"
    received_lines = [
        f"Crates of {commodity} Found Dismembered on board",
        f"Crates of {commodity} wet on board (Packing and/or Contents)",
        f"Crates of {commodity} moldy on board (Packing and/or Contents)",
    ]
    total_rec_str = f"{rec_str}  Crates of {commodity}"
    return commodity, received_lines, total_rec_str


def _bundles_received_template(display_name, rec_str, bundle_label=None):
    label = bundle_label or display_name
    commodity = f"Bundles of {label}"
    received_lines = [
        f"{commodity}.",
        f"{commodity} Found Dismembered on board",
    ]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _lumber_received_template(display_name, rec_str):
    """Wood/lumber (white/beech/red wood) uses the bundle + wet/mouldy wording."""
    commodity = "BUNDLES"
    received_lines = [
        f"Bundles of {display_name} Found Dismembered on board",
        f"Bundles of {display_name} wet on board (Packing and/or Contents)",
        f"Bundles of {display_name} moldy on board (Packing and/or Contents)",
    ]
    total_rec_str = f"{rec_str}  Bundles of {display_name}"
    return commodity, received_lines, total_rec_str


def _coils_received_template(rec_str):
    commodity = "COILS"
    received_lines = [
        "Coils Found Rusty on board",
        "Coils Packaging damaged on board",
    ]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _simple_received_template(rec_str, commodity):
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _unit_received_template(rec_str):
    commodity = "Unit"
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  Units"
    return commodity, received_lines, total_rec_str


def _package_received_template(rec_str):
    commodity = "package"
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _unit_package_received_template(rec_str):
    commodity = "Units + Package"
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _general_cargo_received_template(rec_str, display_name):
    commodity = display_name or "General Cargo"
    received_lines = ["Packaging damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _compute_commodity_and_received_lines(raw_commodity: str, rec_str: str):
    """
    Given the raw commodity string from Excel and the received quantity string (rec_str),
    compute:
      - normalized commodity name
      - list of 'received' description lines
      - total_rec_str string to be displayed under 'Total Received'
    """
    raw_text = _normalize_commodity_text(raw_commodity)
    display_name = raw_text or "General Cargo"

    family, _ = _classify_commodity(raw_commodity)

    # ----------------------------------------------------------------
    # 1. Specific product families / KEYWORD_RULE canonical groups
    # ----------------------------------------------------------------
    if family == "BIG BAG":
        return _big_bags_received_template(rec_str)

    if family in {"MDF", "CTP", "FFP", "MDF + PLYWOOD", "PLYWOOD"}:
        return _crates_received_template(display_name, rec_str)

    if family in {"PIPE", "TUBE"}:
        commodity = "TUBES"
        received_lines = ["TUBES.", "TUBES Damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"
        return commodity, received_lines, total_rec_str

    if family == "POUTRELLE":
        return _simple_received_template(rec_str, commodity="POUTRELLES")

    if family == "CORNIERE":
        return _simple_received_template(rec_str, commodity="CORNIERES")

    if family in {"STEEL BEAMS", "BEAMS"}:
        return _bundles_received_template(display_name, rec_str, bundle_label="BEAMS")

    if family == "METAL SHEET":
        return _bundles_received_template(display_name, rec_str, bundle_label="METAL SHEET")

    if family == "FORMWORK":
        return _bundles_received_template(display_name, rec_str, bundle_label="formwork")

    if family == "FIL M":
        commodity = "FIL MACHINE"
        received_lines = ["RLX FOUND DISMEMBERED ON BOARD"]
        total_rec_str = f"{rec_str}  {commodity}"
        return commodity, received_lines, total_rec_str

    if family in {"COIL", "BOBINE", "BOB"}:
        return _coils_received_template(rec_str)

    if family in {"WHITE WOOD", "BEECH WOOD", "RED WOOD"}:
        return _lumber_received_template(display_name, rec_str)

    if family == "BRIDGE COMP":
        return _bundles_received_template(display_name, rec_str)

    # ----------------------------------------------------------------
    # 2. Unit / package buckets (multilingual + singular/plural)
    # ----------------------------------------------------------------
    if _is_unit_package_combined(raw_text):
        return _unit_package_received_template(rec_str)

    unit_hit = _is_unit_type(raw_text) or _is_unit_type(family or "")
    package_hit = _is_package_type(raw_text) or _is_package_type(family or "")

    if raw_text:
        unit_hit = unit_hit or matches_any_constant(raw_text, UNIT_CARGO_TYPES)
        package_hit = package_hit or matches_any_constant(raw_text, PACKAGE_CARGO_TYPES)

    if family:
        unit_hit = unit_hit or matches_any_constant(family, UNIT_CARGO_TYPES)
        package_hit = package_hit or matches_any_constant(family, PACKAGE_CARGO_TYPES)

    if family in COMMODITY_TYPES and family not in GOODS__TYPES:
        unit_hit = True

    if unit_hit and package_hit:
        return _unit_package_received_template(rec_str)
    if package_hit:
        return _package_received_template(rec_str)
    if unit_hit:
        return _unit_received_template(rec_str)

    # ----------------------------------------------------------------
    # 3. General cargo fallback
    # ----------------------------------------------------------------
    return _general_cargo_received_template(rec_str, display_name)


def computecommodity_and_received_lines(raw_commodity: str, rec_str: str):
    """
    Public compatibility wrapper for the non-underscore function name.
    Retains the original signature and return tuple.
    """
    return _compute_commodity_and_received_lines(raw_commodity, rec_str)


def _fill_entry_table(
    doc,
    table,
    client: str,
    commodity: str,
    manifest_qty_str: str,
    tonnage_str: str,
    received_lines,
    total_rec_str: str,
):
    """
    Fill the 5-row table in the DOCX document for a single cargo entry.
    Handles:
      - Receiver / Commodity
      - Manifested Quantity / Tonnage
      - Dynamic 'Received:' lines
      - Total Received line
      - Final note and separator
    """
    # Row 0: Receiver / Commodity
    row0 = table.rows[0].cells
    row0[0].width = Cm(9)
    p0 = row0[0].paragraphs[0]
    p0.add_run("Receiver : ").bold = True
    p0.add_run(client)
    p0.alignment = WD_ALIGN_PARAGRAPH.LEFT

    row0[1].width = Cm(9)
    p1 = row0[1].paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_c = p1.add_run("Commodity : ")
    run_c1 = p1.add_run(commodity)
    run_c.bold = True
    run_c.font.name = "Agency FB"
    run_c1.font.name = "Agency FB"

    # Row 1: Manifested Quantity / Tonnage
    row1 = table.rows[1].cells
    row1[0].width = Cm(12)
    p2 = row1[0].paragraphs[0]
    p2.add_run("Manifested Quantity : ").bold = True
    p2.add_run(f"{manifest_qty_str} {commodity}")
    p2.alignment = WD_ALIGN_PARAGRAPH.LEFT

    row1[1].width = Cm(5)
    p3 = row1[1].paragraphs[0]
    p3.add_run("Tonnage : ").bold = True
    p3.add_run(f"{tonnage_str} Mt")
    p3.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # --- DYNAMIC RECEIVED AREA (Row 2) ---
    row2 = table.rows[2].cells
    row2[0].width = Cm(30)

    row2_cell = table.rows[2].cells[0]

    # Clear default paragraph and add the formatted lines
    row2_cell.paragraphs[0].clear()
    for i, line in enumerate(received_lines):
        if i == 0:
            p = row2_cell.paragraphs[0]
        else:
            p = row2_cell.add_paragraph()

        run_label = p.add_run("Received:    ")
        run_label.bold = True
        p.add_run(line)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Row 3: Total Received
    row3 = table.rows[3].cells
    row3[0].width = Cm(12)
    p4 = row3[0].paragraphs[0]
    p4.add_run("Total Received: ").bold = True
    p4.add_run(f" {total_rec_str}")
    p4.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Row 4: Final line
    row4 = table.rows[4].cells
    row4[0].width = Cm(25)
    p5 = row4[0].paragraphs[0]
    full = p5.add_run("The Quantity Will Be confirmed after delivery Cargo.")
    full.bold = True

    # Border Line
    p_sep = doc.add_paragraph()
    p_sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sep = p_sep.add_run("=*"*29)
    run_sep.bold = True


def _shorten_bl_code(bl: str) -> str:
    """
    Shorten B/L codes like '25030TJD0701-17' or '25030TJD0101/01'
    Rule: Find 3 consecutive letters, then take those 3 letters and everything after them.
    Examples:
        '25030TJD0701-17' -> 'TJD0701-17'
        '25030TJD0101/01' -> 'TJD0101/01'
    """
    if bl is None:
        return ""
    s = str(bl).strip()

    # Find 3 consecutive letters
    m = re.search(r"([A-Za-z]{3})(.*)$", s)
    if m:
        # Return the 3 letters + everything after them
        return m.group(1) + m.group(2)

    return s


def matches_any_constant(type_str, constants_set):
    """
    Check if type_str contains any constant from constants_set (or vice versa).
    Handles partial matches like "ENGINS" matching "ENGIN" or "grue lourd" matching "GRUE".
    Empty/None values never match.
    """
    type_str_upper = _normalize_match_text(type_str)
    if not type_str_upper:
        return False

    for constant in constants_set:
        constant_upper = _normalize_match_text(constant)
        if not constant_upper:
            continue
        if constant_upper in type_str_upper:
            return True
        if type_str_upper in constant_upper:
            return True
    return False


def normalize_type(type_value):
    """
    Normalize TYPE value to standard categories.
    Recognizes French and English, singular and plural.
    Groups units and packages into 'UNITS + PACKAGES' so the same client
    has all units + packages aggregated under one entry.
    """
    if pd.isna(type_value):
        return None

    type_str = _normalize_commodity_text(type_value)
    if not type_str:
        return type_str

    # 1. Combined unit+package group
    if _is_unit_package_combined(type_str):
        return "UNITS + PACKAGES"

    # 2. Structural/goods families first (BOBINE/COIL, PIPE/TUBE, POUTRELLE, CORNIERE, CTP, MDF, etc.)
    if _matches_keyword(type_str, "CTP"):
        return "CTP"
    if _matches_keyword(type_str, "BOBINE") or _matches_keyword(type_str, "BOB") or _matches_keyword(type_str, "COIL"):
        return "BOBINE"
    if _matches_keyword(type_str, "PIPE") or _matches_keyword(type_str, "TUBE"):
        return "PIPE"
    if _matches_keyword(type_str, "POUTRELLE"):
        return "POUTRELLE"
    if _matches_keyword(type_str, "CORNIERE") or _matches_keyword(type_str, "CORNIER"):
        return "CORNIERE"

    structural_families = [
        "MDF + PLYWOOD",
        "MDF",
        "PLYWOOD",
        "FFP",
        "BEAMS",
        "STEEL BEAMS",
        "METAL SHEET",
        "FORMWORK",
        "FIL M",
        "BRIDGE COMP",
        "BIG BAG",
    ]
    structural_families.sort(
        key=lambda family: len(_normalize_commodity_text(family)),
        reverse=True,
    )
    for family in structural_families:
        if _matches_keyword(type_str, family):
            return family.upper()

    # 3. Units and Packages classification (multilingual + singular/plural)
    is_pkg = _is_package_type(type_str) or matches_any_constant(type_str, PACKAGE_CARGO_TYPES)
    is_unit = _is_unit_type(type_str) or matches_any_constant(type_str, UNIT_CARGO_TYPES)

    family, _ = _classify_commodity(type_str)
    if family:
        is_pkg = is_pkg or _is_package_type(family) or matches_any_constant(family, PACKAGE_CARGO_TYPES)
        is_unit = is_unit or _is_unit_type(family) or matches_any_constant(family, UNIT_CARGO_TYPES)

    if family in COMMODITY_TYPES and family not in GOODS__TYPES:
        is_unit = True

    if is_unit or is_pkg:
        return "UNITS + PACKAGES"

    return type_str


def first_non_null(series):
    return next((x for x in series if pd.notna(x)), None)


# Helper function for B/L aggregation
def aggregate_bl(series):
    """
    Collect every distinct, non-empty B/L value in the group and join them
    into a single aggregated string (e.g. 'BL1 / BL2 / BL3').
    """
    bl_values = []
    for x in series:
        if pd.notna(x):
            s = str(x).strip()
            if s:
                # In case a cell already contains ' / ', split and preserve distinct items
                parts = [p.strip() for p in s.split('/') if p.strip()]
                bl_values.extend(parts)
    if not bl_values:
        return ""
    unique_bls = list(dict.fromkeys(bl_values))
    return " / ".join(unique_bls)


# Specified order, plus the generic buckets that must be last.
COMMODITY_SORT_ORDER = {
    "CTP": 0,
    "BOBINE": 1,
    "PIPE": 2,
    "POUTRELLE": 3,
    "CORNIERE": 4,
    "UNITS + PACKAGES": 6,
    "UNITS": 7,
    "PACKAGES": 8,
}
# Priority for every structural / general commodity outside the explicit list.
OTHER_COMMODITY_SORT_PRIORITY = 5


def _canonical_sort_group(type_value):
    """
    Reduce a TYPE value to the canonical commodity group used for ordering.
    Supports English & French, singular & plural.
    Aliases such as TUBE/PIPE or BOB/COIL/BOBINE are collapsed so related
    structural commodities order together.
    """
    if type_value is None:
        return "OTHER"

    text = _normalize_commodity_text(type_value)
    if not text:
        return "OTHER"

    # Combined unit+package label
    if _is_unit_package_combined(text):
        return "UNITS + PACKAGES"

    # Specified structural commodities and their aliases (FR + EN, sing + plur)
    if _matches_keyword(text, "CTP"):
        return "CTP"
    if _matches_keyword(text, "BOBINE") or _matches_keyword(text, "BOB") or _matches_keyword(text, "COIL"):
        return "BOBINE"
    if _matches_keyword(text, "PIPE") or _matches_keyword(text, "TUBE"):
        return "PIPE"
    if _matches_keyword(text, "POUTRELLE"):
        return "POUTRELLE"
    if _matches_keyword(text, "CORNIERE") or _matches_keyword(text, "CORNIER"):
        return "CORNIERE"

    structural_families = [
        "MDF + PLYWOOD",
        "MDF",
        "PLYWOOD",
        "FFP",
        "BEAMS",
        "STEEL BEAMS",
        "METAL SHEET",
        "FORMWORK",
        "FIL M",
        "BRIDGE COMP",
        "BIG BAG",
    ]
    structural_families.sort(
        key=lambda family: len(_normalize_commodity_text(family)),
        reverse=True,
    )
    for family in structural_families:
        if _matches_keyword(text, family):
            return family.upper()

    # Generic unit / package buckets
    family, _ = _classify_commodity(text)
    is_unit = _is_unit_type(text) or _is_unit_type(family or "") or matches_any_constant(family or text, UNIT_CARGO_TYPES)
    is_package = _is_package_type(text) or _is_package_type(family or "") or matches_any_constant(family or text, PACKAGE_CARGO_TYPES)

    if family in COMMODITY_TYPES and family not in GOODS__TYPES:
        is_unit = True

    if is_unit and is_package:
        return "UNITS + PACKAGES"
    if is_unit:
        return "UNITS"
    if is_package:
        return "PACKAGES"

    return text


def commodity_sort_priority(type_value):
    """
    Return the sort priority for a TYPE value used by both Bordereaux and
    Débarquement. Lower numbers are rendered first.
    """
    group = _canonical_sort_group(type_value)
    if group in COMMODITY_SORT_ORDER:
        return COMMODITY_SORT_ORDER[group]
    return OTHER_COMMODITY_SORT_PRIORITY


def _apply_commodity_sort(commodity_type):
    return commodity_sort_priority(commodity_type)


def group_sourcefile_by_client(
    input_excel: str,
    sheet_name: int | str = 0,
    skip_units_packages: bool = False,
    bl_aggregated: bool = False,
) -> pd.DataFrame:
    df = pd.read_excel(input_excel, sheet_name=sheet_name, engine="openpyxl")

    # Skip rows whose commodity type is in UNITS_TYPES or PACKAGES_TYPES
    if skip_units_packages and COL_TYPE in df.columns:
        skip_types = UNITS_TYPES | PACKAGES_TYPES
        df = df[
            ~df[COL_TYPE]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(skip_types)
        ].reset_index(drop=True)

    # Ensure numeric
    for col in [COL_QUANTITE, COL_TONAGE]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Short B/L into the same column
    if COL_BL in df.columns:
        df[COL_BL] = df[COL_BL].apply(_shorten_bl_code)
    
    # Normalize TYPE column before grouping
    if COL_TYPE in df.columns:
        df[COL_TYPE] = df[COL_TYPE].apply(normalize_type)

    # Base aggregation
    agg_dict = {
        COL_QUANTITE: "sum",
        COL_TONAGE: "sum",
        COL_BL: aggregate_bl,
    }

    skip_cols = [COL_CLIENT, COL_QUANTITE, COL_TONAGE, COL_BL, COL_PRODUIT, COL_TYPE]
    
    if not bl_aggregated:
        skip_cols.remove(COL_BL)
        agg_dict.pop(COL_BL, None)

    # For all other columns, keep first non-null value
    for col in COLUMNS:
        if col in skip_cols:
            continue
        
        if col in df.columns:
            agg_dict[col] = first_non_null
           
    grouped = df.groupby([COL_CLIENT, COL_TYPE], as_index=False).agg(agg_dict)

    # Apply the shared commodity ordering used by both document types
    grouped['sort_priority'] = grouped[COL_TYPE].apply(_apply_commodity_sort)

    # Sort
    sorted_grouped = grouped.sort_values(
        by=['sort_priority', COL_CLIENT],
        ascending=[True, True],
        na_position='last'
    ).reset_index(drop=True)

    # Clean up
    sorted_grouped = sorted_grouped.drop(columns=['sort_priority'])
    
    return sorted_grouped

