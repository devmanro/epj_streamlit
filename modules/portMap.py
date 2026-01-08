import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_drawable_canvas import st_canvas
from PIL import Image
import os
import math
from assets.constants.constants import MAP_IMAGE_PATH

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 500

# === HELPER FUNCTIONS ===
def get_icon(item_type):
    mapping = {
        'Container Ship': '🚢', 'Bulk Carrier': '🛳️', 'Tanker': '⛽',
        'Plywood': '🪵', 'Coil': '⚫', 'Beams': '🏗️', 'Utilities': '🔧', 'Grain': '🌾'
    }
    return mapping.get(item_type, '📦')

def determine_location(x, y):
    """
    Returns (Dock Name, Position Name, Storage Zone)
    """
    try:
        # 1. Determine Dock (Horizontal split)
        if x < CANVAS_WIDTH / 3:
            dock = "QW (West)"
        elif x < (CANVAS_WIDTH / 3) * 2:
            dock = "QMXT (Mixte)"
        else:
            dock = "QE (East)"
        
        # 2. Determine Berth (1-6)
        dock_width = CANVAS_WIDTH / 3
        relative_x = x % dock_width
        berth_num = math.ceil((relative_x / dock_width) * 6)
        berth_num = max(1, min(6, berth_num)) # Clamp between 1-6

        # 3. Determine Storage Zone (Vertical split for Warehouses)
        # Assuming 4 zones from top to bottom
        zone_height = CANVAS_HEIGHT / 4
        zone_num = math.ceil((CANVAS_HEIGHT - y) / zone_height) # Inverted Y logic
        zone = f"Zone-{max(1, min(4, zone_num))}"

        return dock, f"Pos-{berth_num}", zone
    except:
        return "Unknown", "N/A", "N/A"

def generate_initial_drawing(df):
    objects = []
    if df.empty: return {"version": "4.4.0", "objects": []}
    
    for index, row in df.iterrows():
        if pd.isna(row.get('x')) or pd.isna(row.get('y')): continue
        obj = {
            "type": "text", 
            "left": row['x'],
            "top": CANVAS_HEIGHT - row['y'],
            "width": 20, "height": 20, "fill": "black",
            "text": get_icon(row.get('type')),
            "fontSize": 30, "fontFamily": "sans-serif",
            "userData": {"id": row['id']}
        }
        objects.append(obj)
    return {"version": "4.4.0", "objects": objects}

