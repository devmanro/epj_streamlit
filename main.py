import os
import time
import logging
import traceback
import io
import zipfile
import tempfile
import streamlit as st
from pathlib import Path
from typing import List, Tuple
import openpyxl
from openpyxl.utils import get_column_letter
import pandas as pd

import numpy as np

from tools.tools import ensure_directories

from assets.constants.constants import UPLOAD_DIR, DB_PATH, PATH_DEBRQ, UPLOAD_DIR

import concurrent.futures
import threading
import time
import queue

# --- Thread-safe log queue ---
log_queue = queue.Queue()

    # ── Constants ─────────────────────────────────────────────────────────
FILE_TIMEOUT_SECONDS = 30  # seconds before skipping a file
# --- Define this helper OUTSIDE or AT THE TOP of your app script ---
def process_single_file_wrapper(result_dict, tmp_path, wb_name, output_folder, last_table_tail_cols, log_fn):
    import traceback
    try:
        import openpyxl
        wb = openpyxl.load_workbook(tmp_path, data_only=True)
        sheet = wb.worksheets[0]
        imgs = get_recap(
            sheet=sheet,
            workbook_name=wb_name,
            output_folder=output_folder,
            last_table_tail_cols=int(last_table_tail_cols),
            log_fn=threadsafe_log,  # ✅ thread-safe, no Streamlit context needed

        )
        wb.close()
        result_dict["images"] = imgs
        result_dict["success"] = True
    except Exception as e:
        # Capture FULL traceback, not just the message
        result_dict["error"] = traceback.format_exc()
        result_dict["success"] = False


def threadsafe_log(msg: str):
    """Put log messages into queue instead of calling Streamlit directly."""
    log_queue.put(msg)

def drain_log_queue(log_container):
    """Call this from the main thread to flush pending log messages."""
    while not log_queue.empty():
        try:
            msg = log_queue.get_nowait()
            log_container.write(f"  📝 {msg}")
        except queue.Empty:
            break



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
    detect_horizontal_tables,
    export_range_as_image,
    get_used_bounds,
    get_visible_rows,
    get_visible_cols,
    find_last_bordered_table,
    get_recap,
    get_whatsapp_groups_greenapi,
    send_images_to_whatsapp,
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
# Assumes 'choice' is already defined by your sidebar/menu

# ==========================================================
# ========== STREAMLIT UI ==================================
# ==========================================================

