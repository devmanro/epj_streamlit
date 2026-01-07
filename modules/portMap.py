import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import os

# === CONFIGURATION ===
MAP_IMAGE_PATH = "assets/map/port_map.png"
CANVAS_WIDTH = 900
CANVAS_HEIGHT = 500

def get_icon(item_type):
    mapping = {
        'Container Ship': '🚢', 'Bulk Carrier': '🛳️', 'Tanker': '⛽',
        'Plywood': '🪵', 'Coil': '⚫', 'Beams': '🏗️', 'Utilities': '🔧', 'Grain': '🌾'
    }
    return mapping.get(item_type, '📦')

def show_map():
    st.set_page_config(layout="wide", page_title="Port Logic System")
    
    # --- 1. Session State Initialization ---
    if 'port_data' not in st.session_state:
        st.session_state['port_data'] = pd.DataFrame([
            {'id': 1, 'x': 150, 'y': 200, 'client': 'CMA CGM', 'type': 'Container Ship', 'qty': '1000 TEU', 'size': 'Large'},
            {'id': 2, 'x': 400, 'y': 350, 'client': 'MSC', 'type': 'Plywood', 'qty': '500 pallets', 'size': '200m2'},
        ])

    if 'temp_item_details' not in st.session_state:
        st.session_state['temp_item_details'] = {'client': 'CMA CGM', 'type': 'Container Ship', 'qty': '100', 'size': 'Std'}

    # --- 2. Image Loading ---
    bg_image = None
    if os.path.exists(MAP_IMAGE_PATH):
        try:
            raw_img = Image.open(MAP_IMAGE_PATH).convert("RGB")
            bg_image = raw_img.resize((CANVAS_WIDTH, CANVAS_HEIGHT))
        except Exception as e:
            st.error(f"Error loading image: {e}")
    
    st.title("⚓ Port Operations Map")
    st.markdown("---")

    # --- 3. Layout: Map (Left) vs Controls (Right) ---
    col_map, col_controls = st.columns([3, 1], gap="medium")

    # --- RIGHT COLUMN: CONTROLS & MODE SWITCH ---
    with col_controls:
        st.subheader("⚙️ Controls")
        
        # 3.1 Mode Switcher
        mode = st.radio(
            "Operation Mode:", 
            ["👁️ View Mode", "✏️ Edit Mode"], 
            horizontal=True,
            help="Switch between viewing the port status and editing/placing items."
        )

        st.divider()

        # 3.2 Form (Only visible in Edit Mode)
        if mode == "✏️ Edit Mode":
            st.info("Define Item Details below, then click on the Map (Left) to place it.")
            with st.form("item_details_form"):
                st.write("**New Item Details**")
                client = st.selectbox("Client", ["CMA CGM", "MSC", "Maersk", "Sonatrach", "Cevital"])
                cat_type = st.selectbox("Item Type", [
                    "Container Ship", "Bulk Carrier", "Tanker",
                    "Plywood", "Coil", "Beams", "Utilities", "Grain"
                ])
                qty = st.text_input("Quantity", "100 units")
                size = st.text_input("Size/Area", "Standard")
                
                # We save these to session state so they are ready when we click the canvas
                if st.form_submit_button("Update Placement Data"):
                    st.session_state['temp_item_details'] = {
                        'client': client, 'type': cat_type, 'qty': qty, 'size': size
                    }
                    st.success("Details updated! Click on map to drop.")
            
            st.markdown("""
            **Tool Tips:**
            - **Point Tool:** Click to add the item defined above.
            - **Transform Tool (Rectangle with dots):** Select and move existing dots.
            - **Trash Can:** Delete the selected dot.
            """)

        else:
            st.success("Currently in Read-Only View Mode.")
            st.metric("Total Items on Port", len(st.session_state['port_data']))

    # --- LEFT COLUMN: MAP AREA ---
    with col_map:
        # === EDIT MODE: CANVAS ===
        if mode == "✏️ Edit Mode":
            st.subheader("✏️ Editor Map")
            # We use a key based on the mode so it resets cleanly
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.8)",  # Orange opaque
                stroke_width=2,
                background_image=bg_image,
                background_color="#eee",
                update_streamlit=True,
                height=CANVAS_HEIGHT,
                width=CANVAS_WIDTH,
                drawing_mode="point", # Default to placing
                display_toolbar=True, # Shows toolbar (Point, Transform, Undo, Clear)
                point_display_radius=8,
                key="canvas_editor",
            )

            # Logic to handle adding points from Canvas
            if canvas_result.json_data is not None:
                objects = canvas_result.json_data["objects"]
                
                # Check if a new object was just added (simple logic: count increased)
                # Note: For robust editing (moving/deleting), we usually sync the whole DF to JSON and back.
                # Here we strictly handle "New Click = New Item" for simplicity based on your prompt.
                if len(objects) > len(st.session_state['port_data']):
                    last_click = objects[-1]
                    details = st.session_state['temp_item_details']
                    
                    # Create new row
                    new_entry = {
                        'id': len(st.session_state['port_data']) + 1,
                        'x': last_click["left"],
                        'y': CANVAS_HEIGHT - last_click["top"], # Invert Y for Plotly
                        'client': details['client'],
                        'type': details['type'],
                        'qty': details['qty'],
                        'size': details['size']
                    }
                    
                    # Update State
                    st.session_state['port_data'] = pd.concat(
                        [st.session_state['port_data'], pd.DataFrame([new_entry])], 
                        ignore_index=True
                    )
                    st.rerun()

        # === VIEW MODE: PLOTLY ===
        else:
            st.subheader("👁️ Live Map View")
            df_viz = st.session_state['port_data'].copy()
            
            if not df_viz.empty:
                df_viz['icon_visual'] = df_viz['type'].apply(get_icon)
                
                fig = px.scatter(
                    df_viz, x='x', y='y', color='client',
                    text='icon_visual',
                    hover_data={'x':False, 'y':False, 'icon_visual':False, 'type':True, 'qty':True, 'size':True},
                )
                
                # Small icons as requested (size 14)
                fig.update_traces(textfont_size=14, marker=dict(opacity=0))
                
                if bg_image:
                    fig.update_layout(
                        images=[dict(
                            source=bg_image, xref="x", yref="y",
                            x=0, y=CANVAS_HEIGHT,
                            sizex=CANVAS_WIDTH, sizey=CANVAS_HEIGHT,
                            sizing="stretch", layer="below"
                        )]
                    )

                fig.update_xaxes(range=[0, CANVAS_WIDTH], showgrid=False, visible=False)
                fig.update_yaxes(range=[0, CANVAS_HEIGHT], showgrid=False, visible=False)
                fig.update_layout(height=CANVAS_HEIGHT, margin=dict(l=0, r=0, b=0, t=10), dragmode="pan")
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Map is empty.")

    # --- 4. DATA TABLE AREA (Below Map) ---
    st.markdown("---")
    
    if mode == "✏️ Edit Mode":
        st.subheader("📝 Edit Manifest Table")
        st.caption("Make changes in the table below, then click 'Save Table Changes' to update the map.")
        
        # Editable Table
        edited_df = st.data_editor(
            st.session_state['port_data'], 
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor_main"
        )
        
        # SAVE BUTTON
        if st.button("💾 Save Table Changes", type="primary"):
            st.session_state['port_data'] = edited_df
            st.success("Map updated with table changes!")
            st.rerun()
            
    else:
        with st.expander("📋 View Manifest Table (Read Only)"):
            st.dataframe(st.session_state['port_data'], use_container_width=True)
