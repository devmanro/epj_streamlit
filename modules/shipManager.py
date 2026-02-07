import streamlit as st
import pandas as pd
import os
from modules.json_to_excel import extract_to_excel_flattened as gen_excel
from assets.constants.constants import DB_PATH, COLUMNS
from tools.tools import getDB, align_data, create_mapping_ui, show_mapping_dialog
from modules.Bl_tracking import render_tracking_ui
from modules.genDocs import docGeneration
from assets.constants.constants import UPLOAD_DIR,DB_PATH


# Note: Pass in your helper functions (gen_table, etc) or ensure they are global
def render_single_file_manager(clear_downloads_func):

    tab_old, tab_track = st.tabs(
        ["My current view", "Landing / Stock tracking"])

    
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "inserted_file" not in st.session_state:
        st.session_state.inserted_file = None
    if "final_mapping" not in st.session_state:
        st.session_state.final_mapping = {}

    with tab_old:
        st.subheader("📂 Single Ship Operations")
        docGeneration(clear_downloads_func)

    with tab_track:
        st.subheader("📊 Landing / Stock Tracking")
        # You can reuse the same function or create a new one for this tab
        # For now, let's just call the same function to demonstrate
        render_tracking_ui(None, None)
