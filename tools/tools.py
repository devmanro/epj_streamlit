import streamlit as st
import re
import os
import pandas as pd
from pyarrow import null

from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT


from assets.constants.constants import (
    COL_CLIENT,
    COL_QUANTITE,
    COL_TONAGE,
    COL_BL,

    # add COL_VALUES here if you have such a column name
    COL_TYPE,
    COMMODITY_TYPES,
)


from assets.constants.constants import DB_PATH, COLUMNS


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


def align_data(uploaded_df, mapping):
    try:
        # st.write("mappe*ing:")
        valid_mappings_count = sum(
            1 for value in mapping.values() if value is not None)

        if valid_mappings_count <= 2:
            return uploaded_df, False  # Return original DataFrame if required columns are missing

        # Rename columns based on the mapping
        df_mapped = uploaded_df.rename(columns=mapping)

        final_cols = [value for key, value in mapping.items()
                      if value is not None]

        # Keep only the required columns
        df_aligned = df_mapped[final_cols]

        return df_aligned, True

    except Exception as e:
        print(f"Error during alignment: {e}")
        return uploaded_df, False


@st.dialog("Map Your Columns", width="large")
def show_mapping_dialog(uploaded_df):
    st.write("Match your file columns to the database headings:")
    # st.info(list(uploaded_df.columns))

    mapping = {}
    st.session_state.trigger_mapping = False
    st.session_state.final_mapping = mapping
    # Define how many mapping boxes you want per row
    COLS_PER_ROW = 4

    # Iterate through COLUMNS in chunks to create rows
    for i in range(0, len(COLUMNS), COLS_PER_ROW):
        row_cols = st.columns(COLS_PER_ROW)

        # Get the subset of columns for this specific row
        batch = COLUMNS[i: i + COLS_PER_ROW]

        for j, req_col in enumerate(batch):
            with row_cols[j]:
                # Using a container or border for better visual separation
                with st.container(border=True):
                    st.markdown(f"**{req_col}**")

                    selected_source_column = st.selectbox(
                        "Source column:",
                        options=[None] + list(uploaded_df.columns),
                        key=f"map_{req_col}",
                        label_visibility="collapsed"  # Hide label to save space
                    )
                    if selected_source_column:  # Only add to mapping if a column was selected
                        mapping[selected_source_column] = req_col

    if st.button("Confirm and Import", type="primary", width='stretch'):
        # 1. Clear the trigger immediately so it doesn't re-open
        st.session_state.final_mapping = mapping
        # st.session_state.mapping_shown = True
        st.session_state.uploaded_file = None
        # Print to the terminal window

        # 2. Force a rerun to close the dialog and update the main app
        st.rerun()


