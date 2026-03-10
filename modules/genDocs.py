import os
import streamlit as st
import pandas as pd
from datetime import date


from modules.json_to_excel import extract_to_excel_flattened as gen_excel
from tools.tools import getDB, align_data, show_mapping_dialog
from modules.genBorderaux import generate_brd
from modules.genDebarq import gen_table_deb
from modules.genPv import generate_daily_pv
from assets.constants.constants import UPLOAD_DIR, DB_PATH, COLUMNS


def docGeneration(clear_downloads_func):

    if "inserted_file" not in st.session_state:
        st.session_state.inserted_file = None
    if "final_mapping" not in st.session_state:
        st.session_state.final_mapping = {}
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

     # 1. Upload Logic
    st.session_state.uploaded_file = st.file_uploader(
        "Upload XLSX/CSV/JSON Ship Data",
        type=["xlsx", "csv", "json"],  # Added json
        on_change=clear_downloads_func,
        key=f"uploader_{st.session_state.uploader_key}"
    )

    if st.session_state.uploaded_file and not st.session_state.get("final_mapping", False):
        # if st.session_state.uploaded_file and not st.session_state.uploaded_file_processed:
        # if uploaded_file and not st.session_state.get("mapping_shown", False):
        filename = st.session_state.uploaded_file.name
        # Handle JSON conversion
        if st.session_state.uploaded_file.name.endswith('.json'):
            excel_name = filename.replace('.json', '.xlsx')
            save_path = os.path.join(UPLOAD_DIR, excel_name)
            # Convert JSON to Excel using your helper
            excel_path = gen_excel(
                st.session_state.uploaded_file, save_path, st_upload=True)
            st.success(f"JSON converted and saved as: {excel_name}")
            st.session_state.inserted_file = excel_name
        else:
            save_path = os.path.join(UPLOAD_DIR, filename)
            with open(save_path, "wb") as f:
                f.write(st.session_state.uploaded_file.getbuffer())
            st.success(f"Saved {filename}")
            st.session_state.inserted_file = filename

        # st.session_state.mapping_shown = True
        st.session_state.trigger_mapping = True
        st.session_state.uploader_key += 1

    # 2. List and Select Files
    files = os.listdir(UPLOAD_DIR)
    if files:

        default_index = 0
        if st.session_state.uploaded_file and st.session_state.inserted_file in files:
            # st.session_state.uploaded_file = None # Reset uploader
            default_index = files.index(st.session_state.inserted_file)
            # st.session_state.inserted_file=None

        st.session_state.selected_file = st.selectbox(
            "Select a ship file to operate on:",
            files,
            index=default_index,
            on_change=clear_downloads_func,
            key="file_selector_widget"
        )
        # st.toast(f" {st.session_state.selected_file}")
        file_path = os.path.join(UPLOAD_DIR, st.session_state.selected_file)

        # Load Data
        df_raw = pd.read_excel(file_path) if st.session_state.selected_file.endswith(
            '.xlsx') else pd.read_csv(file_path)
        molded_df = df_raw
        trigger = st.session_state.get("trigger_mapping", False)
        # TRIGGER DIALOG ONLY ON NEW UPLOAD
        if st.session_state.inserted_file and trigger:
            show_mapping_dialog(df_raw)

        if not trigger and st.session_state.inserted_file:
            st.toast("inside final mapping")
            # clear the inserted file after processing
            st.session_state.inserted_file = None
            st.session_state.trigger_mapping = False  # clear the trigger

            final_mp = st.session_state.get("final_mapping", {})

            # success=False
            molded_df, success = align_data(df_raw, final_mp)
            if os.path.exists(file_path):
                os.remove(file_path)

            if len(final_mp) and success:
                # if success :
                st.success("Data Aligned Successfully!")
                molded_df = molded_df.reindex(columns=COLUMNS)
                # delete first row that contain headers in the molded_df
                # molded_df = molded_df.iloc[1:].copy() # This line deletes the first row
                # Save the aligned DataFrame to the original file path
                molded_df.to_excel(file_path, index=False)
                st.session_state.final_mapping = {}

                # st.toast(f"no mapping arranged so file uplodade was rejected {file_path}")
                # st.rerun()
            st.rerun()
        else:
            pass

        del df_raw

        # CRUD Operations
        st.write(f"**Editing:** `{st.session_state.selected_file}`")
        # IMPORTANT: Key must be unique from Tab 1
        filter_col, table_col = st.columns([1, 4])  # 1:4 ratio — filter is small
        with table_col:
            
            edited_df = st.data_editor(
                molded_df,
                num_rows="dynamic",
                key="single_file_editor",
                width='stretch',
                # column_order

                column_config={
                    "_index": st.column_config.CheckboxColumn("Select"),
                    # ── Ship Name ──
                    "NAVIRE": st.column_config.TextColumn(
                        "🚢 Navire",
                        help="Nom du navire",
                        max_chars=100,
                        default="",
                        width="medium",
                    ),

                    #         # ── Date of Arrival ──
                    # "DATE": st.column_config.DateColumn(
                    #     "📅 DATE",
                    #     help="Date d'arrivée",
                    #     format="DD/MM/YYYY",
                    #     min_value=date(2020, 1, 1),
                    #     max_value=date(2030, 12, 31),
                    #     step=1,
                    # ),

                    # ── Bill of Lading ──
                    "B/L": st.column_config.TextColumn(
                        "📄 B/L",
                        help="Numéro de connaissement (Bill of Lading)",
                        max_chars=50,
                        default="",
                        width="medium",
                    ),

                    # ── Designation ──
                    "DESIGNATION": st.column_config.TextColumn(
                        "📦 Désignation",
                        help="Description de la marchandise",
                        max_chars=200,
                        default="",
                        width="large",
                    ),

                    # ── Quantity ──
                    "QUANTITE": st.column_config.NumberColumn(
                        "🔢 Quantité",
                        help="Nombre d'unités",
                        min_value=0,
                        max_value=100000,
                        step=1,
                        format="%d",
                        default=0,
                        width="small",
                    ),

                    # ── Tonnage ──
                    "TONAGE": st.column_config.NumberColumn(
                        "⚖️ Tonnage",
                        help="Poids en tonnes",
                        min_value=0.0,
                        max_value=999999.0,
                        step=0.01,
                        format="%.2f T",
                        default=0.0,
                        width="small",
                    ),

                    # ── Client ──
                    "CLIENT": st.column_config.TextColumn(
                        "👤 Client",
                        help="Nom du client",
                        max_chars=100,
                        default="",
                        width="medium",
                    ),

                    # ── Chassis / Serial ──
                    "CHASSIS/SERIAL": st.column_config.TextColumn(
                        "🔧 Chassis/Serial",
                        help="Numéro de chassis ou numéro de série",
                        max_chars=50,
                        default="",
                        width="medium",
                    ),

                    # ── Reste T/P ──
                    "RESTE T/P": st.column_config.NumberColumn(
                        "📊 Reste T/P",
                        help="Reste à traiter (Tonnes/Pièces)",
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        default=0.0,
                        width="small",
                    ),

                    # ── Type ──
                    "TYPE": st.column_config.SelectboxColumn(
                        "📋 Type",
                        help="Type de marchandise",
                        options=[
                            "Conteneur",
                            "Véhicule",
                            "Matériel",
                            "Divers",
                            "Vrac",
                            "Roulier",
                            "Conventionnel",
                        ],
                        default="Divers",
                        width="medium",
                    ),

                    # ── Situation ──
                    "SITUATION": st.column_config.SelectboxColumn(
                        "🚦 Situation",
                        help="Situation actuelle",
                        options=[
                            "En attente",
                            "En cours",
                            "Dédouané",
                            "Livré",
                            "Bloqué",
                            "En transit",
                            "Sorti",
                        ],
                        default="En attente",
                        width="medium",
                    ),

                    # # ── Observation ──
                    # "OBSERVATION": st.column_config.TextColumn(
                    #     "📝 Observation",
                    #     help="Notes et observations",
                    #     max_chars=500,
                    #     default="",
                    #     width="large",
                    # ),

                    # # ── Position ──
                    # "POSITION": st.column_config.TextColumn(
                    #     "📍 Position",
                    #     help="Emplacement dans le port/entrepôt",
                    #     max_chars=50,
                    #     default="",
                    #     width="small",
                    # ),

                    # # ── Transit ──
                    # "TRANSIT": st.column_config.TextColumn(
                    #     "🚚 Transit",
                    #     help="Transitaire",
                    #     max_chars=100,
                    #     default="",
                    #     width="medium",
                    # ),

                    # ── Keys ──
                    "CLES": st.column_config.SelectboxColumn(
                        "🔑 Clés",
                        help="Clés disponibles",
                        options=[
                            "Oui",
                            "Non",
                            "N/A",
                        ],
                        default="N/A",
                        width="small",
                    ),

                    # ── Surface ──
                    "SURFACE": st.column_config.NumberColumn(
                        "📐 Surface",
                        help="Surface en m²",
                        min_value=0.0,
                        step=0.01,
                        format="%.2f m²",
                        default=0.0,
                        width="small",
                    ),

                    # # ── DAEMO Breaker ──
                    # "DAEMO BREAKER (DRB) TOP BOX TYPE": st.column_config.TextColumn(
                    #     "🔨 DAEMO Breaker",
                    #     help="DAEMO Breaker (DRB) Top Box Type",
                    #     max_chars=100,
                    #     default="",
                    #     width="medium",
                    # ),

                    # # ── Date Enlevement ──
                    # "DATE ENLEV": st.column_config.DateColumn(
                    #     "📅 Date Enlèvement",
                    #     help="Date d'enlèvement de la marchandise",
                    #     format="DD/MM/YYYY",
                    #     min_value=date(2000, 1, 1),
                    #     max_value=date(2030, 12, 31),
                    #     default=None,
                    #     width="small",
                    # ),
                },
            )
       
        with filter_col:
            filtered_df = molded_df.copy()
            
            for i, column in enumerate(molded_df.columns):
                if column == "_select":
                    continue
                    
                unique_values = molded_df[column].unique().tolist()
                
                # Multiselect is large; using a label and index makes it compact
                selected_values = st.multiselect(
                    f"{column}",
                    options=unique_values,
                    default=[],
                    key=f"filter_{column}_{i}",
                    label_visibility="collapsed", # Hides label to save space
                    placeholder="All" # Makes it look smaller when empty
                )
                
                if selected_values:
                    filtered_df = filtered_df[filtered_df[column].isin(selected_values)]

        col1, col2, col3, col4, col5 = st.columns(5)

        # --- SAVE CHANGES ---
        if col1.button("💾 Save Changes", key="btn_save"):
            # 2. Merge with Global DB
            # edited_df = edited_df.reindex(columns=COLUMNS)
            # edited_df.to_excel(file_path, index=False)
            st.toast("File Updated!")

            st.session_state.uploaded_file = None
            st.session_state.trigger_mapping = False  # clear the trigger
            # clear the inserted file after processing
            st.session_state.inserted_file = None
            st.session_state.final_mapping = {}

            global_db = getDB()
            global_db = global_db.reindex(columns=COLUMNS)
            # Combine current edited data with the master database
            updated_global = pd.concat(
                [global_db, edited_df], ignore_index=True)

            # Optional: Remove exact duplicate rows
            updated_global = updated_global.drop_duplicates()

            # 3. Save the master database back to DB_PATH
            updated_global.to_excel(DB_PATH, index=False)

            st.toast("File and Global Database Updated!")
            clear_downloads_func()

        # --- OPERATION 2 ---
        if col2.button("📋 Gen. Debarquement", key="btn_debarq"):
            generated_path = gen_table_deb(file_path)
            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Debarquement (Excel)",
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
            st.info("Debarquement Table Generated")

        # --- OPERATION 3: GENERATE BORDERAUX ---
        if col3.button("📜 Gen. Borderaux", key="btn_brd"):
            # Execute generation logic
            generated_path = generate_brd(
                file_path, sheet_name=0, template_name="template.docx")

            st.session_state.active_download = {
                "path": generated_path,
                "label": "📥 Download Bordereau (Word)",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }

            st.success("Bordereau Generated!")

        # --- OPERATION 4 ---
        if col4.button("📝 Gen. Daily PVs", key="btn_pvs"):
            # Execute generation logic
            generated_path = generate_daily_pv(file_path)
            # os.path.basename(generated_path)
            # Set session state for download button
            st.session_state.active_download = {
                "path": generated_path,
                "label": f"📥 Download {os.path.basename(file_path)}",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            }
            st.success(
                f"PV Generated in folder: {os.path.basename(file_path)}")
            st.info("Gen. Daily PVs")

        # --- OPERATION 5: DELETE FILE ---
        with col5:
            c1, c2 = st.columns([1, 2])
            with c1:
                confirm_delete = st.checkbox(
                    "Confirmer la suppression", key="check_del", label_visibility="collapsed")
            with c2:
                if st.button("🗑️ Delete", key="btn_delete", type="secondary", disabled=not confirm_delete):
                    try:
                        os.remove(file_path)
                        st.toast(f"Deleted {st.session_state.selected_file}")
                        clear_downloads_func()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        # 3. DYNAMIC DOWNLOAD BUTTON
        if "active_download" in st.session_state and st.session_state.active_download:
            st.divider()
            file_info = st.session_state.active_download

            # Check if file exists before trying to open
            if os.path.exists(file_info["path"]):
                with open(file_info["path"], "rb") as f:
                    st.download_button(
                        label=file_info["label"],
                        data=f.read(),
                        file_name=os.path.basename(file_info["path"]),
                        mime=file_info["mime"],
                        type="primary",
                        key="dl_button_dynamic"
                    )
            else:
                st.error("Generated file not found. Please regenerate.")
