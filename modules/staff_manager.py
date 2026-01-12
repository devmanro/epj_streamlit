import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
  
  



def staff_m():
    master_path = "data/workforce.xlsx"

    # --- 1. Load Master & Initialize Session State ---
    if "workforce_data" not in st.session_state:
        if os.path.exists(master_path):
            st.session_state["workforce_data"] = pd.read_excel(master_path)
        else:
            st.session_state["workforce_data"] = pd.DataFrame(
                columns=["Mat", "Nom", "Fonction", "Affectation",
                            "Navire", "Marchandise", "Shift", "Date"]
            )

    # Initialize the "Lock" flag
    if "file_processed" not in st.session_state:
        st.session_state["file_processed"] = False

    # --- 2. Upload Logic ---
    st.subheader("Import Shift Sheet")
    uploaded_shift = st.file_uploader(
        "Upload new shift Excel file", type=["xlsx"], key="sh_up")

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
            map_master = {
                col.lower().strip(): col for col in st.session_state["workforce_data"].columns}

            # B. Rename New Data Headers to match Master
            rename_map = {orig: map_master[low] for low,
                            orig in map_new.items() if low in map_master}
            new_data = new_data.rename(columns=rename_map)

            # C. Identify Column Names
            col_date = map_master['date']
            col_mat = map_master['mat']
            col_shift = map_master['shift']

            # --- CRITICAL FIX: Standardize Data BEFORE Key Gen ---
            # 1. Ensure Dates are actual Python Date Objects for the View
            # coerce_errors=True handles typos in dates
            new_data[col_date] = pd.to_datetime(
                new_data[col_date], errors='coerce').dt.date
            st.session_state["workforce_data"][col_date] = pd.to_datetime(
                st.session_state["workforce_data"][col_date], errors='coerce').dt.date

            # 2. Generate Key using STRING FORMATTING (Removes Time issues)
            # We force the date to YYYY-MM-DD string format for the ID key
            for df_obj in [st.session_state["workforce_data"], new_data]:
                df_obj['match_key'] = (
                    pd.to_datetime(df_obj[col_date]).dt.strftime('%Y-%m-%d') + "_" +
                    df_obj[col_mat].astype(str).str.lower().str.strip() + "_" +
                    df_obj[col_shift].astype(str).str.lower().str.strip()
                )

            # D. Merge and Deduplicate
            combined_df = pd.concat(
                [st.session_state["workforce_data"], new_data], ignore_index=True)

            # Keep='last' ensures new data overwrites old data
            updated_df = combined_df.drop_duplicates(
                subset=['match_key'], keep='last').drop(columns=['match_key'])

            # E. Update State & Lock
            st.session_state["workforce_data"] = updated_df
            st.session_state["file_processed"] = True

            # F. Success Message
            msg = st.empty()
            msg.success("✅ Table merged! Old records updated with new data.")
            import time
            time.sleep(2)  # Short pause
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
