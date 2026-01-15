import streamlit as st
import pandas as pd
import os

def render_global_manager(db_path):
    st.subheader("🌍 Global Loading Dashboard")
    
    # 1. Check if the database file exists
    if not os.path.exists(db_path):
        st.error(f"Database file not found at: {db_path}")
        st.info("Please ensure the master database file exists in the data folder.")
        return

    # 2. Load the Master Data
    try:
        # We read from the single constant path now
        df = pd.read_excel(db_path)
    except Exception as e:
        st.error(f"Error reading database: {e}")
        return

      

    # 3. Dynamic Filtering Section
    st.write("### 🔍 Advanced Filters")
    
    # Create an expandable filter area to save vertical space
    with st.expander("Filter Options (Click to expand)", expanded=False):
        # We create a copy of the dataframe to apply filters to
        filtered_df = df.copy()
        
        # Create columns for the filter widgets
        cols = st.columns(3)
        
        # Logic to automatically create filters for every column
        for i, column in enumerate(df.columns):
            if column == "_select":
                continue
            # Alternate widgets across the 3 columns
            with cols[i % 3]:
                unique_values = df[column].unique().tolist()
                selected_values = st.multiselect(
                    f"Filter {column}",
                    options=unique_values,
                    default=[],
                    key=f"filter_{column}"
                )
                if selected_values:
                    filtered_df = filtered_df[filtered_df[column].isin(selected_values)]

    st.divider()

    # 4. Display the Filtered Table
    # Users can also use the built-in magnifying glass icon on the table to search
    st.write(f"Showing {len(filtered_df)} of {len(df)} records")
    
    # edited_df = st.data_editor(
    #     filtered_df,
    #     use_container_width=True,
    #     num_rows="dynamic",
    #     key="global_db_editor"
    # )
    edited_df = st.data_editor(
            filtered_df,
            use_container_width=True,
            num_rows="dynamic",
            key="global_db_editor",
            column_config={
                "_index": st.column_config.CheckboxColumn("Select")
            },
        )

    # 5. Save/Export Logic
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 Save Global Changes to Database"):
            try:
                # This saves the edited table back to your constant DB_PATH
                edited_df.to_excel(db_path, index=False)
                st.success("Database updated successfully!")
            except Exception as e:
                st.error(f"Save failed: {e}")
                
    with col_b:
        csv = edited_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Current View (CSV)",
            data=csv,
            file_name="filtered_database.csv",
            mime="text/csv"
        )