elif choice == "Send_Recaps":
    st.header("Send_Recaps")

    # 1. Inputs
    uploaded_files = st.file_uploader("Select Excel Files", type=["xlsx", "xlsm", "xls"], accept_multiple_files=True)
    output_folder = st.text_input("Output Folder Path", value="/tmp/output")
    last_table_tail_cols = st.number_input("Ending columns for last table tail", value=6, min_value=1)
    file_timeout = st.number_input("⏱️ Per-file timeout (seconds)", value=30, min_value=5)

    # 2. WhatsApp Settings (same as your code)
    # ... [Keep your WhatsApp credentials and group selector code here] ...

    st.divider()

    # 3. Control Buttons
    col_start, col_stop = st.columns(2)
    
    # Initialize session states
    if "processing" not in st.session_state:
        st.session_state.processing = False
    if "cancel_requested" not in st.session_state:
        st.session_state.cancel_requested = False

    if col_start.button("🚀 Start Processing", use_container_width=True, disabled=st.session_state.processing):
        st.session_state.processing = True
        st.session_state.cancel_requested = False
        st.session_state.pop("zip_buffer", None)
        st.rerun()

    if col_stop.button("🛑 Stop / Cancel", use_container_width=True, disabled=not st.session_state.processing):
        st.session_state.cancel_requested = True
        st.warning("Stop signal sent. Will stop after current file attempt.")

    if st.session_state.processing:
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        # Use st.container so logs persist and don't get wiped
        log_container = st.container()
        
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        all_images = []
        timed_out_files = []
        failed_files = []

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                total = len(uploaded_files)
                
                if total == 0:
                    st.warning("No files uploaded!")
                    st.session_state.processing = False
                    st.stop()

                for idx, up_file in enumerate(uploaded_files):
                    if st.session_state.cancel_requested:
                        log_container.warning("🛑 Cancelled by user.")
                        break

                    wb_name = Path(up_file.name).stem
                    status_text.text(f"Processing {idx+1}/{total}: {wb_name}...")
                    log_container.write(f"---\n📂 Starting: **{wb_name}**")

                    # Save uploaded file to temp disk
                    tmp_path = os.path.join(tmp_dir, up_file.name)
                    with open(tmp_path, "wb") as f:
                        f.write(up_file.getbuffer())
                    
                    # Verify file was saved correctly
                    file_size = os.path.getsize(tmp_path)
                    log_container.write(f"  💾 Saved to disk: {file_size} bytes at `{tmp_path}`")
                    
                    if file_size == 0:
                        log_container.error(f"  ❌ File is empty after saving! Skipping.")
                        failed_files.append((wb_name, "Empty file after save"))
                        continue

                    # Run in thread with timeout
                    res_dict = {
                        "images": [],
                        "success": False,
                        "error": None
                    }
                    
                    thread = threading.Thread(
                        target=process_single_file_wrapper,
                        args=(
                            res_dict,
                            tmp_path,
                            wb_name,
                            output_folder,
                            last_table_tail_cols,
                            lambda msg: log_container.write(f"  📝 {msg}")  # thread-safe enough for logging
                        ),
                        daemon=True  # Dies if main app dies
                    )
                    
                    start_time = time.time()
                    thread.start()
                    thread.join(timeout=float(file_timeout))
                    elapsed = time.time() - start_time

                    if thread.is_alive():
                        log_container.warning(
                            f"  ⏱️ TIMEOUT after {elapsed:.1f}s (limit: {file_timeout}s) — **{wb_name}** skipped"
                        )
                        timed_out_files.append(wb_name)
                    else:
                        log_container.write(f"  ⏱️ Completed in {elapsed:.1f}s")
                        
                        if res_dict["success"]:
                            imgs = res_dict.get("images", [])
                            log_container.write(f"  ✅ Success — {len(imgs)} image(s) generated")
                            
                            # Verify images actually exist on disk
                            valid_imgs = []
                            for img_path in imgs:
                                if os.path.exists(img_path):
                                    valid_imgs.append(img_path)
                                else:
                                    log_container.warning(f"  ⚠️ Image path not found on disk: `{img_path}`")
                            
                            all_images.extend(valid_imgs)
                        else:
                            error_detail = res_dict.get("error", "Unknown error")
                            log_container.error(f"  ❌ FAILED: {wb_name}")
                            # Show full traceback in expander
                            with log_container.expander(f"🔍 Full error for {wb_name}"):
                                st.code(error_detail, language="python")
                            failed_files.append((wb_name, error_detail))

                    progress_bar.progress((idx + 1) / total)

            # Summary
            st.divider()
            col1, col2, col3 = st.columns(3)
            col1.metric("✅ Images Generated", len(all_images))
            col2.metric("⏱️ Timed Out", len(timed_out_files))
            col3.metric("❌ Failed", len(failed_files))

            if timed_out_files:
                st.warning(f"**Timed out:** {', '.join(timed_out_files)}")
            
            if failed_files:
                st.error("**Failed files:**")
                for fname, err in failed_files:
                    with st.expander(f"❌ {fname}"):
                        st.code(err, language="python")

            if all_images:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for img in all_images:
                        zf.write(img, arcname=Path(img).name)
                st.session_state.zip_buffer = zip_buf.getvalue()
                status_text.text(f"✅ Done! {len(all_images)} images ready.")
            else:
                status_text.text("⚠️ No images generated. Check errors above.")

        except Exception as e:
            import traceback
            st.error(f"**Critical Error:** {e}")
            st.code(traceback.format_exc(), language="python")
        finally:
            st.session_state.processing = False

    # 5. Persistent Download Button
    if st.session_state.get("zip_buffer"):
        st.download_button(
            label="⬇️ Download All Images (ZIP)",
            data=st.session_state.zip_buffer,
            file_name="exported_tables.zip",
            mime="application/zip",
            use_container_width=True,
        )