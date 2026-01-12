import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
  
 

  

def staff_m():
  
    # --- Configuration ---
    master_path = "data/workforce.xlsx"
    required_cols = ["Mat", "Nom", "Fonction", "Affectation", "Navire", "Marchandise", "Shift", "Date"]

    # --- 1. Load Master & Initialize Session State ---
    if "workforce_data" not in st.session_state:
        if os.path.exists(master_path):
            st.session_state["workforce_data"] = pd.read_excel(master_path)
        else:
            st.session_state["workforce_data"] = pd.DataFrame(columns=required_cols)

    # Ensure Date column is datetime
    st.session_state["workforce_data"]["Date"] = pd.to_datetime(st.session_state["workforce_data"]["Date"]).dt.date

    if "file_processed" not in st.session_state:
        st.session_state["file_processed"] = False

    st.header("👷 Shift & Tally Follow-up")

    # --- 2. Sidebar Filters ---
    st.sidebar.header("🔍 Filter Records")
    df = st.session_state["workforce_data"]

    # Calendar Filter
    date_range = st.sidebar.date_input("Select Date Range", [])
    # Shift Filter
    unique_shifts = df["Shift"].unique().tolist()
    selected_shifts = st.sidebar.multiselect("Filter by Shift", unique_shifts, default=unique_shifts)
    # Ship Filter
    unique_ships = df["Navire"].unique().tolist()
    selected_ships = st.sidebar.multiselect("Filter by Ship", unique_ships, default=unique_ships)

    # Apply Filters
    filtered_df = df[df["Shift"].isin(selected_shifts) & df["Navire"].isin(selected_ships)]
    if len(date_range) == 2:
        filtered_df = filtered_df[(filtered_df["Date"] >= date_range[0]) & (filtered_df["Date"] <= date_range[1])]

    # --- 3. Feature: Insert New Shift (Empty Template) ---
    st.subheader("Shift Management")
    if st.button("➕ Prepare New Shift (Reuse Staff List)"):
        # Get unique staff to keep (Mat, Nom, Fonction)
        if not df.empty:
            new_shift_template = df[["Mat", "Nom", "Fonction"]].drop_duplicates()
            # Add empty columns for the rest
            for col in ["Affectation", "Navire", "Marchandise", "Shift", "Date"]:
                new_shift_template[col] = None
            
            st.session_state["workforce_data"] = pd.concat([df, new_shift_template], ignore_index=True)
            st.success("New shift rows added at the bottom. Fill in the Ship and Date in the table below.")
            st.rerun()

    # --- 4. Upload Logic ---
    uploaded_shift = st.file_uploader("Upload new shift Excel file", type=["xlsx"], key="sh_up")
    if uploaded_shift is None:
        st.session_state["file_processed"] = False

    if uploaded_shift and not st.session_state["file_processed"]:
        new_data = pd.read_excel(uploaded_shift)
        # ... (Your existing normalization and merge logic here) ...
        st.session_state["file_processed"] = True
        st.rerun()

    # --- 5. Display & Save ---
    st.divider()
    st.write(f"### Master Workforce Log ({len(filtered_df)} rows visible)")

    edited_work = st.data_editor(
        filtered_df,
        num_rows="dynamic",
        key="editor_workforce",
        use_container_width=True
    )

    # Update master if edited
    if st.button("💾 Save Changes to Master"):
        # Merge edited view back to master logic
        st.session_state["workforce_data"].update(edited_work)
        st.session_state["workforce_data"].to_excel(master_path, index=False)
        st.success("Changes saved to disk!")

    # --- 6. Export Features ---
    st.subheader("📤 Export & Print")
    col1, col2 = st.columns(2)

    # Excel Export
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        filtered_df.to_excel(writer, index=False, sheet_name='ShiftReport')
        
    col1.download_button(
        label="📥 Download Excel (Printable)",
        data=buffer.getvalue(),
        file_name=f"djendjen_shift_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.ms-excel"
    )

    col2.info("💡 To print: Download the Excel file above and press Ctrl+P.")