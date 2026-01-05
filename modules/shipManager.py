import streamlit as st
import pandas as pd
import os

# Note: Pass in your helper functions (gen_table, etc) or ensure they are global
def render_single_file_manager(upload_dir, clear_downloads_func, gen_table_func, generate_brd_func):
    st.subheader("📂 Single Ship Operations")
    
    # 1. Upload Logic
    uploaded_file = st.file_uploader(
        "Upload XLS/CSV Ship Data",
        type=["xlsx", "csv"],
        on_change=clear_downloads_func,
        key="file_uploader_widget"
    )

    if uploaded_file:
        save_path = os.path.join(upload_dir, uploaded_file.name)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Saved {uploaded_file.name}")

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
        df = pd.read_excel(file_path) if selected_file.endswith('.xlsx') else pd.read_csv(file_path)

        # CRUD Operations
        st.write(f"**Editing:** `{selected_file}`")
        # IMPORTANT: Key must be unique from Tab 1
        edited_df = st.data_editor(df, num_rows="dynamic", key="single_file_editor") 

        col1, col2, col3, col4 = st.columns(4)

        # --- SAVE CHANGES ---
        if col1.button("💾 Save Changes", key="btn_save"):
            edited_df.to_excel(file_path, index=False)
            st.toast("File Updated!")
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
            generated_path = generate_brd_func(
                file_path, sheet_name=0, template_name="template.docx")
            
            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Bordereau (Word)",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
            st.success("Bordereau Generated!")

        # --- OPERATION 4 ---
        if col4.button("📝 Gen. Daily PVs", key="btn_pvs"):
            st.info("Gen. Daily PVs")

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