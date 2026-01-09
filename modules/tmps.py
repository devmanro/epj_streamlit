 
 
 
 
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
