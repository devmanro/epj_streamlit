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
)
from modules.json_to_excel import extract_to_excel_flattened as gen_excel


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def render_global_manager():
    st.subheader("🌍 Global Loading Dashboard")

    tab_sqlite, tab_excel = st.tabs([
        "🗄️ Import → SQLite DB",
        "📊 Excel DB (legacy)",
    ])

    with tab_sqlite:
        _render_sqlite_manager()

    with tab_excel:
        _render_excel_manager()


# ─────────────────────────────────────────────────────────────────────────────
#  SQLite Manager — full docGeneration flow + DB save
# ─────────────────────────────────────────────────────────────────────────────

def _clear_sqlite_upload():
    """Reset session state used by the SQLite import pipeline."""
    st.session_state.pop("sq_inserted_file",  None)
    st.session_state.pop("sq_final_mapping",  None)
    st.session_state.pop("trigger_mapping", None)


def _render_sqlite_manager():
    """
    Full import pipeline (mirrors docGeneration) but saves to SQLite instead
    of the legacy Excel database.

    Steps:
        1. Upload file  (xlsx / csv / json)
        2. Save file to UPLOAD_DIR (so mapping dialog can read it)
        3. Column-mapping dialog  (show_mapping_dialog)
        4. align_data()           (rename / reorder columns + AI cargo-type)
        5. clean_dataframe_types()
        6. import_manifest_to_db() → database.sqlite
        7. Show result metrics + per-row errors
        8. Browse / download vessels already in DB
    """

    # ── Session-state keys (prefixed sq_ to avoid collisions except trigger_mapping) ─
    if "sq_inserted_file"   not in st.session_state:
        st.session_state.sq_inserted_file   = None
    if "sq_final_mapping"   not in st.session_state:
        st.session_state.sq_final_mapping   = {}
    if "trigger_mapping" not in st.session_state:
        st.session_state.trigger_mapping = False
    if "sq_uploader_key"    not in st.session_state:
        st.session_state.sq_uploader_key    = 0

    st.markdown("### 📥 Import Manifest → SQLite Database")
    st.caption(
        "Upload a manifest file. You will be guided through column mapping, "
        "data alignment, and then the rows are saved permanently to SQLite."
    )

    # ── STEP 1 — Vessel metadata ─────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**① Vessel Information**")
        c1, c2, c3 = st.columns(3)
        vessel_name = c1.text_input(
            "Vessel Name (Leave blank to auto-extract)",
            placeholder="e.g. MING ZHOU 8",
            key="sq_vessel_name",
        )
        escale = c2.text_input(
            "Escale (optional)",
            placeholder="e.g. 2024/001",
            key="sq_escale",
        )
        imo = c3.text_input(
            "IMO (optional)",
            placeholder="e.g. 9876543",
            key="sq_imo",
        )

    # ── STEP 2 — File upload ─────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("**② Upload Manifest File**")
        uploaded = st.file_uploader(
            "Choose manifest (.xlsx / .csv / .json)",
            type=["xlsx", "csv", "json"],
            key=f"sq_uploader_{st.session_state.sq_uploader_key}",
            on_change=_clear_sqlite_upload,
        )

    # ── Save file to disk & trigger mapping dialog ───────────────────────────
    if uploaded and not st.session_state.sq_final_mapping:
        filename = uploaded.name

        if filename.endswith(".json"):
            # Convert JSON → Excel
            excel_name = filename.replace(".json", ".xlsx")
            save_path  = os.path.join(UPLOAD_DIR, excel_name)
            try:
                gen_excel(uploaded, save_path, st_upload=True)
                st.success(f"✅ JSON converted → {excel_name}")
                st.session_state.sq_inserted_file = excel_name
            except Exception as exc:
                st.error(f"❌ JSON conversion failed: {exc}")
                return
        else:
            save_path = os.path.join(UPLOAD_DIR, filename)
            try:
                with open(save_path, "wb") as fh:
                    fh.write(uploaded.getbuffer())
                st.success(f"✅ File saved: {filename}")
                st.session_state.sq_inserted_file = filename
            except Exception as exc:
                st.error(f"❌ Could not save file: {exc}")
                return

        # Increment uploader key so widget resets cleanly after mapping
        st.session_state.trigger_mapping = True
        st.session_state.sq_uploader_key   += 1

    # ── STEP 3 — Column-mapping dialog ───────────────────────────────────────
    inserted_file  = st.session_state.sq_inserted_file
    trigger        = st.session_state.trigger_mapping

    if inserted_file and trigger:
        file_path = os.path.join(UPLOAD_DIR, inserted_file)
        try:
            df_for_mapping = (
                pd.read_excel(file_path)
                if inserted_file.endswith((".xlsx", ".xls"))
                else pd.read_csv(file_path)
            )
        except Exception as exc:
            st.error(f"❌ Could not read saved file for mapping: {exc}")
            return

        with st.container(border=True):
            st.markdown("**③ Column Mapping**")
            st.info(
                "A mapping dialog will open. Match your file's columns "
                "to the database column names, then click **Confirm and Import**."
            )
        show_mapping_dialog(df_for_mapping)
        st.stop()

    # ── STEP 4 — align_data + clean + import to SQLite ───────────────────────
    if inserted_file and not trigger:
        st.session_state.trigger_mapping = False

        final_mp = st.session_state.get("sq_final_mapping", {}) \
                   or st.session_state.get("final_mapping", {})

        file_path = os.path.join(UPLOAD_DIR, inserted_file)

        # Load the raw file
        with st.spinner("Loading file…"):
            try:
                df_raw = (
                    pd.read_excel(file_path)
                    if inserted_file.endswith((".xlsx", ".xls"))
                    else pd.read_csv(file_path)
                )
            except Exception as exc:
                st.error(f"❌ Cannot read file '{inserted_file}': {exc}")
                _clear_sqlite_upload()
                return

        # ── align columns ─────────────────────────────────────────────────
        with st.spinner("Aligning columns and running cargo-type prediction…"):
            try:
                molded_df, success = align_data(df_raw, final_mp)
            except Exception as exc:
                st.error(f"❌ align_data() failed: {exc}")
                st.code(str(exc))
                _clear_sqlite_upload()
                return

        if not success:
            st.warning(
                "⚠️ Column alignment was skipped (too few mapped columns). "
                "The file will be imported as-is."
            )
            molded_df = df_raw

        # ── reindex to standard columns ───────────────────────────────────
        with st.spinner("Reindexing to standard schema…"):
            df_out = molded_df.reindex(columns=COLUMNS).fillna("-")
            mapped_target_cols = set(final_mp.values()) if final_mp else set()
            unmapped_cols = [
                col for col in df_out.columns if col not in mapped_target_cols
            ]
            try:
                df_clean = clean_dataframe_types(df_out, only_cols=unmapped_cols)
            except Exception as exc:
                st.warning(f"⚠️ clean_dataframe_types() raised: {exc}")
                df_clean = df_out

        # ── preview ───────────────────────────────────────────────────────
        with st.expander("🔍 Preview aligned data (first 20 rows)", expanded=False):
            st.dataframe(df_clean.head(20), use_container_width=True, hide_index=True)

        # ── validate and extract vessel metadata ──────────────────────────
        vname = st.session_state.get("sq_vessel_name", "").strip()
        escale = st.session_state.get("sq_escale", "").strip()
        imo = st.session_state.get("sq_imo", "").strip()

        def extract_first_valid(col_name):
            if col_name in df_clean.columns:
                valid = df_clean[col_name].replace(["-", "", "None", "nan"], pd.NA).dropna()
                if not valid.empty:
                    return str(valid.iloc[0]).strip()
            return ""

        if not vname: vname = extract_first_valid("NAVIRE")
        if not escale: escale = extract_first_valid("ESCALE")
        if not imo: imo = extract_first_valid("IMO_NAVIRE")

        if not vname:
            st.error(
                "❌ **Vessel Name is required.** "
                "Could not auto-extract from file. Please type it in the Vessel Name field above and re-upload the file."
            )
            _clear_sqlite_upload()
            return

        # ── import to SQLite ──────────────────────────────────────────────
        with st.spinner(f"Saving {len(df_clean)} rows to SQLite…"):
            try:
                inserted, skipped, row_errors = import_manifest_to_db(
                    df_clean,
                    vessel_name=vname,
                    escale=escale or None,
                    imo=imo or None,
                )
            except Exception as exc:
                st.error(f"❌ import_manifest_to_db() failed: {exc}")
                st.code(str(exc))
                _clear_sqlite_upload()
                return

        # ── results ───────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("### 📊 Import Result")
        m1, m2, m3 = st.columns(3)
        m1.metric("✅ Rows Inserted",        inserted)
        m2.metric("⏭️ Duplicates Skipped",   skipped)
        m3.metric("❌ Row Errors",           len(row_errors))

        if inserted > 0:
            st.success(
                f"✅ **{inserted}** rows saved for vessel **{vname}** to SQLite!"
            )
        else:
            st.warning("No new rows were inserted (all may be duplicates or errors).")

        if row_errors:
            st.markdown("#### ⚠️ Row-level Errors")
            with st.expander(f"Show {len(row_errors)} row error(s)", expanded=True):
                for err in row_errors:
                    st.warning(err)

        # ── clean up session state ────────────────────────────────────────
        # Remove the temp file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        # Reset pipeline state
        st.session_state.sq_inserted_file   = None
        st.session_state.sq_final_mapping   = {}
        st.session_state.trigger_mapping = False
        st.session_state.final_mapping      = {}   # shared key used by show_mapping_dialog

    # ═════════════════════════════════════════════════════════════════════════
    #  BROWSE VESSELS ALREADY IN DB
    # ═════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### 🚢 Vessels in SQLite Database")

    vessels = list_vessels()
    if not vessels:
        st.info("No vessels in the database yet. Import a manifest above to get started.")
        return

    vessels_df = pd.DataFrame(vessels)
    vessels_df.columns = ["ID", "Vessel", "Escale", "IMO", "Arrival Date", "Lines"]
    st.dataframe(vessels_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 🔍 Browse Manifest Lines")

    vessel_names    = [v["name"] for v in vessels]
    selected_vessel = st.selectbox(
        "Select a vessel to inspect",
        vessel_names,
        key="sqlite_vessel_sel",
    )

    if selected_vessel:
        df_lines = load_manifest_for_vessel(selected_vessel)
        if df_lines.empty:
            st.warning("No lines found for this vessel.")
        else:
            st.caption(f"{len(df_lines)} manifest lines for **{selected_vessel}**")
            display_cols = [c for c in df_lines.columns if c != "_db_id"]
            st.dataframe(df_lines[display_cols], use_container_width=True, hide_index=True)

            csv_bytes = df_lines[display_cols].to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download as CSV",
                data=csv_bytes,
                file_name=f"{selected_vessel}_manifest.csv",
                mime="text/csv",
            )

    st.divider()

    with st.expander("🗑️ Delete a Vessel from DB (irreversible)"):
        del_name = st.selectbox("Vessel to delete", vessel_names, key="sqlite_del_sel")
        sel_id   = next((v["id"] for v in vessels if v["name"] == del_name), None)
        if st.button("🗑️ Delete Vessel + All Lines", type="secondary", key="sqlite_del_btn"):
            if sel_id is not None:
                delete_vessel(sel_id)
                st.success(f"Deleted vessel '{del_name}' and all its manifest lines.")
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  Legacy Excel Manager  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _render_excel_manager():

    df = getDB()

    st.write("### 🔍 Advanced Filters")

    with st.expander("Filter Options (Click to expand)", expanded=False):
        filtered_df = df.copy()
        cols = st.columns(3)

        for i, column in enumerate(df.columns):
            if column == "_select":
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
            "NAVIRE":          st.column_config.TextColumn("🚢 Navire",        width="small"),
            "B/L":             st.column_config.TextColumn("📄 B/L",           width="medium"),
            "DESIGNATION":     st.column_config.TextColumn("📦 Désignation",   width="large"),
            "QUANTITE":        st.column_config.NumberColumn("🔢 Quantité",    format="%d",    width="small"),
            "TONAGE":          st.column_config.NumberColumn("⚖️ Tonnage",     format="%.2f T", width="small"),
            "CLIENT":          st.column_config.TextColumn("👤 Client",        width="medium"),
            "CHASSIS/SERIAL":  st.column_config.TextColumn("🔧 Chassis/Serial", width="medium"),
        },
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("💾 Save Global Changes to Database"):
            try:
                edited_df.to_excel(DB_PATH, index=False)
                st.success("Database updated successfully!")
            except Exception as e:
                st.error(f"Save failed: {e}")

    with col_b:
        csv = edited_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Current View (CSV)",
            data=csv,
            file_name="filtered_database.csv",
            mime="text/csv",
        )
