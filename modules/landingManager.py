import os
import streamlit as st
import pandas as pd

from tools.tools import (
    getDB,
    align_data,
    show_mapping_dialog,
    clean_dataframe_types,
    get_display_name,
)
from assets.constants.constants import (
    DB_PATH, UPLOAD_DIR, COLUMNS,
    PATH_BRDX, PATH_PVS, PATH_TEMPLATES, PATH_DEBRQ,
)
from infrastructure.database.db_importer import (
    import_manifest_to_db,
    load_all_manifest_lines,
    load_manifest_for_vessel,
    list_vessels,
    delete_vessel,
    update_changed_manifest_lines,
)
from modules.json_to_excel import extract_to_excel_flattened as gen_excel


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def render_global_manager():
    _render_manager()


# ─────────────────────────────────────────────────────────────────────────────
#  SQLite Manager — full docGeneration flow + DB save
# ─────────────────────────────────────────────────────────────────────────────

def _clear_sqlite_upload():
    """Reset session state used by the SQLite import pipeline."""
    st.session_state.pop("sq_inserted_file",  None)
    st.session_state.pop("sq_final_mapping",  None)
    st.session_state.pop("trigger_mapping", None)


# ─────────────────────────────────────────────────────────────────────────────
#  SQLite DB Manager — editable view saving changed rows to DB
# ─────────────────────────────────────────────────────────────────────────────