def show_map():
    st.set_page_config(layout="wide", page_title="Port Logic System")
    
    # --- 1. Session State & Data Init ---
    if 'port_data' not in st.session_state:
        st.session_state['port_data'] = pd.DataFrame([
            {'id': 1, 'x': 150, 'y': 200, 'client': 'CMA CGM', 'type': 'Container Ship', 'qty': '1000 TEU', 'size': 'Large'},
            {'id': 2, 'x': 450, 'y': 350, 'client': 'MSC', 'type': 'Plywood', 'qty': '500 pallets', 'size': '200m2'},
        ])
    
    # Ensure tool mode exists
    if 'tool_mode' not in st.session_state:
        st.session_state['tool_mode'] = 'transform' # Default to moving items

    if 'canvas_initial_json' not in st.session_state:
        st.session_state['canvas_initial_json'] = generate_initial_drawing(st.session_state['port_data'])

    # --- 2. Image Loading ---
    bg_image = None
    if os.path.exists(MAP_IMAGE_PATH):
        try:
            raw_img = Image.open(MAP_IMAGE_PATH).convert("RGB")
            bg_image = raw_img.resize((CANVAS_WIDTH, CANVAS_HEIGHT))
        except: st.error("Image not found")

    st.title("⚓ Port Operations Map")
    col_map, col_controls = st.columns([3, 1], gap="medium")

    # === RIGHT COLUMN: CONTROLS ===
    with col_controls:
        st.subheader("⚙️ Controls")
        
        # A. Mode Switcher
        app_mode = st.radio("App Mode:", ["👁️ View Mode", "✏️ Edit Mode"], horizontal=True)
        st.divider()

        if app_mode == "✏️ Edit Mode":
            # B. TOOL SWITCHER (The Fix!)
            # We map friendly names to st_canvas 'drawing_mode' strings
            tool_map = {"✋ Move Items": "transform", "📍 Place New Item": "point"}
            
            selected_tool_friendly = st.radio(
                "Select Tool:", 
                ["✋ Move Items", "📍 Place New Item"],
                horizontal=True,
                key="tool_radio"
            )
            # Update session state for the canvas to read
            st.session_state['tool_mode'] = tool_map[selected_tool_friendly]

            st.divider()

            # C. Item Details Form
            # Only show this if we are in 'Place' mode to reduce clutter
            if st.session_state['tool_mode'] == "point":
                with st.form("add_item_form"):
                    st.markdown("#### 📦 New Item Details")
                    client = st.selectbox("Client", ["CMA CGM", "MSC", "Maersk", "Sonatrach", "Cevital"])
                    cat_type = st.selectbox("Item Type", ["Container Ship", "Bulk Carrier", "Tanker", "Plywood", "Coil", "Beams", "Utilities", "Grain"])
                    qty = st.text_input("Quantity", "100")
                    size = st.text_input("Size", "Std")
                    
                    if st.form_submit_button("Update Next Drop"):
                        st.session_state['temp_item_details'] = {
                            'client': client, 'type': cat_type, 'qty': qty, 'size': size
                        }
                        st.success("Details saved! Click on the map to drop.")
            else:
                st.info("Select 'Place New Item' above to add cargo.")

    # === LEFT COLUMN: MAP & TABLE ===
    with col_map:
        
        # ---------------------------------------------------------
        # MODE: EDIT
        # ---------------------------------------------------------
        if app_mode == "✏️ Edit Mode":
            st.subheader("✏️ Editor Canvas")
            
            # 1. Canvas with Dynamic Drawing Mode
            canvas_result = st_canvas(
                fill_color="rgba(255, 0, 0, 0.5)", # Red dot for new drops
                background_image=bg_image,
                background_color="#eee",
                initial_drawing=st.session_state['canvas_initial_json'],
                update_streamlit=True,
                height=CANVAS_HEIGHT,
                width=CANVAS_WIDTH,
                drawing_mode=st.session_state['tool_mode'], # <--- KEY FIX
                display_toolbar=True,
                key="canvas_editor_main"
            )

            # 2. Data Processing (Add Zone/Dock info)
            display_df = st.session_state['port_data'].copy()
            
            # Ensure safe columns
            for c in ['x', 'y', 'type', 'client', 'id']:
                if c not in display_df.columns: display_df[c] = None

            loc_data = []
            if not display_df.empty:
                display_df['Icon'] = display_df['type'].apply(lambda x: get_icon(x) if x else "📦")
                for _, row in display_df.iterrows():
                    # Calculate Dock, Berth AND Zone
                    res = determine_location(row.get('x',0), row.get('y',0))
                    loc_data.append(res)
            else:
                display_df['Icon'] = []
            
            # Unpack the 3-part location tuple
            display_df['Dock'] = [l[0] for l in loc_data]
            display_df['Berth'] = [l[1] for l in loc_data]
            display_df['Zone'] = [l[2] for l in loc_data]

            # 3. Editable Table
            st.subheader("📝 Edit Data")
            cols_show = ['Icon', 'Dock', 'Berth', 'Zone', 'client', 'type', 'qty', 'size', 'id']
            final_cols = [c for c in cols_show if c in display_df.columns]
            
            edited_df = st.data_editor(
                display_df[final_cols],
                num_rows="dynamic",
                use_container_width=True,
                key="table_editor_v2",
                disabled=['Icon', 'Dock', 'Berth', 'Zone', 'id'],
                hide_index=True
            )

            # 4. SAVE LOGIC
        if st.button("💾 Save All Changes", type="primary"):
        # 1. Map existing IDs to their new positions from the Canvas
            canvas_positions = {}
            new_points_list = []

        if canvas_result.json_data and "objects" in canvas_result.json_data:
            for obj in canvas_result.json_data["objects"]:
                # If it has an ID, it's an existing item being moved
                if "userData" in obj and "id" in obj["userData"]:
                    canvas_positions[obj["userData"]["id"]] = {
                        'x': obj["left"], 
                        'y': CANVAS_HEIGHT - obj["top"]
                    }
                # If it's a raw 'point', it's a brand new placement
                elif obj.get("type") == "point":
                    new_points_list.append({
                        'x': obj["left"], 
                        'y': CANVAS_HEIGHT - obj["top"]
                    })

        # 2. Start with the data currently in the Table Editor
        # This captures your text edits (Client, Qty, etc.)
        updated_rows = edited_df.to_dict('records')

        # 3. Apply the new coordinates from the Canvas to those rows
        for row in updated_rows:
            if row['id'] in canvas_positions:
                row['x'] = canvas_positions[row['id']]['x']
                row['y'] = canvas_positions[row['id']]['y']

        # 4. Append the Brand New Points
        det = st.session_state.get('temp_item_details', 
                                {'client':'New', 'type':'Container', 'qty':'0', 'size':'Std'})
        
        current_max_id = max([r.get('id', 0) for r in updated_rows] + [0])
        
        for pt in new_points_list:
            current_max_id += 1
            new_row = {
                'id': current_max_id,
                'x': pt['x'], 'y': pt['y'],
                'client': det['client'], 'type': det['type'],
                'qty': det['qty'], 'size': det['size']
            }
            updated_rows.append(new_row)

        # 5. Final Save to Session State
        st.session_state['port_data'] = pd.DataFrame(updated_rows)
        # Clear the initial JSON so the canvas redraws from the new data
        st.session_state['canvas_initial_json'] = generate_initial_drawing(st.session_state['port_data'])
        
        st.success(f"Saved {len(new_points_list)} new items and updated positions!")
        st.rerun()

        # ---------------------------------------------------------
        # MODE: VIEW
        # ---------------------------------------------------------
        else:
            st.subheader("👁️ Live Map View")
            # ... (Standard View Logic) ...
            df_viz = st.session_state['port_data'].copy()
            if not df_viz.empty:
                df_viz['icon_visual'] = df_viz['type'].apply(lambda x: get_icon(x) if x else "📦")
                fig = px.scatter(df_viz, x='x', y='y', color='client', text='icon_visual')
                fig.update_traces(textfont_size=16, marker=dict(opacity=0))
                
                if bg_image:
                    fig.update_layout(images=[dict(source=bg_image, xref="x", yref="y", x=0, y=CANVAS_HEIGHT, sizex=CANVAS_WIDTH, sizey=CANVAS_HEIGHT, sizing="stretch", layer="below")])
                
                fig.update_layout(height=CANVAS_HEIGHT, margin=dict(l=0, r=0, b=0, t=10), dragmode="pan", xaxis_visible=False, yaxis_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Port Empty")