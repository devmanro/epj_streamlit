import streamlit as st
import pandas as pd
import os
from modules.processor import calculate_daily_totals
import time
# Import your specific scripts
from modules.genBorderaux import generate_brd
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
            generate_brd(edited_df)
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
    
    img = Image.open("assets/map/port_map.png")
    
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
    master_path = "data/workforce.xlsx"

    # --- 1. Load Master & Initialize Session State ---
    if "workforce_data" not in st.session_state:
        if os.path.exists(master_path):
            st.session_state["workforce_data"] = pd.read_excel(master_path)
        else:
            st.session_state["workforce_data"] = pd.DataFrame(
                columns=["Mat", "Nom", "Fonction", "Affectation", "Navire", "Marchandise", "Shift", "Date"]
            )

    # Initialize the "Lock" flag
    if "file_processed" not in st.session_state:
        st.session_state["file_processed"] = False

    # --- 2. Upload Logic ---
    st.subheader("Import Shift Sheet")
    uploaded_shift = st.file_uploader("Upload new shift Excel file", type=["xlsx"], key="sh_up")

    # RESET LOCK: If user clears the file, reset the flag so they can upload again later
    if uploaded_shift is None:
        st.session_state["file_processed"] = False

    # PROCESS FILE: Run only if file exists AND hasn't been processed yet
    if uploaded_shift and not st.session_state["file_processed"]:
        new_data = pd.read_excel(uploaded_shift)

        # A. Normalize Headers
        map_new = {col.lower().strip(): col for col in new_data.columns}
        required_cols = ["date", "mat", "shift"]
        
        if all(req in map_new for req in required_cols):
            # Get Master Header Map
            map_master = {col.lower().strip(): col for col in st.session_state["workforce_data"].columns}
            
            # B. Rename New Data Headers to match Master
            rename_map = {orig: map_master[low] for low, orig in map_new.items() if low in map_master}
            new_data = new_data.rename(columns=rename_map)

            # C. Identify Column Names
            col_date = map_master['date']
            col_mat = map_master['mat']
            col_shift = map_master['shift']

            # --- CRITICAL FIX: Standardize Data BEFORE Key Gen ---
            # 1. Ensure Dates are actual Python Date Objects for the View
            # coerce_errors=True handles typos in dates
            new_data[col_date] = pd.to_datetime(new_data[col_date], errors='coerce').dt.date
            st.session_state["workforce_data"][col_date] = pd.to_datetime(st.session_state["workforce_data"][col_date], errors='coerce').dt.date

            # 2. Generate Key using STRING FORMATTING (Removes Time issues)
            # We force the date to YYYY-MM-DD string format for the ID key
            for df_obj in [st.session_state["workforce_data"], new_data]:
                df_obj['match_key'] = (
                    pd.to_datetime(df_obj[col_date]).dt.strftime('%Y-%m-%d') + "_" +
                    df_obj[col_mat].astype(str).str.lower().str.strip() + "_" +
                    df_obj[col_shift].astype(str).str.lower().str.strip()
                )

            # D. Merge and Deduplicate
            combined_df = pd.concat([st.session_state["workforce_data"], new_data], ignore_index=True)
            
            # Keep='last' ensures new data overwrites old data
            updated_df = combined_df.drop_duplicates(subset=['match_key'], keep='last').drop(columns=['match_key'])

            # E. Update State & Lock
            st.session_state["workforce_data"] = updated_df
            st.session_state["file_processed"] = True

            # F. Success Message
            msg = st.empty()
            msg.success("✅ Table merged! Old records updated with new data.")
            import time
            time.sleep(2) # Short pause
            msg.empty()
            st.rerun()

        else:
            missing = [r for r in required_cols if r not in map_new]
            st.error(f"Missing columns: {missing}")

    # --- 3. Display & Save ---
    st.divider()
    st.write("### Master Workforce Log")
    
    # Data Editor (Now shows clean dates because we converted them to .dt.date above)
    edited_work = st.data_editor(
        st.session_state["workforce_data"], 
        num_rows="dynamic",
        key="editor_workforce",
        use_container_width=True
    )

    if st.button("💾 Save Manual Changes to Excel"):
        # Save to disk
        edited_work.to_excel(master_path, index=False)
        st.toast("Master database saved successfully!")