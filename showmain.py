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
#from tools.whatsapp import send_image_to_whatsapp_greenapi ,get_whatsapp_group_metadata_greenapi

from tools.whatsapp import (
    get_whatsapp_chats_greenapi, send_text_to_whatsapp_greenapi,
    send_image_to_whatsapp_greenapi, receive_whatsapp_notification_greenapi,
    delete_whatsapp_notification_greenapi, parse_incoming_notification,
    get_whatsapp_chat_history_greenapi,
    normalize_message,
)

from tools.tools import ensure_directories
from assets.constants.constants import UPLOAD_DIR, DB_PATH, PATH_DEBRQ, UPLOAD_DIR , API_TOKEN, ID_INSTANCE

from modules.send_recap import render_send_recaps_tab
from modules.whatsapp_chat import render_whatsapp_chat_tab

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

from modules.Dashboard import Dashboard
from modules.landingManager import render_global_manager
from modules.shipManager import render_single_file_manager
from modules.portMap import show_map  # Import the function

from modules.Generate_Pages import page_generate_sheets

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
def show_main_app():
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
        "WhatsApp_Chat",
        # "Generate_Sheets",
    ]
    # choice = st.sidebar.radio("Navigation", menu)
    choice = st.sidebar.radio("Navigation", menu, index=2)
    
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
        # Dashboard()
    
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
    elif choice == "Send_Recaps":
        render_send_recaps_tab(ID_INSTANCE,API_TOKEN,st)
    elif choice == "WhatsApp_Chat":
        render_whatsapp_chat_tab(ID_INSTANCE, API_TOKEN, st)
    elif choice == "Generate_Sheets":
        page_generate_sheets()     # ←FOR OMAR SHEETS(RST,CHASSIS,NAVIRE)
