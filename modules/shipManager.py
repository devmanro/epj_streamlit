import streamlit as st
import pandas as pd
import os
from modules.json_to_excel import extract_to_excel_flattened as gen_excel



# Note: Pass in your helper functions (gen_table, etc) or ensure they are global
def render_single_file_manager(upload_dir, clear_downloads_func, gen_table_func, generate_brd_func, generate_daily_pv):
    st.subheader("📂 Single Ship Operations")
    
    # 1. Upload Logic
    uploaded_file = st.file_uploader(
        "Upload XLSX/CSV/JSON Ship Data",
        type=["xlsx", "csv", "json"],
        on_change=clear_downloads_func,
        key="file_uploader_widget"
    )

    if uploaded_file:
        filename = uploaded_file.name
        if filename.endswith('.json'):
            excel_name = filename.replace('.json', '.xlsx')
            save_path = os.path.join(upload_dir, excel_name)
            # gen_excel is extract_to_excel_flattened
            gen_excel(uploaded_file, save_path, st_upload=True)
            st.success(f"JSON converted and saved as: {excel_name}")
        else:
            save_path = os.path.join(upload_dir, filename)
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"Saved {filename}")

    # 2. List and Select Files
    files = [f for f in os.listdir(upload_dir) if not f.endswith('.json')] # Only show Excel/CSV
    if files:
        selected_file = st.selectbox(
            "Select a ship file to operate on:",
            files,
            on_change=clear_downloads_func,
            key="file_selector_widget"
        )
        file_path = os.path.join(upload_dir, selected_file)

        # Load Data
        df = pd.read_excel(file_path) if selected_file.endswith('.xlsx') else pd.read_csv(file_path)

        # Ensure 'Select' column exists for row selection
        if "Select" not in df.columns:
            df.insert(0, "Select", False)

        # --- NEW: COLUMN MANAGEMENT ---
        with st.expander("🛠️ Column Management (Add/Delete/Rename)"):
            c1, c2 = st.columns(2)
            new_col = c1.text_input("New Column Name")
            if c1.button("➕ Add Column"):
                df[new_col] = ""
                df.to_excel(file_path, index=False) if file_path.endswith('xlsx') else df.to_csv(file_path, index=False)
                st.rerun()

            col_to_del = c2.selectbox("Select Column to Remove", [c for c in df.columns if c != "Select"])
            if c2.button("🗑️ Remove Column"):
                df = df.drop(columns=[col_to_del])
                df.to_excel(file_path, index=False) if file_path.endswith('xlsx') else df.to_csv(file_path, index=False)
                st.rerun()

        # CRUD Operations
        st.write(f"**Editing:** `{selected_file}` (Copy/Paste enabled)")
        
        edited_df = st.data_editor(
            df, 
            num_rows="dynamic", 
            key="single_file_editor",
            use_container_width=True,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select", default=False)
            }
        ) 

        col1, col2, col3, col4, col5 = st.columns(5)

        # --- SAVE CHANGES ---
        if col1.button("💾 Save Changes", key="btn_save"):
            # Save without the internal 'Select' column if desired, or keep it
            edited_df.to_excel(file_path, index=False)
            st.toast("File Updated!")
            clear_downloads_func()

        # --- OPERATION 2: DEBARQUEMENT ---
        if col2.button("📋 Gen. Debarquement", key="btn_debarq"):
            generated_path = gen_table_func(file_path)
            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Debarquement (Excel)",
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }

        # --- OPERATION 3: BORDERAUX ---
        if col3.button("📜 Gen. Borderaux", key="btn_brd"):
            generated_path = generate_brd_func(file_path, sheet_name=0, template_name="template.docx")
            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Bordereau (Word)",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }

        # --- OPERATION 4: PVs ---
        if col4.button("📝 Gen. Daily PVs", key="btn_pvs"):
            generated_path = generate_daily_pv(file_path)
            st.session_state.active_download = {
                "path": generated_path,
                "label": f"📥 Download {os.path.basename(file_path)}",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }

        # --- OPERATION 5: DELETE FILE ---
        with col5:
            confirm_delete = st.checkbox("Confirm", key="check_del")
            if st.button("🗑️ Delete", key="btn_delete", disabled=not confirm_delete):
                os.remove(file_path)
                st.rerun()

        # 3. DYNAMIC DOWNLOAD BUTTON
        if "active_download" in st.session_state and st.session_state.active_download:
            st.divider()
            file_info = st.session_state.active_download
            if os.path.exists(file_info["path"]):
                with open(file_info["path"], "rb") as f:
                    st.download_button(
                        label=file_info["label"],
                        data=f.read(),
                        file_name=os.path.basename(file_info["path"]),
                        mime=file_info["mime"],
                        type="primary"
                    )