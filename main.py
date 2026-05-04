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

    uploaded_files = st.file_uploader(
        "Select Excel Files",
        type=["xlsx", "xlsm", "xls"],
        accept_multiple_files=True,
    )
    output_folder = st.text_input("Output Folder Path", value="/tmp/output")
    last_table_tail_cols = st.number_input(
        "Ending columns to capture for last table tail picture",
        value=6,
        min_value=1,
    )

    # ── WhatsApp settings ─────────────────────────────────────────────
    st.divider()
    st.subheader("📱 WhatsApp Settings (Green API)")

    with st.expander("🔑 API Credentials", expanded=False):
        id_instance = st.text_input(
            "ID Instance",
            value=st.session_state.get("wa_id_instance", ""),
            type="default",
            key="wa_id_instance",
        )
        api_token = st.text_input(
            "API Token",
            value=st.session_state.get("wa_api_token", ""),
            type="password",
            key="wa_api_token",
        )
        
        if st.button("🔄 Load My WhatsApp Groups"):
            if id_instance and api_token:
                with st.spinner("Fetching groups..."):
                    groups = get_whatsapp_groups_greenapi(id_instance, api_token)
                st.session_state.wa_groups = groups
                if groups:
                    st.success(f"Found {len(groups)} group(s).")
                else:
                    st.warning("No groups found or invalid credentials.")
            else:
                st.error("Please enter ID Instance and API Token first.")

    # Group selector logic
    send_to_whatsapp = False
    selected_chat_id = None

    if st.session_state.get("wa_groups"):
        groups = st.session_state.wa_groups
        group_options = {g["name"]: g["id"] for g in groups}

        selected_group_name = st.selectbox(
            "Select WhatsApp Group",
            options=list(group_options.keys()),
        )
        selected_chat_id = group_options[selected_group_name]
        st.caption(f"Chat ID: `{selected_chat_id}`")

        send_to_whatsapp = st.checkbox(
            "📤 Send images to this group after processing",
            value=False,
        )
    else:
        manual_chat_id = st.text_input(
            "Or enter Group Chat ID manually",
            placeholder="120363XXXXXXXXXX@g.us",
        )
        if manual_chat_id:
            selected_chat_id = manual_chat_id
            send_to_whatsapp = st.checkbox(
                "📤 Send images to this group after processing",
                value=False,
            )

    st.divider()

    # ── Processing Execution ──────────────────────────────────────────
    if st.button("🚀 Start Processing", use_container_width=True):
        if not uploaded_files:
            st.error("Please select at least one file.")
        elif send_to_whatsapp and not selected_chat_id:
            st.error("Please select or enter a WhatsApp group.")
        elif send_to_whatsapp and (not id_instance or not api_token):
            st.error("Please enter Green API credentials.")
        else:
            st.session_state.processing = True
            st.session_state.do_send_wa = send_to_whatsapp
            st.session_state.wa_chat_id = selected_chat_id
            st.session_state.pop("zip_buffer", None)

    # ── Processing block ─────────────────────────────────────────────
    if st.session_state.get("processing"):
        status_text = st.empty()
        progress_bar = st.progress(0)
        log_area = st.expander("Show Logs", expanded=True)

        Path(output_folder).mkdir(parents=True, exist_ok=True)
        all_images: List[str] = []

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                total = len(uploaded_files)
                for idx, up_file in enumerate(uploaded_files):
                    wb_name = Path(up_file.name).stem
                    status_text.text(f"Processing {idx + 1}/{total}: {wb_name}...")

                    # Save upload to temp file
                    tmp_path = os.path.join(tmp_dir, up_file.name)
                    with open(tmp_path, "wb") as fh:
                        fh.write(up_file.getbuffer())

                    wb = openpyxl.load_workbook(tmp_path, data_only=True)
                    sheet = wb.worksheets[0]

                    imgs = get_recap(
                        sheet=sheet,
                        workbook_name=wb_name,
                        output_folder=output_folder,
                        last_table_tail_cols=int(last_table_tail_cols),
                        log_fn=log_area.write,
                    )
                    all_images.extend(imgs)
                    wb.close()
                    progress_bar.progress((idx + 1) / total)

            # ── ZIP Bundle ────────────────────────────────────────────
            if all_images:
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, mode="w") as zf:
                    for img_path in all_images:
                        zf.write(img_path, arcname=Path(img_path).name)
                st.session_state.zip_buffer = zip_buf.getvalue()
                status_text.text("✅ Done!")
                st.success(f"Processed {total} workbook(s). {len(all_images)} image(s) created.")
            else:
                status_text.text("⚠️ No images were generated.")

            # ── WhatsApp Dispatch ─────────────────────────────────────
            if st.session_state.get("do_send_wa") and all_images:
                st.info(f"📤 Sending {len(all_images)} image(s) to WhatsApp...")
                wa_log = st.expander("WhatsApp Send Logs", expanded=True)
                ok, fail = send_images_to_whatsapp(
                    image_paths=all_images,
                    chat_id=st.session_state.wa_chat_id,
                    id_instance=st.session_state.wa_id_instance,
                    api_token=st.session_state.wa_api_token,
                    log_fn=wa_log.write,
                    delay_seconds=1.5,
                )
                if fail == 0:
                    st.success(f"✅ All {ok} image(s) sent to WhatsApp!")
                else:
                    st.warning(f"Sent: {ok} ✅ | Failed: {fail} ❌ — check logs above.")

        except Exception as exc:
            st.error(f"An error occurred: {exc}")
            st.text(traceback.format_exc())
        finally:
            st.session_state.processing = False

    # ── Persistent download button ────────────────────────────────────
    if st.session_state.get("zip_buffer"):
        st.download_button(
            label="⬇️ Download All Images (ZIP)",
            data=st.session_state.zip_buffer,
            file_name="exported_tables.zip",
            mime="application/zip",
            use_container_width=True,
        )
