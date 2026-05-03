import streamlit as st
import os
import time
import logging
import traceback
import io
import zipfile
import tempfile
from pathlib import Path
from typing import List, Tuple
import openpyxl
from openpyxl.utils import get_column_letter
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib import colors as mcolors
import numpy as np

from tools.tools import ensure_directories

from assets.constants.constants import UPLOAD_DIR, DB_PATH, PATH_DEBRQ, UPLOAD_DIR
# Import your specific scripts
# from modules.genBorderaux import generate_brd

# from modules.genPv import generate_daily_pv
from modules.utilities import utilities
from modules.staff_manager import staff_m

from modules.Dashboard import dashboard
from modules.landingManager import render_global_manager
from modules.shipManager import render_single_file_manager
from modules.portMap import show_map  # Import the function

from modules.M_tracker import manifest_tracker
from modules.get_recap import (
    get_excel_files,
    detect_horizontal_tables,
    export_range_as_image,
)

# from modules.genPvs import generate_pv

# st.set_page_config(page_title="Djendjen Logistics Portal", layout="wide")

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
# choice = st.sidebar.radio("Navigation", menu)
choice = st.sidebar.radio("Navigation", menu, index=0)

# # --- Helper: File Management Logic ---
# if not os.path.exists(UPLOAD_DIR):
#     os.makedirs(UPLOAD_DIR)

if "active_download" not in st.session_state:
    # Will store a dict: {"path": ..., "type": ...}
    st.session_state.active_download = None


# Callback to clear state
def clear_downloads():
    st.session_state.active_download = None


# ---------------------------------------------------------
# 0. DASHBOARD
# ---------------------------------------------------------
if choice == "Dashboard":
    # Pass UPLOAD_DIR if your dashboard needs to scan the files for stats
    ensure_directories()
    dashboard()

# Add to your navigation choices
if choice == "Manifest Tracker":
    manifest_tracker(UPLOAD_DIR)

# ---------------------------------------------------------
# 1 & 5. FILE MANAGER & GLOBAL DATABASE
# ---------------------------------------------------------
if choice == "State Manager":
    st.header("⚓ State Manager")

    # Initialize session state for downloads if not exists
    if "active_download" not in st.session_state:
        st.session_state.active_download = None

    # Create the Tabs
    tab1, tab2 = st.tabs(["🌍 Global Loading Manager", "📂 Single File Manager"])

    # TAB 1: Global View (The new feature)
    with tab1:
        # Call the function from Part 1
        # Make sure render_global_manager is defined or imported
        render_global_manager()

    # TAB 2: Single File Manager (The original feature)
    with tab2:
        # Call the function from Part 2
        # We pass your existing helper functions to keep it modular
        render_single_file_manager(clear_downloads)


# ---------------------------------------------------------
# 6. PORT MAP MODULE (Interactive Overlay)
# ---------------------------------------------------------
elif choice == "Port Map":
    st.header("📍 Port Djendjen Interactive Map")
    show_map()  # Call the function

    # # This uses a scatter plot over your image to simulate "positions"
    # import plotly.express as px
    # from PIL import Image

    # img = Image.open("assets/map/port_map.png")

    # # Placeholder data for ship positions (You would store this in a JSON/CSV)
    # map_data = pd.DataFrame({
    #     'x': [100, 250, 400],
    #     'y': [200, 150, 300],
    #     'Ship': ['Ship A', 'Ship B', 'Ship C'],
    #     'Client': ['CMA CGM', 'MSC', 'Maersk'],
    #     'Type': ['Containers', 'General Cargo', 'Bulk']
    # })

    # fig = px.scatter(map_data, x='x', y='y', text='Ship', color='Client',
    #                  hover_data=['Type'])
    # fig.update_layout(images=[dict(source=img, xref="x", yref="y", x=0, y=500,
    #                                sizex=1000, sizey=500, sizing="stretch", layer="below")])
    # fig.update_xaxes(showgrid=False, range=[0, 1000])
    # fig.update_yaxes(showgrid=False, range=[0, 500])

    # st.plotly_chart(fig, width='stretch')

    st.write("### Manage Positions")
    # Add form here to update x, y coordinates for specific ships

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
# 10. Send_Recaps
# ---------------------------------------------------------
elif choice == "Send_Recaps":
    st.header("Send_Recaps")

    uploaded_files = st.file_uploader(
        "Select Excel Files", type=["xlsx", "xlsm", "xls"], accept_multiple_files=True
    )
    output_folder = st.text_input("Output Folder Path", value="/tmp/output")
    col_limit = st.number_input("Last Table Column Limit", value=6, min_value=1)

    if st.button("🚀 Start Processing", use_container_width=True):
        if not uploaded_files:
            st.error("Please select at least one file.")
        else:
            st.session_state.processing = True
            if "zip_buffer" in st.session_state:
                del st.session_state.zip_buffer

    if "processing" in st.session_state and st.session_state.processing:
        status_text = st.empty()
        progress_bar = st.progress(0)
        log_area = st.expander("Show Logs", expanded=True)

        Path(output_folder).mkdir(parents=True, exist_ok=True)

        generated_images: List[str] = []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                for idx, uploaded_file in enumerate(uploaded_files):
                    workbook_name = Path(uploaded_file.name).stem
                    status_text.text(f"Processing: {workbook_name}...")

                    # Save uploaded bytes to temp file
                    temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                    with open(temp_file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    # Open with openpyxl (Linux-compatible)
                    wb = openpyxl.load_workbook(
                        temp_file_path, data_only=True, read_only=False
                    )
                    sheet = wb.worksheets[0]

                    tables = detect_horizontal_tables(sheet)

                    if tables:
                        last_table_idx = len(tables) - 1
                        for i, (start_col, end_col, start_row, end_row) in enumerate(
                            tables, 1
                        ):
                            if i - 1 == last_table_idx:
                                total_cols = end_col - start_col + 1
                                cols_to_take = min(col_limit, total_cols)
                                eff_start_col = end_col - cols_to_take + 1
                            else:
                                eff_start_col = start_col

                            # Pass bounds as tuple instead of win32 range object
                            rng_bounds = (start_row, end_row, eff_start_col, end_col)

                            out_name = f"{workbook_name}__{sheet.title}__table{i}.png"
                            out_path = os.path.join(output_folder, out_name)

                            export_range_as_image(sheet, rng_bounds, out_path)
                            generated_images.append(out_path)
                            log_area.write(f"✅ Saved: {out_name}")

                    wb.close()
                    progress_bar.progress((idx + 1) / len(uploaded_files))

            # Bundle into ZIP (no compression)
            if generated_images:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(
                    zip_buffer,
                    mode="w",
                    compression=zipfile.ZIP_STORED,
                ) as zf:
                    for img_path in generated_images:
                        zf.write(img_path, arcname=Path(img_path).name)
                zip_buffer.seek(0)
                st.session_state.zip_buffer = zip_buffer.getvalue()

            st.success("All workbooks processed successfully!")

        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.text(traceback.format_exc())
        finally:
            st.session_state.processing = False

    # Single download button for all images
    if "zip_buffer" in st.session_state and st.session_state.zip_buffer:
        st.download_button(
            label="⬇️ Download All Images (ZIP)",
            data=st.session_state.zip_buffer,
            file_name="exported_tables.zip",
            mime="application/zip",
            use_container_width=True,
        )