def _render_manager():
    st.markdown("### 🗄️ Global Manifest Database Manager")

    df = load_all_manifest_lines()

    if df.empty:
        st.info("No records in SQLite database yet. Import a manifest to get started.")
        return

    st.write("### 🔍 Advanced Filters")

    with st.expander("Filter Options (Click to expand)", expanded=False):
        filtered_df = df.copy()
        cols = st.columns(3)

        for i, column in enumerate(df.columns):
            if column in ("_select", "_db_id"):
                continue
            with cols[i % 3]:
                unique_values  = df[column].unique().tolist()
                selected_values = st.multiselect(
                    f"Filter {column}",
                    options=unique_values,
                    default=[],
                    key=f"filter_{column}",
                )
                if selected_values:
                    filtered_df = filtered_df[filtered_df[column].isin(selected_values)]

    filtered_df = filtered_df.reset_index(drop=True)
    st.divider()

    st.write(f"Showing {len(filtered_df)} of {len(df)} records")

    edited_df = st.data_editor(
        filtered_df,
        width="stretch",
        num_rows="dynamic",
        key="global_db_editor",
        hide_index=True,
        column_config={
            "_db_id":          None,  # Hide internal primary key column
            "NAVIRE":          st.column_config.TextColumn("🚢 Navire", width="small"),
            "ESCALE":          st.column_config.TextColumn("Escale", width="small"),
            "IMO_NAVIRE":      st.column_config.TextColumn("IMO Navire", width="small"),
            "ARRIVAL_DATE":    st.column_config.DateColumn("Arrival Date", format="DD/MM/YYYY", width="small"),
            "B/L":             st.column_config.TextColumn("📄 B/L", width="medium"),
            "ARTICLE":         st.column_config.NumberColumn("Article", step=1, format="%d", width="small"),
            "CLIENT":          st.column_config.TextColumn("👤 Client", width="medium"),
            "DESIGNATION":     st.column_config.TextColumn("📦 Désignation", width="large"),
            "PRODUIT":         st.column_config.TextColumn("Produit", width="small"),
            "MODELE":          st.column_config.TextColumn("Modèle", width="small"),
            "TYPE":            st.column_config.TextColumn("Type", width="small"),
            "CARGO_TYPE":      st.column_config.SelectboxColumn(
                "Cargo Type",
                options=["VEHICULE", "ENGIN", "CAMION", "CONTENEUR", "MARCHANDISE DIVERSE", "AUTRE"],
                width="medium",
            ),
            "CHASSIS/SERIAL":  st.column_config.TextColumn("🔧 Chassis/Serial", width="medium"),
            "QUANTITE":        st.column_config.NumberColumn("🔢 Quantité", step=1, format="%d", width="small"),
            "TONAGE":          st.column_config.NumberColumn("⚖️ Tonnage", format="%.3f", width="small"),
            "RESTE T/P":       st.column_config.NumberColumn("Reste T/P", step=1, format="%d", width="small"),
            "SURFACE":         st.column_config.NumberColumn("Surface", format="%.3f", width="small"),
            "SITUATION":       st.column_config.TextColumn("Situation", width="medium"),
            "OBSERVATION":     st.column_config.TextColumn("Observation", width="large"),
            "POSITION":        st.column_config.TextColumn("Position", width="medium"),
            "TRANSIT":         st.column_config.TextColumn("Transit", width="small"),
            "CLES":            st.column_config.NumberColumn("🔑 Nbr Clé", step=1, format="%d", width="small"),
            "DATE":            st.column_config.DateColumn("📅 Date", format="DD/MM/YYYY", width="small"),
            "DATE ENLEV":      st.column_config.DateColumn("📅 Date Enlev.", format="DD/MM/YYYY", width="small"),
            "landed_qty":      st.column_config.NumberColumn("Landed Qty", step=1, format="%d", width="small"),
            "received_qty":    st.column_config.NumberColumn("Received Qty", step=1, format="%d", width="small"),
        },
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 Save Global Changes to Database"):
            # Extract change state from Streamlit data editor
            editor_state = st.session_state.get("global_db_editor", {})
            edited_rows_dict = editor_state.get("edited_rows", {})
            added_rows_list = editor_state.get("added_rows", [])
            deleted_rows_list = editor_state.get("deleted_rows", [])

            updates = []
            deletions = []
            additions = added_rows_list

            # 1. Collect updates from edited_rows dict
            for row_idx, col_changes in edited_rows_dict.items():
                try:
                    row_idx_int = int(row_idx)
                    if 0 <= row_idx_int < len(filtered_df):
                        line_id = filtered_df.iloc[row_idx_int]["_db_id"]
                        if pd.notna(line_id):
                            updates.append({
                                "_db_id": int(line_id),
                                "changes": col_changes
                            })
                except Exception as exc:
                    st.warning(f"Could not parse edit for row {row_idx}: {exc}")

            # Fallback comparison if edited_rows dict was empty/cleared
            if not updates and len(edited_df) == len(filtered_df):
                for idx in range(len(filtered_df)):
                    orig_row = filtered_df.iloc[idx]
                    edit_row = edited_df.iloc[idx]
                    line_id = orig_row["_db_id"]
                    if pd.isna(line_id):
                        continue

                    row_changes = {}
                    for col in filtered_df.columns:
                        if col == "_db_id":
                            continue
                        val_orig = orig_row[col]
                        val_edit = edit_row[col]
                        if (pd.isna(val_orig) and pd.notna(val_edit)) or (pd.notna(val_orig) and val_orig != val_edit):
                            row_changes[col] = val_edit

                    if row_changes:
                        updates.append({"_db_id": int(line_id), "changes": row_changes})

            # 2. Collect deletions from deleted_rows list
            for row_idx in deleted_rows_list:
                try:
                    row_idx_int = int(row_idx)
                    if 0 <= row_idx_int < len(filtered_df):
                        line_id = filtered_df.iloc[row_idx_int]["_db_id"]
                        if pd.notna(line_id):
                            deletions.append(int(line_id))
                except Exception as exc:
                    st.warning(f"Could not parse deletion for row {row_idx}: {exc}")

            if not updates and not additions and not deletions:
                st.info("No changed rows detected to save.")
            else:
                updated_c, added_c, deleted_c, errs = update_changed_manifest_lines(
                    updates=updates,
                    additions=additions,
                    deletions=deletions,
                )

                if errs:
                    for err in errs:
                        st.error(err)

                msg_parts = []
                if updated_c > 0: msg_parts.append(f"{updated_c} updated")
                if added_c > 0: msg_parts.append(f"{added_c} added")
                if deleted_c > 0: msg_parts.append(f"{deleted_c} deleted")

                summary_str = ", ".join(msg_parts) if msg_parts else "0 rows modified"
                st.success(f"✅ SQLite Database updated successfully! ({summary_str})")
                st.rerun()

    with col_b:
        display_df = edited_df.drop(columns=["_db_id"], errors="ignore")
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Current View (CSV)",
            data=csv,
            file_name="filtered_database.csv",
            mime="text/csv",
        )

