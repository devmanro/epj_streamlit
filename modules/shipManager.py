"""
modules/shipManager.py
──────────────────────────────────────────────────────────────────────────────
Single File Manager  —  SQLite-backed edition.

Architecture
────────────
All manifest data is stored in / read from database.sqlite via the
infrastructure.database.db_importer helpers.
The legacy data/uploads/ folder is still used as a *temporary staging area*
during the column-mapping step, then the temp file is deleted.
Downstream document generators (Debarquement, Borderaux, Daily PVs) receive
a temporary Excel file path built from the edited DataFrame; the temp file is
cleaned up after the generator returns.

Session-state keys (all prefixed sfm_ to avoid collisions):
    sfm_inserted_file   - basename of the temp file saved to UPLOAD_DIR
    sfm_final_mapping   - column-mapping dict from show_mapping_dialog
    sfm_trigger_mapping - bool flag that opens the mapping dialog
    sfm_uploader_key    - int, incremented to reset the file uploader widget
"""

import os
import streamlit as st
import pandas as pd

from tools.tools import (
    align_data,
    show_mapping_dialog,
    clean_dataframe_types,
    get_display_name,
)
from assets.constants.constants import UPLOAD_DIR, COLUMNS
from infrastructure.database.db_importer import (
    import_manifest_to_db,
    load_manifest_for_vessel,
    list_vessels,
    delete_vessel,
    update_vessel_name,
    replace_vessel_lines,
)
from modules.json_to_excel import extract_to_excel_flattened as gen_excel
from modules.Bl_tracking import render_tracking_ui

# downstream generators
from modules.genDebarq import gen_table_deb
from modules.genBorderaux import generate_brd
from modules.genPv import generate_daily_pv


# =============================================================================
#  PUBLIC ENTRY POINT
# =============================================================================

def render_single_file_manager(clear_downloads_func):
    """Render the Single File Manager tab (My current view + Landing/Stock)."""
    tab_main, tab_track = st.tabs(
        ["My current view", "Landing / Stock tracking"]
    )

    with tab_main:
        st.subheader("📂 Single Ship Operations")
        _render_sfm_main(clear_downloads_func)

    with tab_track:
        st.subheader("📊 Landing / Stock Tracking")
        render_tracking_ui(None, None)


# =============================================================================
#  SESSION-STATE HELPERS
# =============================================================================