def _compute_commodity_and_received_lines(raw_commodity: str, rec_str: str):
    """
    Given the raw commodity string from Excel and the received quantity string (rec_str),
    compute:
      - normalized commodity name
      - list of 'received' description lines
      - total_rec_str string to be displayed under 'Total Received'
    """
    commodity = raw_commodity
    received_lines = []
    total_rec_str = rec_str

    if "BAG" in raw_commodity or "BAG" in raw_commodity:
        commodity = "Big Bags"
        total_rec_str = f"{rec_str}  Big Bags"
        received_lines = [
            "BIG BAGS FOUND TORN ON BOARD",
            "BIG BAGS FOUND BROKEN ON BOARD",
            "EMPTY BAG ON BOARD",
        ]

    elif any(x in raw_commodity for x in ["PLYWOOD", "MDF", "CTP"]):
        commodity = raw_commodity
        received_lines = [
            f"Crates of {commodity} Found Dismembered on board",
            f"Crates of {commodity} wet on board (Packing and/or Contents)",
            f"Crates of {commodity} moldy on board (Packing and/or Contents)",
        ]
        total_rec_str = f"{rec_str}  Crates of {commodity}"

    elif any(x in raw_commodity for x in ["PIPE", "TUBE"]):
        commodity = "TUBES"
        received_lines = ["TUBES.", "TUBES Damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"

    elif "BEAMS" in raw_commodity:
        commodity = "Bundles of BEAMS"
        received_lines = ["Bundles of BEAMS.",
                          "Bundles of BEAMS Found Dismembered on board"]
        total_rec_str = f"{rec_str}  {commodity}"

    elif any(x in raw_commodity for x in ["FILE MACHINE", "FIL"]):
        commodity = "FIL MACHINE"
        received_lines = ["RLX FOUND DISMEMBERED ON BOARD"]
        total_rec_str = f"{rec_str}  {commodity}"

    elif "COIL" in raw_commodity or "BOB" in raw_commodity:
        commodity = "Coils"
        received_lines = ["Coils Found Rusty on board",
                          "Coils Packaging damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"

    elif any(wood in raw_commodity for wood in ["WHITE WOOD", "BEECH WOOD", "RED WOOD"]):
        commodity = "Bundles"
        received_lines = [
            f"Bundles of {raw_commodity} Found Dismembered on board",
            f"Bundles of {raw_commodity} wet on board (Packing and/or Contents)",
            f"Bundles of {raw_commodity} moldy on board (Packing and/or Contents)",
        ]
        total_rec_str = f"{rec_str}  Bundles of {raw_commodity}"
   
    elif "COLI" in raw_commodity and "PACKAGE" in raw_commodity:
        commodity = "Units + Package"
        received_lines = [commodity, f"{commodity} Damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"
    elif "COLI" in raw_commodity :
        commodity = "Units"
        received_lines = [commodity, f"{commodity} Damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"
    # elif not raw_commodity:
    #     commodity = "Units + Package"
    #     received_lines = ["Packaging damaged on board"]
    #     total_rec_str = f"{rec_str}  {commodity}"
    else:
        commodity = raw_commodity if raw_commodity else "General Cargo"
        received_lines = ["Packaging damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


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
    # row2_cell.merge(table.rows[2].cells[1])  # if you want to merge later

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
    # row3[0].merge(row3[1])
    p4 = row3[0].paragraphs[0]
    p4.add_run("Total Received: ").bold = True
    p4.add_run(f" {total_rec_str}")
    p4.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Row 4: Final line
    row4 = table.rows[4].cells
    row4[0].width = Cm(25)
    # row4[0].merge(row4[1])
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
    Take a B/L like 'LDJD4520' and return 'JD520'
    Rule: keep the last 3 digits and the 2 letters immediately before them.
    If pattern is not found, return the original string.
    """
    if bl is None:
        return ""
    s = str(bl).strip()
    m = re.search(r"([A-Za-z]{2}\d{3})$", s)
    return m.group(1) if m else s


def group_sourcefile_by_client(
    input_excel: str,
    sheet_name: int | str = 0,
    skip_unknown_commodities: bool = False,
) -> pd.DataFrame:
    df = pd.read_excel(input_excel, sheet_name=sheet_name, engine="openpyxl")

    # --- Skip rows with unknown / unwanted TYPE before grouping ---
    if skip_unknown_commodities and COL_TYPE in df.columns:
        df = df[
            df[COL_TYPE].isin(COMMODITY_TYPES) &  # only known types
            (df[COL_TYPE] != "OTHERS")           # but not "OTHERS"
        ]

    allowed_types = {"COIL", "UNITS", "PACKAGES", "OTHERS"}
    # Ensure numeric
    for col in [COL_QUANTITE, COL_TONAGE]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Short B/L into the same column
    if COL_BL in df.columns:
        df[COL_BL] = df[COL_BL].apply(_shorten_bl_code)

    # Base aggregation
    agg_dict = {
        COL_QUANTITE: "sum",
        COL_TONAGE: "sum",
        COL_BL: lambda s: ",".join([x for x in s if isinstance(x, str) and x]),
    }

    # For all other columns, keep first non-null value
    # Fix: Use a helper function to avoid closure issues
    def first_non_null(series):
        return next((x for x in series if pd.notna(x)), None)
    
    for col in COLUMNS:
        if col in [COL_CLIENT, COL_QUANTITE, COL_TONAGE, COL_BL]:
            continue
        if col in df.columns:
            # Special handling for COL_TYPE: join only specific commodity types
            if col == COL_TYPE:
                agg_dict[col] = lambda s: ",".join([x for x in s.unique() if pd.notna(x) and x in allowed_types])
            else:
                agg_dict[col] = first_non_null

    grouped = df.groupby(COL_CLIENT, as_index=False).agg(agg_dict)
    return grouped
