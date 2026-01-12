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

CLIENT_COLORS = {
    'CMA CGM': '#1f77b4', 'MSC': '#ff7f0e', 'Maersk': '#2ca02c',
    'Sonatrach': '#d62728', 'Cevital': '#9467bd', 'Other': '#7f7f7f'
}



# === HELPER FUNCTIONS ===


def get_client_color(client_name):
    return CLIENT_COLORS.get(client_name, CLIENT_COLORS['Other'])


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
        berth_num = max(1, min(6, berth_num))  # Clamp between 1-6

        # 3. Determine Storage Zone (Vertical split for Warehouses)
        # Assuming 4 zones from top to bottom
        zone_height = CANVAS_HEIGHT / 4
        zone_num = math.ceil((CANVAS_HEIGHT - y) /
                             zone_height)  # Inverted Y logic
        zone = f"Zone-{max(1, min(4, zone_num))}"

        return dock, f"Pos-{berth_num}", zone
    except:
        return "Unknown", "N/A", "N/A"


def generate_initial_drawing(df):
    objects = []
    if df.empty:
        return {"version": "4.4.0", "objects": []}

    for index, row in df.iterrows():
        if pd.isna(row.get('x')) or pd.isna(row.get('y')):
            continue
        # Get color based on client
        c_color = get_client_color(row.get('client'))
        icon = get_icon(row.get('type'))
        item_id = row.get('item_id')
        obj = {
            # "type": f"{letyp}|{row['item_id']}",
            "type": "text",
            "left": row['x'],
            "top": CANVAS_HEIGHT - row['y'],
            "width": 8, "height": 8, "fill": c_color,
            "text": icon,  # ID encoded here
            "fontSize": 30,
            "fontFamily": f"Time new Romans | {item_id}",
        }

        objects.append(obj)

    return {"version": "4.4.0", "objects": objects}


