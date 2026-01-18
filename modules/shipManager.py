import streamlit as st
import pandas as pd
import os
from modules.json_to_excel import extract_to_excel_flattened as gen_excel
from assets.constants.constants import DB_PATH,COLUMNS
from tools.tools import getDB ,align_data ,create_mapping_ui,show_mapping_dialog


# Note: Pass in your helper functions (gen_table, etc) or ensure they are global
def render_single_file_manager(upload_dir, clear_downloads_func, gen_table_func, generate_brd_func,generate_daily_pv):
    st.subheader("📂 Single Ship Operations")
    st.session_state.uploader_key = 0
    # 1. Upload Logic
    uploaded_file = st.file_uploader(
        "Upload XLSX/CSV/JSON Ship Data",
        type=["xlsx", "csv", "json"], # Added json
        on_change=clear_downloads_func,
        key=f"uploader_{st.session_state.uploader_key}"
    )

    # if uploaded_file and not st.session_state.get("final_mapping", False):
    if uploaded_file and not st.session_state.get("mapping_shown", False):
        filename = uploaded_file.name
        # Handle JSON conversion
        if uploaded_file.name.endswith('.json'):
            excel_name = filename.replace('.json', '.xlsx')
            save_path = os.path.join(upload_dir, excel_name)
            # Convert JSON to Excel using your helper
            excel_path = gen_excel(uploaded_file, save_path,st_upload=True)
            st.success(f"JSON converted and saved as: {excel_name}")
        else:
            save_path = os.path.join(upload_dir, filename)
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"Saved {filename}")

        st.session_state.mapping_shown = True
        st.session_state.trigger_mapping = True
        st.session_state.uploader_key = 1
        
    # 2. List and Select Files
    files = os.listdir(upload_dir)
    if files:
        selected_file = st.selectbox(
            "Select a ship file to operate on:",
            files,
            on_change=clear_downloads_func,
            key="file_selector_widget"
        )

        file_path = os.path.join(upload_dir, selected_file)

        # Load Data
        df_raw = pd.read_excel(file_path) if selected_file.endswith('.xlsx') else pd.read_csv(file_path)

        # TRIGGER DIALOG ONLY ON NEW UPLOAD
        if st.session_state.get("trigger_mapping", False):
            show_mapping_dialog(df_raw) 

        # Process data if mapping is confirmed
        # if "final_mapping" in st.session_state:
        if st.session_state.get("final_mapping",False):
            mapping = st.session_state.final_mapping
            
            # # Create aligned dataframe
            # final_df = pd.DataFrame(columns=COLUMNS)
            # for req_col, user_col in mapping.items():
            #     if user_col:
            #         final_df[req_col] = df_raw[user_col]

            df_raw, success=align_data(df_raw, mapping, COLUMNS)

            if success:
                st.success("Data Aligned Successfully!")
            else:
                st.error("Alignment failed. Keeping original data format.")

            # Clean up to prevent repeated processing
            st.session_state.final_mapping = False
            st.session_state.trigger_mapping = False  # Clear the trigger
            # st.rerun()

        # CRUD Operations
        st.write(f"**Editing:** `{selected_file}`")
        # IMPORTANT: Key must be unique from Tab 1
        edited_df = st.data_editor(
            df_raw,
            num_rows="dynamic",
            key="single_file_editor",
            use_container_width=True,
            column_config={
                "_index": st.column_config.CheckboxColumn("Select")
            },
        )

        col1, col2, col3, col4, col5 = st.columns(5)

        # --- SAVE CHANGES ---
        if col1.button("💾 Save Changes", key="btn_save"):
            # 2. Merge with Global DB
            edited_df.to_excel(file_path, index=False)
            st.toast("File Updated!")

            global_db = getDB()
            # Combine current edited data with the master database
            updated_global = pd.concat([global_db, edited_df], ignore_index=True)
            
            # Optional: Remove exact duplicate rows
            updated_global = updated_global.drop_duplicates()
            
            # 3. Save the master database back to DB_PATH
            updated_global.to_excel(DB_PATH, index=False)
            
            st.toast("File and Global Database Updated!")
            clear_downloads_func()

        # --- OPERATION 2 ---
        if col2.button("📋 Gen. Debarquement", key="btn_debarq"):
            generated_path = gen_table_func(file_path)
            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Debarquement (Excel)",
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
            st.info("Debarquement Table Generated")

        # --- OPERATION 3: GENERATE BORDERAUX ---
        if col3.button("📜 Gen. Borderaux", key="btn_brd"):
            # Execute generation logic
            generated_path = generate_brd_func(file_path, sheet_name=0, template_name="template.docx")
            
            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Bordereau (Word)",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
            
            st.success("Bordereau Generated!")

        # --- OPERATION 4 ---
        if col4.button("📝 Gen. Daily PVs", key="btn_pvs"):
            # Execute generation logic
            generated_path = generate_daily_pv(file_path)
            # os.path.basename(generated_path)
            # Set session state for download button
            st.session_state.active_download = {
                "path": generated_path,
                "label": f"📥 Download {os.path.basename(file_path)}",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
            st.success(f"PV Generated in folder: {os.path.basename(file_path)}")
            st.info("Gen. Daily PVs")

        # --- OPERATION 5: DELETE FILE ---
        with col5:
            c1, c2 = st.columns([1,2])
            with c1:
                confirm_delete = st.checkbox("", key="check_del")
            with c2:
                if st.button("🗑️ Delete", key="btn_delete", type="secondary", disabled=not confirm_delete):
                    try:
                        os.remove(file_path)
                        st.toast(f"Deleted {selected_file}")
                        clear_downloads_func()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        # 3. DYNAMIC DOWNLOAD BUTTON
        if "active_download" in st.session_state and st.session_state.active_download:
            st.divider()
            file_info = st.session_state.active_download

            # Check if file exists before trying to open
            if os.path.exists(file_info["path"]):
                with open(file_info["path"], "rb") as f:
                    st.download_button(
                        label=file_info["label"],
                        data=f.read(),
                        file_name=os.path.basename(file_info["path"]),
                        mime=file_info["mime"],
                        type="primary",
                        key="dl_button_dynamic"
                    )
            else:
                st.error("Generated file not found. Please regenerate.")