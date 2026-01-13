import streamlit as st
import pandas as pd
import os
from datetime import datetime
import io

from assets.constants.constants import FIXED_STAFF_PATH ,WORKFORCE_DB

# --- Configuration ---
# Ensure these global paths are defined in your main app
# WORKFORCE_DB = "data/workforce.xlsx"
# FIXED_STAFF_PATH = "data/staff_template.csv" 
required_cols = ["Mat", "Nom", "Fonction", "Affectation", "Shift", "Date", "Navire", "Marchandise"]

def staff_m():
    st.header("👷 Shift & Tally Management")

    # --- 1. Load Master Database ---
    if "workforce_data" not in st.session_state:
        if os.path.exists(WORKFORCE_DB):
            st.session_state["workforce_data"] = pd.read_excel(WORKFORCE_DB)
            # Ensure Date is object/date format for consistency
            st.session_state["workforce_data"]["Date"] = pd.to_datetime(st.session_state["workforce_data"]["Date"]).dt.date
        else:
            st.session_state["workforce_data"] = pd.DataFrame(columns=required_cols)

    # Initialize staging state for Tab 2
    if "new_shift_stage" not in st.session_state:
        st.session_state["new_shift_stage"] = pd.DataFrame(columns=required_cols)

    # Create Tabs
    tab_history, tab_new = st.tabs(["📜 History & Lookup", "➕ New Shift / Import"])

    # ==========================================
    # TAB 1: HISTORY & LOOKUP
    # ==========================================
    with tab_history:
        st.subheader("Search Past Shifts")
        
        df_history = st.session_state["workforce_data"]
        
        # --- Filters ---
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            search_name = st.text_input("Search by Name/ID", placeholder="e.g. Doe or 1024")
        with col_f2:
            search_ship = st.text_input("Search by Ship/Product", placeholder="e.g. LUNA")
        with col_f3:
            # Handle date filter
            min_date = df_history["Date"].min() if not df_history.empty else datetime.now().date()
            max_date = df_history["Date"].max() if not df_history.empty else datetime.now().date()
            date_filter = st.date_input("Filter by Date Range", [])

        # --- Apply Logic ---
        filtered_df = df_history.copy()
        
        if search_name:
            filtered_df = filtered_df[filtered_df["Nom"].astype(str).str.contains(search_name, case=False, na=False) | 
                                      filtered_df["Mat"].astype(str).str.contains(search_name, case=False, na=False)]
        
        if search_ship:
            filtered_df = filtered_df[filtered_df["Navire"].astype(str).str.contains(search_ship, case=False, na=False) |
                                      filtered_df["Marchandise"].astype(str).str.contains(search_ship, case=False, na=False)]

        if isinstance(date_filter, tuple) and len(date_filter) == 2:
            start_d, end_d = date_filter
            filtered_df = filtered_df[(filtered_df["Date"] >= start_d) & (filtered_df["Date"] <= end_d)]

        st.info(f"Showing {len(filtered_df)} records.")
        
        # View / Light Edit History
        edited_history = st.data_editor(
            filtered_df,
            num_rows="fixed",
            use_container_width=True,
            key="history_editor",
            disabled=["Date", "Shift"] # Lock key columns if desired
        )
        
        # Save corrections to history
        if st.button("💾 Save Corrections to History"):
            # Update the master dataframe with changes made in the filtered view
            # Note: This simple approach works best if indices are preserved or mapped.
            # For robustness, we usually rely on row IDs, but here we update the session state directly.
            st.session_state["workforce_data"].update(edited_history)
            st.session_state["workforce_data"].to_excel(WORKFORCE_DB, index=False)
            st.success("History updated successfully.")

    # ==========================================
    # TAB 2: CREATE / IMPORT NEW SHIFT
    # ==========================================
    with tab_new:
        st.subheader("Prepare & Merge New Data")
        
        col_source, col_act = st.columns([1, 2])
        
        with col_source:
            st.markdown("#### 1. Source")
            source_type = st.radio("Select Source:", ["Generate from Template", "Upload File"])
            
            if source_type == "Generate from Template":
                new_date = st.date_input("Shift Date", datetime.now())
                new_shift = st.selectbox("Shift Type", ["Shift A", "Shift B", "Shift C", "Night"])
                
                if st.button("🚀 Load Template"):
                    try:
                        staff_df = pd.read_csv(FIXED_STAFF_PATH, sep=';')
                        staff_df["Date"] = new_date
                        staff_df["Shift"] = new_shift
                        # Initialize empty columns
                        for col in ["Affectation", "Navire", "Marchandise"]:
                            staff_df[col] = ""
                        st.session_state["new_shift_stage"] = staff_df
                        st.rerun()
                    except FileNotFoundError:
                        st.error(f"Template file not found at {FIXED_STAFF_PATH}")

            elif source_type == "Upload File":
                uploaded_file = st.file_uploader("Upload Excel/CSV", type=["xlsx", "csv"])
                if uploaded_file:
                    if st.button("📥 Process Upload"):
                        if uploaded_file.name.endswith('.csv'):
                            df_up = pd.read_csv(uploaded_file)
                        else:
                            df_up = pd.read_excel(uploaded_file)
                        
                        # Normalize columns if needed
                        st.session_state["new_shift_stage"] = df_up
                        st.rerun()

        with col_act:
            st.markdown("#### 2. Edit & Confirm")
            
            if st.session_state["new_shift_stage"].empty:
                st.warning("No new data loaded yet. Select a source on the left.")
            else:
                # Editable Staging Area
                edited_stage = st.data_editor(
                    st.session_state["new_shift_stage"],
                    num_rows="dynamic",
                    use_container_width=True,
                    key="stage_editor"
                )
                
                # Merge Logic
                col_btn_1, col_btn_2 = st.columns(2)
                with col_btn_1:
                    if st.button("✅ Merge to Master DB", type="primary"):
                        # Append new data to master
                        master = st.session_state["workforce_data"]
                        
                        # Ensure date format consistency before merge
                        if "Date" in edited_stage.columns:
                             edited_stage["Date"] = pd.to_datetime(edited_stage["Date"]).dt.date

                        updated_master = pd.concat([master, edited_stage], ignore_index=True)
                        
                        # Update State and File
                        st.session_state["workforce_data"] = updated_master
                        updated_master.to_excel(WORKFORCE_DB, index=False)
                        
                        # Clear staging
                        st.session_state["new_shift_stage"] = pd.DataFrame(columns=required_cols)
                        st.success("Merged successfully! Check the History tab.")
                        st.rerun()
                
                with col_btn_2:
                    if st.button("🗑️ Clear Staging"):
                        st.session_state["new_shift_stage"] = pd.DataFrame(columns=required_cols)
                        st.rerun()