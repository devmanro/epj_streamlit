from pyarrow import null
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
        return null

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

def align_data(uploaded_df, mapping):
    try:
        # st.write("mappe*ing:")
        valid_mappings_count = sum(1 for value in mapping.values() if value is not None)
     
        if valid_mappings_count <= 2 : 
            return uploaded_df, False  # Return original DataFrame if required columns are missing


        # Rename columns based on the mapping
        df_mapped = uploaded_df.rename(columns=mapping)

        final_cols = [value for key, value in mapping.items() if value is not None]

        # Keep only the required columns
        df_aligned = df_mapped[final_cols]
        

        return df_aligned, True
    
    except Exception as e:
        print(f"Error during alignment: {e}")
        return uploaded_df, False

@st.dialog("Map Your Columns", width="large")
def show_mapping_dialog(uploaded_df):
    st.write("Match your file columns to the database headings:")
    # st.info(list(uploaded_df.columns))
    
    mapping = {}
    st.session_state.trigger_mapping = False
    st.session_state.final_mapping = mapping
    # Define how many mapping boxes you want per row
    COLS_PER_ROW = 4
    
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
                    
                    selected_source_column = st.selectbox(
                        "Source column:",
                        options=[None] + list(uploaded_df.columns),
                        key=f"map_{req_col}",
                        label_visibility="collapsed" # Hide label to save space
                    )
                    if selected_source_column: # Only add to mapping if a column was selected
                        mapping[selected_source_column] = req_col
                        

    if st.button("Confirm and Import", type="primary", width='stretch'):
        # 1. Clear the trigger immediately so it doesn't re-open
        st.session_state.final_mapping = mapping
        # st.session_state.mapping_shown = True
        st.session_state.uploaded_file=None
        # Print to the terminal window
     
        # 2. Force a rerun to close the dialog and update the main app
        st.rerun()        