def show_map():
    st.set_page_config(layout="wide", page_title="Port Logic System")

    # --- 1. Session State & Data Init ---
    if 'port_data' not in st.session_state:
        st.session_state['port_data'] = pd.DataFrame([
            {'item_id': 1, 'x': 150, 'y': 200, 'client': 'CMA CGM',
                'type': 'Container Ship', 'qty': '1000 TEU', 'size': 'Large'},
            {'item_id': 2, 'x': 450, 'y': 350, 'client': 'MSC',
                'type': 'Plywood', 'qty': '500 pallets', 'size': '200m2'},
        ])

    
    df_filtered=st.session_state['port_data'].copy()

    # Ensure tool mode exists
    if 'tool_mode' not in st.session_state:
        st.session_state['tool_mode'] = 'transform'  # Default to moving items

    if 'canvas_initial_json' not in st.session_state:
        st.session_state['canvas_initial_json'] = generate_initial_drawing(
            st.session_state['port_data'])

    # --- 2. Image Loading ---
    bg_image = None
    if os.path.exists(MAP_IMAGE_PATH):
        try:
            raw_img = Image.open(MAP_IMAGE_PATH).convert("RGB")
            bg_image = raw_img.resize((CANVAS_WIDTH, CANVAS_HEIGHT))
        except:
            st.error("Image not found")

    st.title("⚓ Port Operations Map")
    col_map, col_controls = st.columns([3, 1], gap="medium")

    # === RIGHT COLUMN: CONTROLS ===
    with col_controls:
        st.subheader("⚙️ Controls")

        # A. Mode Switcher
        app_mode = st.radio(
            "App Mode:", ["👁️ View Mode", "✏️ Edit Mode"], horizontal=True)
        st.divider()

        if app_mode == "✏️ Edit Mode":
            # B. TOOL SWITCHER (The Fix!)
            # We map friendly names to st_canvas 'drawing_mode' strings
            tool_map = {"✋ Move Items": "transform",
                        "📍 Place New Item": "point"}

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
                # with st.form("add_item_form"):
                st.markdown("#### 📦 New Item Details")
                client = st.selectbox(
                    "Client", ["CMA CGM", "MSC", "Maersk", "Sonatrach", "Cevital"])
                cat_type = st.selectbox("Item Type", [
                                        "Container Ship", "Bulk Carrier", "Tanker", "Plywood", "Coil", "Beams", "Utilities", "Grain"])
                qty = st.text_input("Quantity", "100")
                size = st.text_input("Size", "Std")

                # if st.form_submit_button("Update Next Drop"):
                st.session_state['temp_item_details'] = {
                    'client': client, 'type': cat_type, 'qty': qty, 'size': size
                }

                st.success(" Click on the map to drop a new Client.")
            else:
                st.info("Move Items Then click save Changes")
        else:
            df_viz = st.session_state['port_data'].copy()
            # 1. Multi-select for Clients
            all_clients = df_viz['client'].unique()
            selected_clients = st.multiselect("Select Clients", all_clients, default=all_clients)
            
            # 2. Multi-select for Types
            all_types = df_viz['type'].unique()
            selected_types = st.multiselect("Select Types", all_types, default=all_types)

            # 3. Filter the data based on selection
            df_filtered = df_viz[
                (df_viz['client'].isin(selected_clients)) & 
                (df_viz['type'].isin(selected_types))
            ]
            st.info("right side of view map")
    # === LEFT COLUMN: MAP & TABLE ===
    with col_map:
        # ---------------------------------------------------------
        # MODE: EDIT
        # ---------------------------------------------------------
        if app_mode == "✏️ Edit Mode":
            st.subheader("✏️ Editor Canvas")

            st.session_state["canvas_initial_json"] = generate_initial_drawing(
                st.session_state["port_data"])

            # 1. Canvas with Dynamic Drawing Mode
            canvas_result = st_canvas(
                fill_color="rgba(255, 0, 0, 0.5)",  # Red dot for new drops
                background_image=bg_image,
                background_color="#eee",
                initial_drawing=st.session_state['canvas_initial_json'],
                update_streamlit=True,
                height=CANVAS_HEIGHT,
                width=CANVAS_WIDTH,
                drawing_mode=st.session_state['tool_mode'],  # <--- KEY FIX
                display_toolbar=True,
                key="canvas_editor_main"
            )
            # preparing data for displaying it on the table
            # 2. Data Processing (Add Zone/Dock info)
            display_df = st.session_state['port_data'].copy()

            # st.session_state['canvas_initial_json'] = generate_initial_drawing(st.session_state['port_data'])

            # Ensure safe columns
            for c in ['x', 'y', 'type', 'client', 'item_id']:
                if c not in display_df.columns:
                    display_df[c] = None

            loc_data = []
            if not display_df.empty:
                display_df['Icon'] = display_df['type'].apply(
                    lambda x: get_icon(x) if x else "📦")
                for _, row in display_df.iterrows():
                    # Calculate Dock, Berth AND Zone
                    res = determine_location(row.get('x', 0), row.get('y', 0))
                    loc_data.append(res)
            else:
                display_df['Icon'] = []

            # Unpack the 3-part location tuple
            display_df['Dock'] = [l[0] for l in loc_data]
            display_df['Berth'] = [l[1] for l in loc_data]
            display_df['Zone'] = [l[2] for l in loc_data]

            # 3. Editable Table
            st.subheader("📝 Edit Data")
            cols_show = ['Icon', 'Dock', 'Berth', 'Zone',
                         'client', 'type', 'qty', 'size', 'item_id']
            final_cols = [c for c in cols_show if c in display_df.columns]

            edited_df = st.data_editor(
                display_df[final_cols],
                num_rows="dynamic",
                use_container_width=True,
                key="table_editor_v2",
                disabled=['Icon', 'Dock', 'Berth', 'Zone', 'item_id'],
                hide_index=True
            )

            # 4. SAVE LOGIC From
            if st.button("💾 Save All Changes", type="primary"):
                # 1. Create a map of {item_id: (new_x, new_y)} from the canvas objects
                # canvas_shapes   st.session_state["canvas_initial_json"]
                # print("here is BEFORE moving data port ......")
                # print(st.session_state["port_data"])
                canvas_shapes = canvas_result.json_data.get("objects", [])

                coords_map, new_pts = {}, []

                # if canvas_result and canvas_result.json_data and "objects" in canvas_result.json_data:
                for obj in canvas_shapes:
                    letype = obj.get("type")
                    if letype in ["text"]:
                        _, item_id = obj.get("fontFamily").split("|")
                        item_id = int(item_id.strip())
                        coords_map[item_id] = (
                            obj["left"], CANVAS_HEIGHT - obj["top"])
                    elif letype in ["circle"]:
                        new_pts.append(
                            (obj["left"], CANVAS_HEIGHT - obj["top"]))

                upd = []
                for _, r in edited_df.iterrows():
                    # rid = r["item_id"]
                    rdict = r.to_dict()

                    rid2 = int(rdict.get("item_id"))

                    if rid2 in coords_map:
                        print("inside cordinate existed")
                        rdict["x"], rdict["y"] = coords_map[rid2]
                    else:
                        print("keeping original coordinate for table")
                        orig = st.session_state['port_data'].query(
                            "item_id==@rid2").iloc[0]
                        rdict["x"], rdict["y"] = orig["x"], orig["y"]

                    upd.append(rdict)

                det = st.session_state.get("temp_item_details", {})
                next_id = max([r["item_id"] for r in upd]+[0]) + 1
                for x, y in new_pts:
                    upd.append({**det, "item_id": next_id, "x": x, "y": y})
                    next_id += 1

                st.session_state["port_data"] = pd.DataFrame(upd)
                st.session_state["canvas_initial_json"] = generate_initial_drawing(
                    st.session_state["port_data"])
                print("here is after moving data port ......")
                print(st.session_state["port_data"])
                st.rerun()

        # ---------------------------------------------------------
        # MODE: VIEWdf_filtered
        # ---------------------------------------------------------

        else:
            st.subheader("👁️ Live Map View")
            df_viz = st.session_state['port_data'].copy()

            # 1. Validation: Plotly needs 'x' and 'y' columns to exist
            # if not df_filtered.empty:
            # Ensure safe columns
            for c in ['x', 'y', 'type', 'client', 'item_id']:
                if c not in df_filtered.columns:
                    df_filtered[c] = None

            df_filtered['icon_visual'] = df_filtered['type'].apply(
                lambda x: get_icon(x) if x else "📦")

            # 2. Build Plotly Figure
            fig = px.scatter(
                df_filtered,
                x='x',
                y='y',
                color='client' if not df_filtered.empty else None, # Avoid error if empty
                text='icon_visual',
                # Define what shows up in the tooltip
                hover_data={
                    'client': True,
                    'type': True,
                    'qty': True,
                    'size': True,
                    'x': False,  # Set to False to hide coordinates if not needed
                    'y': False,
                    'icon_visual': False
                },
                range_x=[0, CANVAS_WIDTH],
                range_y=[0, CANVAS_HEIGHT]
            )

            fig.update_traces(textposition='top center')


            # Make the emoji icons larger and hide the scatter dots
            fig.update_traces(textfont_size=24, marker=dict(opacity=0))

            # 3. Add Background Image
            if bg_image:
                fig.update_layout(images=[dict(
                    source=bg_image,
                    xref="x", yref="y",
                    x=0, y=CANVAS_HEIGHT,
                    sizex=CANVAS_WIDTH, sizey=CANVAS_HEIGHT,
                    sizing="stretch", layer="below"
                )])

            # 4. Clean up UI
            fig.update_layout(
                height=CANVAS_HEIGHT,
                margin=dict(l=0, r=0, b=0, t=10),
                xaxis_visible=False,
                yaxis_visible=False,
                showlegend=False,
                # showlegend=True,
                # legend=dict(
                #     orientation="h",      # Horizontal legend
                #     yanchor="top",
                #     y=1,               # Position below the plot
                #     xanchor="right",
                #     x=1,
                #     bgcolor="rgba(255, 255, 100, 0.5)"
                # )
            )

            st.plotly_chart(fig, use_container_width=True)
            
            if not df_viz.empty:
                # 5. Summary Table for View Mode  -----------
                st.write("### 📋 Current Port Inventory")

                # recompute location columns like in edit mode
                df_viz['Dock'], df_viz['Berth'], df_viz['Zone'] = zip(
                    *df_viz.apply(lambda r: determine_location(r['x'], r['y']), axis=1))

                # add Icon
                df_viz['Icon'] = df_viz['type'].apply(lambda x: get_icon(x))

                # choose same columns as edit
                cols = ['Icon', 'Dock', 'Berth', 'Zone',
                        'client', 'type', 'qty', 'size', 'item_id']

                st.dataframe(
                    df_viz[cols], use_container_width=True, hide_index=True)

            else:
                st.warning(
                    "The port map is currently empty. Switch to Edit Mode to place items.")
