import streamlit as st
import pandas as pd
import os
import time
import traceback
import tempfile
from pathlib import Path

from tools.tools import ensure_directories

from assets.constants.constants import UPLOAD_DIR, DB_PATH, PATH_DEBRQ, UPLOAD_DIR
from modules.utilities import utilities
from modules.staff_manager import staff_m

from modules.Dashboard import dashboard
from modules.landingManager import render_global_manager
from modules.shipManager import render_single_file_manager
from modules.portMap import show_map

from modules.M_tracker import manifest_tracker
from modules.get_recap import (
    detect_horizontal_tables,
    export_range_as_image,
)

import openpyxl

# --- CSS for styling ---
st.markdown(
    """
    <style>
    .main { background-color: #f9f7f9; }
    .stButton>button { width: 100%; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar Navigation ---
st.sidebar.title("🚢 Port Operations")
menu = [
    "Dashboard",
    "Manifest Tracker",
    "State Manager",
    "Port Map",
    "Workforce Tracking",
    "Logistics Tools",
    "Templates",
    "Send_Recaps",
]
choice = st.sidebar.radio("Navigation", menu, index=0)

if "active_download" not in st.session_state:
    st.session_state.active_download = None


def clear_downloads():
    st.session_state.active_download = None


# ---------------------------------------------------------
# 0. DASHBOARD
# ---------------------------------------------------------
if choice == "Dashboard":
    ensure_directories()
    dashboard()

# ---------------------------------------------------------
# MANIFEST TRACKER
# ---------------------------------------------------------
if choice == "Manifest Tracker":
    manifest_tracker(UPLOAD_DIR)

# ---------------------------------------------------------
# 1 & 5. FILE MANAGER & GLOBAL DATABASE
# ---------------------------------------------------------
if choice == "State Manager":
    st.header("⚓ State Manager")

    if "active_download" not in st.session_state:
        st.session_state.active_download = None

    tab1, tab2 = st.tabs(["🌍 Global Loading Manager", "📂 Single File Manager"])

    with tab1:
        render_global_manager()

    with tab2:
        render_single_file_manager(clear_downloads)


# ---------------------------------------------------------
# 6. PORT MAP MODULE (Interactive Overlay)
# ---------------------------------------------------------
elif choice == "Port Map":
    st.header("📍 Port Djendjen Interactive Map")
    show_map()
    st.write("### Manage Positions")

# ---------------------------------------------------------
# 8. LOGISTICS TOOLS
# ---------------------------------------------------------
elif choice == "Logistics Tools":
    st.header("🧮 Calculateur de Surfaces Portuaires 🚢")
    utilities(st)

# ---------------------------------------------------------
# 9. WORKFORCE TRACKING
# ---------------------------------------------------------
elif choice == "Workforce Tracking":
    staff_m()

# ---------------------------------------------------------
# 10. SEND RECAPS
# ---------------------------------------------------------
elif choice == "Send_Recaps":
    st.header("📤 Send Recaps — Export Tables as Images")

    uploaded_files = st.file_uploader(
        "Select Excel Files",
        type=["xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
    )
    col_limit = st.number_input(
        "Last Table Column Limit", value=6, min_value=1,
        help="For the last detected table, how many rightmost columns to include."
    )

    if st.button("🚀 Start Processing", use_container_width=True):
        if not uploaded_files:
            st.error("Please select at least one file.")
        else:
            st.session_state.processing = True
            st.session_state.recap_results = []

    if st.session_state.get("processing"):
        status_text = st.empty()
        progress_bar = st.progress(0)

        results = []

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "output"
            output_dir.mkdir()

            for idx, uploaded_file in enumerate(uploaded_files):
                workbook_name = Path(uploaded_file.name).stem
                status_text.text(f"Processing: {workbook_name}…")

                temp_file_path = Path(temp_dir) / uploaded_file.name
                temp_file_path.write_bytes(uploaded_file.getbuffer())

                try:
                    wb = openpyxl.load_workbook(
                        str(temp_file_path), data_only=True, read_only=False
                    )
                    ws = wb.worksheets[0]
                    tables = detect_horizontal_tables(ws)

                    if not tables:
                        st.warning(f"No tables found in **{uploaded_file.name}**")
                    else:
                        last_table_idx = len(tables) - 1
                        for i, (start_col, end_col, start_row, end_row) in enumerate(tables):
                            if i == last_table_idx:
                                total_cols = end_col - start_col + 1
                                cols_to_take = min(int(col_limit), total_cols)
                                eff_start_col = end_col - cols_to_take + 1
                            else:
                                eff_start_col = start_col

                            out_name = f"{workbook_name}__{ws.title}__table{i + 1}.png"
                            out_path = str(output_dir / out_name)

                            export_range_as_image(
                                ws, eff_start_col, end_col, start_row, end_row, out_path
                            )
                            results.append((out_name, out_path))

                    wb.close()

                except Exception as e:
                    st.error(f"Error processing **{uploaded_file.name}**: {e}")
                    st.text(traceback.format_exc())

                progress_bar.progress((idx + 1) / len(uploaded_files))

            status_text.text("Done!")
            st.session_state.processing = False

            if results:
                st.success(f"✅ Generated {len(results)} image(s). Download below:")
                for name, path in results:
                    with open(path, "rb") as img_f:
                        st.download_button(
                            label=f"⬇️ {name}",
                            data=img_f.read(),
                            file_name=name,
                            mime="image/png",
                            use_container_width=True,
                        )
