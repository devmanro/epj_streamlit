import streamlit as st
import pandas as pd
import os
from tools.tools import getDB 
from assets.constants.constants import DB_PATH

def render_global_manager():
    st.subheader("🌍 Global Loading Dashboard")
    
    df= getDB()
    
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
    
    # Reset index after all filters are applied
    filtered_df = filtered_df.reset_index(drop=True)
    
    st.divider()

    # 4. Display the Filtered Table
    # Users can also use the built-in magnifying glass icon on the table to search
    st.write(f"Showing {len(filtered_df)} of {len(df)} records")
    
    # edited_df = st.data_editor(
    #     filtered_df,
    #     width='stretch',
    #     num_rows="dynamic",
    #     key="global_db_editor"
    # )
    edited_df = st.data_editor(
            filtered_df,
            width='stretch',
            num_rows="dynamic",
            key="global_db_editor",
            hide_index=True,
             column_config={
                # "_index": st.column_config.CheckboxColumn("Row"),
                "NAVIRE": st.column_config.TextColumn("🚢 Navire", width="small"),
                # "DATE": st.column_config.DateColumn("📄 DATE", width="medium"),
                "B/L": st.column_config.TextColumn("📄 B/L", width="medium"),
                "DESIGNATION": st.column_config.TextColumn("📦 Désignation", width="large"),
                "QUANTITE": st.column_config.NumberColumn("🔢 Quantité", format="%d", width="small"),
                "TONAGE": st.column_config.NumberColumn("⚖️ Tonnage", format="%.2f T", width="small"),
                "CLIENT": st.column_config.TextColumn("👤 Client", width="medium"),
                "CHASSIS/SERIAL": st.column_config.TextColumn("🔧 Chassis/Serial", width="medium"),
                # "RESTE T/P": st.column_config.NumberColumn("📊 Reste T/P", format="%.2f", width="small"),
                # "TYPE": st.column_config.TextColumn("📋 Type",  width="medium"),
                # "SITUATION": st.column_config.TextColumn("🚦 Situation", width="medium"),
                # "CLES": st.column_config.NumberColumn("🔑 Clés",width="small"),
                # "SURFACE": st.column_config.NumberColumn("📐 Surface", format="%.2f m²", width="small"),
            },
        )

    # 5. Save/Export Logic
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 Save Global Changes to Database"):
            try:
                # This saves the edited table back to your constant DB_PATH
                edited_df.to_excel(DB_PATH, index=False)
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