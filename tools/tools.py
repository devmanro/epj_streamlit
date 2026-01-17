import streamlit as st
import pandas as pd
import os 
from assets.constants.constants import DB_PATH , COLUMNS


 
def getDB():
    # 1. Check if the database file exists
    dir_name = os.path.dirname(DB_PATH)
    if not os.path.exists(dir_name):
        st.info(f"Database file creation at: {DB_PATH}")
        os.makedirs(dir_name)

    # 2. Create empty Excel file if it doesn't exist
    if not os.path.exists(DB_PATH):
        # Create a basic dataframe with columns
        df_new = pd.DataFrame(columns=COLUMNS) 
        df_new.to_excel(DB_PATH, index=False)
        st.info(f"Created new database at: {DB_PATH}")

    # 2. Load the Master Data
    try:
        # We read from the single constant path now
        df = pd.read_excel(DB_PATH)
        return df
    except Exception as e:
        st.error(f"Error reading database: {e}")
        return NULL





def create_mapping_ui(uploaded_df, required_columns=COLUMNS):
    st.write("### Map Imported Columns to Database Columns")
    mapping = {}
    
    # Create a dropdown for every required column
    for req_col in required_columns:
        mapping[req_col] = st.selectbox(
            f"Select the source for: **{req_col}**",
            options=[None] + list(uploaded_df.columns),
            key=f"map_{req_col}"
        )
    return mapping




def align_data(uploaded_df, mapping, required_columns):
    # 1. Create a new dataframe with the correct headings
    processed_df = pd.DataFrame(columns=required_columns)
    
    for req_col, user_col in mapping.items():
        if user_col:
            # Move data from uploaded column to the required column
            processed_df[req_col] = uploaded_df[user_col]
        else:
            # Fill with empty values if no match was selected
            processed_df[req_col] = None
            
    return processed_df



@st.dialog("Map Your Columns")
def show_mapping_dialog(uploaded_df):
    st.write("Match your file columns to the database headings:")
    
    mapping = {}
    # Define how many mapping boxes you want per row
    COLS_PER_ROW = 3 
    
    # Iterate through COLUMNS in chunks to create rows
    for i in range(0, len(COLUMNS), COLS_PER_ROW):
        row_cols = st.columns(COLS_PER_ROW)
        
        # Get the subset of columns for this specific row
        batch = COLUMNS[i : i + COLS_PER_ROW]
        
        for j, req_col in enumerate(batch):
            with row_cols[j]:
                # Using a container or border for better visual separation
                with st.container(border=True):
                    st.markdown(f"**{req_col}**")
                    mapping[req_col] = st.selectbox(
                        "Source column:",
                        options=[None] + list(uploaded_df.columns),
                        key=f"map_{req_col}",
                        label_visibility="collapsed" # Hide label to save space
                    )

    if st.button("Confirm and Import", type="primary", use_container_width=True):
        st.session_state.final_mapping = mapping

        