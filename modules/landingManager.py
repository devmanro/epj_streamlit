import streamlit as st
import pandas as pd
import os

def render_global_manager(upload_dir):
    st.subheader("🌍 Global Loading Dashboard")
    st.info("View and filter data across all uploaded ship files.")

    # 1. Gather all files
    all_files = [f for f in os.listdir(upload_dir) if f.endswith(('.xlsx', '.csv'))]

    if not all_files:
        st.warning("No ship data found. Please upload files in the 'Single File Manager' tab.")
        return

    # 2. Aggregate Data
    combined_data = []
    
    for filename in all_files:
        file_path = os.path.join(upload_dir, filename)
        try:
            if filename.endswith('.xlsx'):
                df_temp = pd.read_excel(file_path)
            else:
                df_temp = pd.read_csv(file_path)
            
            # Add a column so we know which ship/file this row belongs to
            df_temp.insert(0, "Ship_File_Source", filename)
            combined_data.append(df_temp)
        except Exception as e:
            st.error(f"Error reading {filename}: {e}")

    if combined_data:
        # 3. Create Master DataFrame
        master_df = pd.concat(combined_data, ignore_index=True)

        # 4. Display with Filters (Streamlit data_editor supports built-in filtering)
        # The user can click column headers to filter/sort like Excel
        edited_master = st.data_editor(
            master_df,
            use_container_width=True,
            num_rows="dynamic",
            key="global_data_editor", # Unique key
            disabled=["Ship_File_Source"] # Prevent changing the source filename
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.caption(f"Total Records: {len(master_df)}")
        with col_b:
            # Option to download the aggregated view
            csv = edited_master.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Export Global View to CSV",
                data=csv,
                file_name="global_loading_state.csv",
                mime="text/csv"
            )