import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import os

# === CONFIGURATION ===
MAP_IMAGE_PATH = "assets/map/port_map.png"
CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 500

def get_icon(item_type):
    mapping = {
        'Container Ship': '🚢', 'Bulk Carrier': '🛳️', 'Tanker': '⛽',
        'Plywood': '🪵', 'Coil': '⚫', 'Beams': '🏗️', 'Utilities': '🔧', 'Grain': '🌾'
    }
    return mapping.get(item_type, '📦')

def show_map():
    # --- 1. Session State Initialization ---
    if 'port_data' not in st.session_state:
        st.session_state['port_data'] = pd.DataFrame([
            {'id': 1, 'x': 150, 'y': 200, 'client': 'CMA CGM', 'type': 'Container Ship', 'qty': '1000 TEU', 'size': 'Large'},
            {'id': 2, 'x': 400, 'y': 350, 'client': 'MSC', 'type': 'Plywood', 'qty': '500 pallets', 'size': '200m2'},
        ])

    if 'placement_mode' not in st.session_state:
        st.session_state['placement_mode'] = False

    if 'temp_item_details' not in st.session_state:
        st.session_state['temp_item_details'] = {}

    # --- 2. Sidebar Operations ---
    st.sidebar.markdown("---")
    st.sidebar.header("🏗️ Port Map Controls")

    if not st.session_state['placement_mode']:
        st.sidebar.subheader("1. Define New Item")
        with st.sidebar.form("item_details_form"):
            client = st.selectbox("Client", ["CMA CGM", "MSC", "Maersk", "Sonatrach", "Cevital"])
            cat_type = st.selectbox("Item Type", [
                "Container Ship", "Bulk Carrier", "Tanker",
                "Plywood", "Coil", "Beams", "Utilities", "Grain"
            ])
            qty = st.text_input("Quantity", "100 units")
            size = st.text_input("Size/Area", "Standard")
            submitted_details = st.form_submit_button("Step 2: Click to Place 👉")

            if submitted_details:
                st.session_state['temp_item_details'] = {
                    'client': client, 'type': cat_type, 'qty': qty, 'size': size
                }
                st.session_state['placement_mode'] = True
                st.rerun()
    else:
        st.sidebar.warning("👇 Click on the map to place the item.")
        st.sidebar.write(f"Placing: **{st.session_state['temp_item_details']['type']}**")
        if st.sidebar.button("Cancel Placement"):
            st.session_state['placement_mode'] = False
            st.session_state['temp_item_details'] = {}
            st.rerun()

    # --- 3. Map Logic ---
    bg_image = None
    if os.path.exists(MAP_IMAGE_PATH):
        bg_image = Image.open(MAP_IMAGE_PATH)
    else:
        st.warning("Map image not found. Using blank grid.")

    # --- MODE 1: PLACEMENT MODE ---
    if st.session_state['placement_mode']:
        st.info("Click the exact location on the map to drop the item.")
        
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=2,
            background_image=bg_image,
            background_color="#eee",
            update_streamlit=True,
            height=CANVAS_HEIGHT,
            width=CANVAS_WIDTH,
            drawing_mode="point",
            key="canvas_clicker",
        )

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            if len(objects) > 0:
                last_click = objects[-1]
                details = st.session_state['temp_item_details']

                new_entry = pd.DataFrame([{
                    'id': len(st.session_state['port_data']) + 1,
                    'x': last_click["left"],
                    'y': CANVAS_HEIGHT - last_click["top"], # Invert Y for Plotly compatibility
                    'client': details['client'],
                    'type': details['type'],
                    'qty': details['qty'],
                    'size': details['size']
                }])

                st.session_state['port_data'] = pd.concat(
                    [st.session_state['port_data'], new_entry], ignore_index=True
                )
                st.session_state['placement_mode'] = False
                st.session_state['temp_item_details'] = {}
                st.success("Item placed successfully!")
                st.rerun()

    # --- MODE 2: VIEW MODE ---
    else:
        df_viz = st.session_state['port_data'].copy()

        if not df_viz.empty:
            df_viz['icon_visual'] = df_viz['type'].apply(get_icon)

            fig = px.scatter(
                df_viz, x='x', y='y', color='client',
                text='icon_visual',
                hover_data={'x':False, 'y':False, 'icon_visual':False, 'type':True, 'qty':True, 'size':True},
                title="Real-time Port Status",
            )

            fig.update_traces(textfont_size=24, marker=dict(opacity=0))

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
            fig.update_layout(height=CANVAS_HEIGHT, margin=dict(l=0, r=0, b=0, t=40))

            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("📋 View Manifest Table"):
                st.dataframe(st.session_state['port_data'], use_container_width=True)
        else:
            st.info("Map is empty. Use the sidebar to define an item.")