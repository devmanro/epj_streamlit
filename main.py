import streamlit as st
import pandas as pd
import os
from modules.processor import calculate_daily_totals
# Import your specific scripts
#from modules.genBorderaux import generate_borderau
#from modules.gendeb import run_debarquement
#from modules.genPvs import generate_pv

st.set_page_config(page_title="Djendjen Logistics Portal", layout="wide")

# --- CSS for styling ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- Sidebar Navigation ---
st.sidebar.title("🚢 Port Operations")
menu = ["Dashboard", "File Manager", "Port Map", "Workforce Tracking", "Logistics Tools", "Templates"]
choice = st.sidebar.radio("Navigation", menu)

# --- Helper: File Management Logic ---
UPLOAD_DIR = "data/uploads/"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# ---------------------------------------------------------
# 1 & 5. FILE MANAGER & GLOBAL DATABASE
# ---------------------------------------------------------
if choice == "File Manager":
    st.header("📂 Data Management Center")
    
    # Upload new files
    uploaded_file = st.file_uploader("Upload XLS/CSV Ship Data", type=["xlsx", "csv"])
    if uploaded_file:
        with open(os.path.join(UPLOAD_DIR, uploaded_file.name), "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Saved {uploaded_file.name}")

    # List and Select Files
    files = os.listdir(UPLOAD_DIR)
    if files:
        selected_file = st.selectbox("Select a ship file to operate on:", files)
        file_path = os.path.join(UPLOAD_DIR, selected_file)
        
        # Load Data
        df = pd.read_excel(file_path) if selected_file.endswith('.xlsx') else pd.read_csv(file_path)
        
        # CRUD Operations
        st.subheader(f"Editing: {selected_file}")
        edited_df = st.data_editor(df, num_rows="dynamic", key="editor")
        
        col1, col2, col3, col4 = st.columns(4)
        if col1.button("💾 Save Changes"):
            edited_df.to_excel(file_path, index=False)
            st.toast("File Updated!")
            
        # 2, 3, 4. Operations on Selected File
        if col2.button("📋 Gen. Debarquement"):
            # Call your gendeb.py logic here
            #result = run_debarquement(edited_df)
            st.info("Debarquement Table Generated")
            
        if col3.button("📜 Gen. Borderaux"):
            #generate_borderau(edited_df)
            st.info("Gen. Borderaux")
            
        if col4.button("📝 Gen. Daily PVs"):
            #generate_pv(edited_df)
            st.info("Gen. Daily PVs")

# ---------------------------------------------------------
# 6. PORT MAP MODULE (Interactive Overlay)
# ---------------------------------------------------------
elif choice == "Port Map":
    st.header("📍 Port Djendjen Interactive Map")
    # This uses a scatter plot over your image to simulate "positions"
    import plotly.express as px
    from PIL import Image
    
    img = Image.open("assets/port_map.png")
    
    # Placeholder data for ship positions (You would store this in a JSON/CSV)
    map_data = pd.DataFrame({
        'x': [100, 250, 400],
        'y': [200, 150, 300],
        'Ship': ['Ship A', 'Ship B', 'Ship C'],
        'Client': ['CMA CGM', 'MSC', 'Maersk'],
        'Type': ['Containers', 'General Cargo', 'Bulk']
    })

    fig = px.scatter(map_data, x='x', y='y', text='Ship', color='Client', 
                     hover_data=['Type'])
    fig.update_layout(images=[dict(source=img, xref="x", yref="y", x=0, y=500, 
                                   sizex=1000, sizey=500, sizing="stretch", layer="below")])
    fig.update_xaxes(showgrid=False, range=[0, 1000])
    fig.update_yaxes(showgrid=False, range=[0, 500])
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.write("### Manage Positions")
    # Add form here to update x, y coordinates for specific ships

# ---------------------------------------------------------
# 8. LOGISTICS TOOLS
# ---------------------------------------------------------
elif choice == "Logistics Tools":
    st.header("🧮 Calculation Tools")
    with st.expander("Surface Area Calculator"):
        type_good = st.selectbox("Type of Good", ["Bulk", "Containers", "Steel Pipes"])
        qty = st.number_input("Quantity/Weight", min_value=1)
        # Add your math logic here
        surface = qty * 1.5 # Example multiplier
        st.success(f"Estimated Surface Needed: {surface} m²")

# ---------------------------------------------------------
# 9. WORKFORCE TRACKING
# ---------------------------------------------------------
elif choice == "Workforce Tracking":
    st.header("👷 Shift & Tally Follow-up")
    work_df = pd.read_excel("data/workforce.xlsx")
    edited_work = st.data_editor(work_df, num_rows="dynamic")
    if st.button("Update Shift Logs"):
        edited_work.to_excel("data/workforce.xlsx", index=False)