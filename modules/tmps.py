 
 
 
 
  if st.button("💾 Save All Changes (Map & Table)", type="primary"):
                current_data = st.session_state['port_data'].copy()
                new_rows = []
                
                # A. Handle Map Changes
                if canvas_result.json_data is not None:
                    canvas_objects = canvas_result.json_data["objects"]
                    
                    for obj in canvas_objects:
                        # Case 1: Existing object (Look for ID in userData)
                        if "userData" in obj and "id" in obj["userData"]:
                            obj_id = obj["userData"]["id"]
                            original_row = current_data[current_data['id'] == obj_id]
                            if not original_row.empty:
                                updated_row = original_row.iloc[0].to_dict()
                                updated_row['x'] = obj["left"]
                                updated_row['y'] = CANVAS_HEIGHT - obj["top"]
                                new_rows.append(updated_row)
                        
                        # Case 2: New Point added via click
                        elif obj["type"] == "point": 
                            details = st.session_state['temp_item_details']
                            new_rows.append({
                                'id': len(current_data) + len(new_rows) + 100, 
                                'x': obj["left"],
                                'y': CANVAS_HEIGHT - obj["top"],
                                'client': details['client'],
                                'type': details['type'],
                                'qty': details['qty'],
                                'size': details['size']
                            })

                # B. Reconstruct DataFrame (CRITICAL FIX HERE)
                # We enforce columns so the DataFrame never loses its structure
                expected_cols = ['id', 'x', 'y', 'client', 'type', 'qty', 'size']
                
                if new_rows:
                    st.session_state['port_data'] = pd.DataFrame(new_rows)
                    # Ensure all expected columns exist (fills missing with NaN if any)
                    for col in expected_cols:
                        if col not in st.session_state['port_data'].columns:
                            st.session_state['port_data'][col] = ""
                else:
                    # If empty, create an empty DF but KEEP THE COLUMNS
                    st.session_state['port_data'] = pd.DataFrame(columns=expected_cols)

                # Refresh the canvas JSON for the next run
                st.session_state['canvas_initial_json'] = generate_initial_drawing(st.session_state['port_data'])
                st.success("Sync Complete!")
                st.rerun()
-----------------------------



        if st.session_state.mapping_shown:
                # df_raw will be the uploaded dataframe after mapping
                df_raw, success = align_data(df_raw, st.session_state.final_mapping, COLUMNS)
                st.session_state.mapping_shown = False
                
                if success:
                    st.success("Columns mapped and data aligned successfully!")
                    # Reindex df_raw to match COLUMNS for consistent display in st.data_editor
                    df_raw = df_raw.reindex(columns=COLUMNS)
                    st.session_state.df_to_edit = df_raw # Store the aligned df for editing
                else:
                    st.error("Column mapping failed or insufficient columns selected.")

        # Load df_to_edit from session_state if it exists, otherwise initialize empty
        if "df_to_edit" not in st.session_state or st.session_state.df_to_edit.empty:
            if df_raw is None or df_raw.empty:
                st.session_state.df_to_edit = pd.DataFrame(columns=COLUMNS) # Start with an empty DataFrame with default headers
            else:
                st.session_state.df_to_edit = df_raw # Use the uploaded/aligned df

        if not st.session_state.df_to_edit.empty or (df_raw is not None and not df_raw.empty):
            st.write("### Review and Edit Data")
            st.info("Edit cells directly. Add new rows using the '+' button.")
            
            edited_df = st.data_editor(
                st.session_state.df_to_edit, # Use the DataFrame from session_state
                num_rows="dynamic",
                key="single_file_editor",
                width='stretch',
                column_config={
                    "_index": st.column_config.CheckboxColumn("Select")
                },
            )

            # Update df_to_edit in session state with the edited version
            st.session_state.df_to_edit = edited_df

            # Explicit Save Button
            if st.button("Save to Database", type="primary", key="save_to_db_button"):
                # Get the current database
                existing_df = getDB()
                if existing_df is not None:
                    # Append the edited data (after reindexing) to the existing database
                    # Ensure edited_df also has the COLUMNS order and shape
                    df_to_save = edited_df.reindex(columns=COLUMNS)
                    updated_df = pd.concat([existing_df, df_to_save], ignore_index=True)
                    # Save the combined DataFrame back to the Excel file
                    updated_df.to_excel(DB_PATH, index=False)
                    st.success("Data successfully saved to database!")
                    # Clear the df_to_edit from session state to prepare for next upload/edit
                    del st.session_state.df_to_edit
                    st.rerun() # Rerun to refresh the app state
                else:
                    st.error("Could not load existing database to save data.")





                     if st.session_state.brd_generated_path:
            st.divider()
            with open(st.session_state.brd_generated_path, "rb") as f:
                btn = st.download_button(
                    label="📥 Download Generated Word Doc",
                    data=f.read(),
                    file_name=os.path.basename(st.session_state.brd_generated_path),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary" # Makes the button stand out
                )