def _sfm_init_state():
    defaults = {
        "sfm_inserted_file":   None,
        "sfm_final_mapping":   {},
        "sfm_trigger_mapping": False,
        "trigger_mapping":     False,
        "sfm_uploader_key":    0,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _sfm_clear_upload():
    """Reset import-pipeline session state (called by the uploader on_change)."""
    st.session_state.sfm_inserted_file   = None
    st.session_state.sfm_final_mapping   = {}
    st.session_state.sfm_trigger_mapping = False
    st.session_state.trigger_mapping     = False
    st.session_state.pop("final_mapping", None)


# =============================================================================
#  TEMP-FILE ADAPTER FOR DOWNSTREAM GENERATORS
# =============================================================================

def _df_to_temp_excel(df: pd.DataFrame, stem: str = "sfm_export") -> str:
    """Write df to a temporary Excel file inside UPLOAD_DIR and return the path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    tmp_path = os.path.join(UPLOAD_DIR, f"_tmp_{stem}.xlsx")
    
    # Strip timezone info from any datetime columns to satisfy Excel/openpyxl
    df_export = df.copy()
    for col in df_export.columns:
        if pd.api.types.is_datetime64_any_dtype(df_export[col]):
            df_export[col] = df_export[col].apply(
                lambda x: x.tz_localize(None) if hasattr(x, "tz_localize") and x is not None and getattr(x, "tzinfo", None) is not None
                else (x.replace(tzinfo=None) if hasattr(x, "replace") and getattr(x, "tzinfo", None) is not None else x)
            )
            
    df_export.to_excel(tmp_path, index=False)
    return tmp_path


def _run_generator(generator_fn, df: pd.DataFrame, vessel_stem: str):
    """
    Write df to a temp Excel, call generator_fn(file_path), clean up and
    return the path to the generated output file.
    """
    tmp_path = _df_to_temp_excel(df, stem=vessel_stem)
    try:
        return generator_fn(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# =============================================================================
#  IMPORT PANEL
# =============================================================================

def _render_import_panel():
    """
    Collapsible expander that mirrors _render_sqlite_manager() from
    landingManager.py but stores the result under sfm_ session-state keys.
    """
        
    uploaded = st.file_uploader(
        "Choose manifest (.xlsx / .csv / .json)",
        type=["xlsx", "csv", "json"],
        key=f"sfm_uploader_{st.session_state.sfm_uploader_key}",
        on_change=_sfm_clear_upload,
    )

    # ── Save file to disk & trigger mapping dialog ────────────────────────
    if uploaded and not st.session_state.sfm_final_mapping and not st.session_state.get("final_mapping"):
        filename = uploaded.name
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        if filename.endswith(".json"):
            excel_name = filename.replace(".json", ".xlsx")
            save_path  = os.path.join(UPLOAD_DIR, excel_name)
            try:
                gen_excel(uploaded, save_path, st_upload=True)
                st.success(f"JSON converted: {excel_name}")
                st.session_state.sfm_inserted_file = excel_name
            except Exception as exc:
                st.error(f"JSON conversion failed: {exc}")
                return
        else:
            save_path = os.path.join(UPLOAD_DIR, filename)
            try:
                with open(save_path, "wb") as fh:
                    fh.write(uploaded.getbuffer())
                st.success(f"File saved: {filename}")
                st.session_state.sfm_inserted_file = filename
            except Exception as exc:
                st.error(f"Could not save file: {exc}")
                return

        st.session_state.trigger_mapping     = True
        st.session_state.sfm_trigger_mapping = True
        st.session_state.sfm_uploader_key   += 1

    # ── Column-mapping dialog ─────────────────────────────────────────────
    inserted_file = st.session_state.sfm_inserted_file

    if st.session_state.get("final_mapping") or st.session_state.get("sfm_final_mapping"):
        st.session_state.trigger_mapping     = False
        st.session_state.sfm_trigger_mapping = False

    trigger = st.session_state.get("sfm_trigger_mapping", False) and st.session_state.get("trigger_mapping", False)

    if inserted_file and trigger:
        file_path = os.path.join(UPLOAD_DIR, inserted_file)
        try:
            df_for_mapping = (
                pd.read_excel(file_path)
                if inserted_file.endswith((".xlsx", ".xls"))
                else pd.read_csv(file_path)
            )
        except Exception as exc:
            st.error(f"Could not read saved file for mapping: {exc}")
            return

        show_mapping_dialog(df_for_mapping)
        st.stop()

    # ── align_data + clean + import to SQLite ─────────────────────────────
    if inserted_file and not trigger:
        st.session_state.trigger_mapping     = False
        st.session_state.sfm_trigger_mapping = False

        # Accept mapping from either sfm_ key or the shared key that
        # show_mapping_dialog writes into.
        final_mp = (
            st.session_state.get("sfm_final_mapping") or
            st.session_state.get("final_mapping", {})
        )

        file_path = os.path.join(UPLOAD_DIR, inserted_file)

        with st.spinner("Loading file..."):
            try:
                df_raw = (
                    pd.read_excel(file_path)
                    if inserted_file.endswith((".xlsx", ".xls"))
                    else pd.read_csv(file_path)
                )
            except Exception as exc:
                st.error(f"Cannot read file: {exc}")
                _sfm_clear_upload()
                return

        with st.spinner("Aligning columns and running cargo-type prediction..."):
            try:
                molded_df, success = align_data(df_raw, final_mp)
            except Exception as exc:
                st.error(f"align_data() failed: {exc}")
                _sfm_clear_upload()
                return

        if not success:
            st.warning(
                "Column alignment skipped (too few mapped columns). "
                "Importing as-is."
            )
            molded_df = df_raw

        with st.spinner("Reindexing to standard schema..."):
            df_out = molded_df.reindex(columns=COLUMNS).fillna("-")
            mapped_target_cols = set(final_mp.values()) if final_mp else set()
            unmapped_cols = [
                col for col in df_out.columns
                if col not in mapped_target_cols
            ]
            try:
                df_clean = clean_dataframe_types(df_out, only_cols=unmapped_cols)
            except Exception as exc:
                st.warning(f"clean_dataframe_types() raised: {exc}")
                df_clean = df_out

        with st.expander("Preview aligned data (first 20 rows)", expanded=False):
            st.dataframe(df_clean.head(20), use_container_width=True, hide_index=True)

        # ── Resolve vessel metadata ───────────────────────────────────────
        vname  = st.session_state.get("sfm_vessel_name", "").strip() if "sfm_vessel_name" in st.session_state else ""
        escale = st.session_state.get("sfm_escale",      "").strip() if "sfm_escale" in st.session_state else ""
        imo    = st.session_state.get("sfm_imo",         "").strip() if "sfm_imo" in st.session_state else ""

        def _first_valid(col_name):
            if col_name in df_clean.columns:
                valid = (
                    df_clean[col_name]
                    .replace(["-", "", "None", "nan"], pd.NA)
                    .dropna()
                )
                if not valid.empty:
                    return str(valid.iloc[0]).strip()
            return ""

        if not vname:  vname  = _first_valid("NAVIRE")
        if not escale: escale = _first_valid("ESCALE")
        if not imo:    imo    = _first_valid("IMO_NAVIRE")

        # ── UNKNOWN fallback ──────────────────────────────────────────────
        if not vname:
            vname = "UNKNOWN"
            st.info(
                "No vessel name found in file or metadata. "
                "Importing under UNKNOWN — you can rename it after import "
                "using the vessel selector below."
            )

        with st.spinner(f"Saving {len(df_clean)} rows to SQLite..."):
            try:
                inserted, skipped, row_errors = import_manifest_to_db(
                    df_clean,
                    vessel_name=vname,
                    escale=escale or None,
                    imo=imo or None,
                )
            except Exception as exc:
                st.error(f"import_manifest_to_db() failed: {exc}")
                _sfm_clear_upload()
                return

        m1, m2, m3 = st.columns(3)
        m1.metric("Rows Inserted",      inserted)
        m2.metric("Duplicates Skipped", skipped)
        m3.metric("Row Errors",         len(row_errors))

        if inserted > 0:
            st.success(f"{inserted} rows saved for vessel {vname} to SQLite!")
        else:
            st.warning("No new rows inserted (all may be duplicates or errors).")

        if row_errors:
            with st.expander(f"{len(row_errors)} row error(s)", expanded=True):
                for err in row_errors:
                    st.warning(err)

        # ── Cleanup ───────────────────────────────────────────────────────
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

        st.session_state.sfm_inserted_file   = None
        st.session_state.sfm_final_mapping   = {}
        st.session_state.sfm_trigger_mapping = False
        st.session_state.trigger_mapping     = False
        st.session_state.pop("final_mapping", None)
        st.rerun()


# =============================================================================
#  MAIN VIEW
# =============================================================================

def _render_sfm_main(clear_downloads_func):
    """Full SQLite-backed Single File Manager view."""
    _sfm_init_state()

    # ── Import panel (collapsible) ────────────────────────────────────────
    _render_import_panel()

    st.divider()

    # ── Load vessels from DB ──────────────────────────────────────────────
    vessels = list_vessels()

    if not vessels:
        st.info(
            "No vessels in the database yet. "
            "Use the Import New Manifest panel above to get started."
        )
        return

    vessel_names = [v["name"] for v in vessels]

    # ── ① VESSEL SELECTOR ─────────────────────────────────────────────────
    selected_vessel_name = st.selectbox(
        "🚢 Select vessel",
        vessel_names,
        key="sfm_vessel_selector",
    )

    selected_vessel = next(
        (v for v in vessels if v["name"] == selected_vessel_name), None
    )

    if selected_vessel is None:
        st.warning("Could not find the selected vessel.")
        return

    vessel_id = selected_vessel["id"]

    # ── Inline rename for UNKNOWN vessels ─────────────────────────────────
    if selected_vessel_name == "UNKNOWN":
        st.warning(
            "⚠️ This vessel was imported without a name. "
            "Enter the correct name below and click Update Name."
        )
        col_name_in, col_name_btn = st.columns([3, 1])
        with col_name_in:
            new_vessel_name = st.text_input(
                "Vessel Name",
                value="",
                placeholder="e.g. MING ZHOU 8",
                key="sfm_rename_input",
                label_visibility="collapsed",
            )
        with col_name_btn:
            if st.button("✏️ Update Name", key="sfm_rename_btn", type="primary"):
                if new_vessel_name.strip():
                    ok = update_vessel_name(vessel_id, new_vessel_name.strip())
                    if ok:
                        st.success(
                            f"Vessel renamed to {new_vessel_name.strip()}"
                        )
                        st.rerun()
                    else:
                        st.error("Rename failed — vessel not found in DB.")
                else:
                    st.warning("Please enter a vessel name before updating.")

    # ── Load manifest lines ────────────────────────────────────────────────
    df_lines = load_manifest_for_vessel(selected_vessel_name)

    if df_lines.empty:
        st.warning(f"No manifest lines found for {selected_vessel_name}.")
        return

    display_cols = [c for c in df_lines.columns if c != "_db_id"]
    st.caption(
        f"{len(df_lines)} manifest lines — {selected_vessel_name} | "
        f"Escale: {selected_vessel.get('escale') or '—'} | "
        f"IMO: {selected_vessel.get('imo') or '—'}"
    )

    # ── Filter popover ─────────────────────────────────────────────────────
    with st.popover("🔍 Filter Table Options", use_container_width=True):
        filtered_df = df_lines[display_cols].copy()
        filter_cols_layout = st.columns(3)
        for i, column in enumerate(display_cols):
            unique_vals = df_lines[column].dropna().unique().tolist()
            if not unique_vals:
                continue
            with filter_cols_layout[i % 3]:
                sel = st.multiselect(
                    f"Filter {column}",
                    options=unique_vals,
                    default=[],
                    key=f"sfm_filter_{column}",
                )
            if sel:
                filtered_df = filtered_df[filtered_df[column].isin(sel)]

    filtered_df = filtered_df.reset_index(drop=True)

    # ── ② DATA TABLE VIEWER ───────────────────────────────────────────────
    try:
        edited_df = st.data_editor(
            filtered_df,
            num_rows="dynamic",
            key="sfm_data_editor",
            width="stretch",
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
    except Exception as exc:
        st.error(f"Data editor error: {exc}")
        edited_df = None

    # ── ③ ACTION BUTTONS ─────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)

    # --- Save Changes ---
    if col1.button("💾 Save Changes", key="sfm_btn_save"):
        if edited_df is not None:
            with st.spinner("Saving changes to SQLite..."):
                ins, errs = replace_vessel_lines(edited_df, vessel_id)
            if errs:
                st.warning(f"{len(errs)} row error(s) during save:")
                for e in errs:
                    st.caption(e)
            if ins > 0:
                st.toast(f"{ins} rows saved for {selected_vessel_name}!")
            else:
                st.warning("No rows were saved. Check errors above.")
            clear_downloads_func()
            st.rerun()
        else:
            st.error("Cannot save — data editor produced no data.")

    # --- Gen. Debarquement ---
    if col2.button("📋 Gen. Débarquement", key="sfm_btn_debarq"):
        if edited_df is not None:
            try:
                stem = selected_vessel_name.replace(" ", "_")
                generated_path = _run_generator(gen_table_deb, edited_df, stem)
                st.session_state.active_download = {
                    "path":  generated_path,
                    "label": "📥 Download Débarquement (Excel)",
                    "mime":  (
                        "application/vnd.openxmlformats-officedocument"
                        ".spreadsheetml.sheet"
                    ),
                }
                st.info("Débarquement table generated.")
            except Exception as exc:
                st.error(f"Gen. Débarquement failed: {exc}")

    # --- Gen. Borderaux ---
    if col3.button("📜 Gen. Borderaux", key="sfm_btn_brd"):
        if edited_df is not None:
            try:
                stem = selected_vessel_name.replace(" ", "_")
                generated_path = _run_generator(
                    lambda p: generate_brd(
                        p, sheet_name=0, template_name="template.docx"
                    ),
                    edited_df,
                    stem,
                )
                st.session_state.active_download = {
                    "path":  generated_path,
                    "label": "📥 Download Bordereau (Word)",
                    "mime":  (
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                }
                st.success("Bordereau generated!")
            except Exception as exc:
                st.error(f"Gen. Borderaux failed: {exc}")

    # --- Gen. Daily PVs ---
    if col4.button("📝 Gen. Daily PVs", key="sfm_btn_pvs"):
        if edited_df is not None:
            try:
                stem = selected_vessel_name.replace(" ", "_")
                generated_path = _run_generator(
                    generate_daily_pv, edited_df, stem
                )
                st.session_state.active_download = {
                    "path":  generated_path,
                    "label": f"📥 Download Daily PVs — {selected_vessel_name}",
                    "mime":  (
                        "application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"
                    ),
                }
                st.success("Daily PVs generated!")
            except Exception as exc:
                st.error(f"Gen. Daily PVs failed: {exc}")

    # --- Delete Vessel ---
    with col5:
        c1, c2 = st.columns([1, 2])
        with c1:
            confirm_del = st.checkbox(
                "Confirm",
                key="sfm_check_del",
                label_visibility="collapsed",
            )
        with c2:
            if st.button(
                "🗑️ Delete",
                key="sfm_btn_delete",
                type="secondary",
                disabled=not confirm_del,
            ):
                delete_vessel(vessel_id)
                st.toast(
                    f"Deleted {selected_vessel_name} and all its lines."
                )
                clear_downloads_func()
                st.rerun()

    # ── Persistent download button ─────────────────────────────────────────
    if st.session_state.get("active_download"):
        st.divider()
        file_info = st.session_state.active_download
        if os.path.exists(file_info["path"]):
            with open(file_info["path"], "rb") as fh:
                st.download_button(
                    label=file_info["label"],
                    data=fh.read(),
                    file_name=os.path.basename(file_info["path"]),
                    mime=file_info["mime"],
                    type="primary",
                    key="sfm_dl_button",
                )
        else:
            st.error("Generated file not found. Please regenerate.")

    # ── CSV download of current view ───────────────────────────────────────
    st.divider()
    csv_bytes = df_lines[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Current View (CSV)",
        data=csv_bytes,
        file_name=f"{selected_vessel_name}_manifest.csv",
        mime="text/csv",
        key="sfm_csv_dl",
    )
