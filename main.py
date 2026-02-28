import streamlit as st
import pandas as pd
import os
import time

from assets.constants.constants import UPLOAD_DIR,DB_PATH
# Import your specific scripts
# from modules.genBorderaux import generate_brd

# from modules.genPv import generate_daily_pv
from modules.utilities import utilities
from modules.staff_manager import staff_m

from modules.Dashboard import  dashboard
from modules.landingManager import render_global_manager
from modules.shipManager import render_single_file_manager
from modules.portMap import show_map  # Import the function

# from modules.genPvs import generate_pv

# st.set_page_config(page_title="Djendjen Logistics Portal", layout="wide")

# --- CSS for styling ---
st.markdown("""
    <style>
    .main { background-color: #f9f7f9; }
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- Sidebar Navigation ---
st.sidebar.title("🚢 Port Operations")
menu = ["Dashboard", "State Manager", "Port Map",
        "Workforce Tracking", "Logistics Tools", "Templates"]
# choice = st.sidebar.radio("Navigation", menu)
choice = st.sidebar.radio("Navigation", menu, index=1)

# --- Helper: File Management Logic ---
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

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
    # Simply call the function imported from modules.Dashboard
    # Pass UPLOAD_DIR if your dashboard needs to scan the files for stats
    dashboard()
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
        render_single_file_manager(
            clear_downloads
        )
 

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
    st.header("🧮 Calculation Tools")
    utilities(st)
   
# ---------------------------------------------------------
# 9. WORKFORCE TRACKING
# ---------------------------------------------------------
elif choice == "Workforce Tracking":
    
    staff_m()