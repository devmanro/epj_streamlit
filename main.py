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
    master_path = "data/workforce.xlsx"

    # Load Master
    if os.path.exists(master_path): 
        work_df = pd.read_excel(master_path)
    else:
        work_df = pd.DataFrame(columns=["Mat","Nom", "Fonction","Affectation","Navire","Marchandise","Shift","Date"]) 

    # --- 1. Upload & Merge Logic ---
    st.subheader("Import Shift Sheet")
    uploaded_shift = st.file_uploader("Upload new shift Excel file", type=["xlsx"])

    if uploaded_shift:
        new_data = pd.read_excel(uploaded_shift)
        
        # Normalize Headers (Ignore Case & Strip whitespace)
        map_new = {col.lower().strip(): col for col in new_data.columns}
        required_cols = ["date", "mat"] # These are strictly needed for the match_key
        
        # Check if required columns exist
        if all(req in map_new for req in required_cols):
            if st.button("Merge & Replace Matching Records"):
                # Map master headers too
                map_master = {col.lower().strip(): col for col in work_df.columns}
                map_new = {col.lower().strip(): col for col in new_data.columns}

                # 3. Create normalized Match Keys
                new_data['match_key'] = (
                    pd.to_datetime(new_data[map_new['date']]).dt.date.astype(str) + 
                    new_data[map_new['mat']].astype(str).str.lower().str.strip()
                )
                
                work_df['match_key'] = (
                    pd.to_datetime(work_df[map_master['date']]).dt.date.astype(str) + 
                    work_df[map_master['mat']].astype(str).str.lower().str.strip()
                )

                # 4. Concatenate and Deduplicate (keep latest)
                combined_df = pd.concat([work_df, new_data], ignore_index=True)
                final_df = combined_df.drop_duplicates(subset=['match_key'], keep='last')
                
                # 5. Cleanup and Save
                final_df = final_df.drop(columns=['match_key'])
                final_df.to_excel(master_path, index=False)
                
                st.success("Successfully normalized and merged records (Date/Mat match).")
                st.rerun()
        else:
            # Show exactly which columns are missing for better debugging
            missing = [r for r in required_cols if r not in map_new]
            st.error(f"Missing columns in uploaded file: {missing}")

    st.divider()
    # ... (Rest of your data_editor code)

    # --- 2. Manual View & Edit ---
    st.subheader("Master Workforce Log")
    edited_work = st.data_editor(work_df, num_rows="dynamic", key="work_editor")
    
    if st.button("Save Manual Changes"):
        edited_work.to_excel(master_path, index=False)
        st.toast("Manual changes saved to database.")