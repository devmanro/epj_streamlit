# bl_tracking.py
# Lightweight tracking UI for "Landed" / "Received" operations
# Integrates into your existing Streamlit app without touching your upload logic.

from __future__ import annotations

from pathlib import Path
from datetime import datetime, date
from typing import Optional, List

import pandas as pd
import streamlit as st

import os
from assets.constants.constants import UPLOAD_DIR, DEFAULT_LOCATIONS, DEFAULT_OPS_LOG_PATH


# -----------------------------
# Configuration
# -----------------------------
REQUIRED_COLUMNS = [
    "NAVIRE",
    "DATE",
    "B/L",
    "DESIGNATION",
    "QUANTITE",
    "TONAGE",
    "CLIENT",
    "CHASSIS/SERIAL",
    "RESTE T/P",
    "TYPE",
    "SITUATION",
    "OBSERVATION",
    "POSITION",
    "TRANSIT",
    "CLES",
    "SURFACE",
    "DAEMO BREAKER (DRB) TOP BOX TYPE",
    "DATE ENLEV"
]


# -----------------------------
# Storage helpers
# -----------------------------

def _ensure_ops_log(ops_log_path: Path) -> Path:
    # Handle empty or None path - use default
    if not ops_log_path or (isinstance(ops_log_path, Path) and not str(ops_log_path).strip()):
        ops_log_path = DEFAULT_OPS_LOG_PATH

    # Ensure it's a Path object
    if not isinstance(ops_log_path, Path):
        ops_log_path = Path(ops_log_path)

    ops_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Define required columns
    required_cols = [
        "NAVIRE", "B/L", "OP_DATE", "LOCATION",
        "QUANTITE", "TONAGE", "CHASSIS/SERIAL", "REMARKS", "CREATED_AT"
    ]

    # If file doesn't exist, create it with headers
    if not ops_log_path.exists():
        pd.DataFrame(columns=required_cols).to_csv(
            ops_log_path, index=False, encoding="utf-8-sig")
    else:
        # File exists - check if it has headers
        try:
            df = pd.read_csv(ops_log_path, encoding="utf-8-sig", nrows=0)
            # If we get here, file has headers, check if they're correct
            if not all(col in df.columns for col in required_cols):
                # Headers are missing or incorrect, recreate with headers only
                pd.DataFrame(columns=required_cols).to_csv(
                    ops_log_path, index=False, encoding="utf-8-sig")
        except (pd.errors.EmptyDataError, Exception):
            # File exists but has no headers or is corrupted, create with headers only
            pd.DataFrame(columns=required_cols).to_csv(
                ops_log_path, index=False, encoding="utf-8-sig")
    
    return ops_log_path


def read_ops_log(ops_log_path: Path = DEFAULT_OPS_LOG_PATH) -> pd.DataFrame:
    _ensure_ops_log(ops_log_path)
    df = pd.read_csv(ops_log_path, encoding="utf-8-sig")
    if not df.empty:
        if "OP_DATE" in df.columns:
            df["OP_DATE"] = pd.to_datetime(df["OP_DATE"], errors="coerce")
        for c in ["QUANTITE", "TONAGE"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        # Normalize key fields
        if "B/L" in df.columns:
            df["B/L"] = df["B/L"].astype(str)
        if "NAVIRE" in df.columns:
            df["NAVIRE"] = df["NAVIRE"].astype(str)
    return df


def append_op_row(row: dict, ops_log_path: Path = DEFAULT_OPS_LOG_PATH) -> None:
    
    df = read_ops_log(ops_log_path)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(ops_log_path, index=False, encoding="utf-8-sig")


# -----------------------------
# Business helpers
# -----------------------------
def _validate_manifest_df(manifest_df: pd.DataFrame) -> list[str]:
    if manifest_df is None or manifest_df.empty:
        return ["Manifest DataFrame is empty."]
    missing = [c for c in REQUIRED_COLUMNS if c not in manifest_df.columns]
    return missing


def _prep_manifest_df(manifest_df: pd.DataFrame) -> pd.DataFrame:
    df = manifest_df.copy()
    # Normalize columns that we rely on
    if "B/L" in df.columns:
        df["B/L"] = df["B/L"].astype(str)
    if "NAVIRE" in df.columns:
        df["NAVIRE"] = df["NAVIRE"].astype(str)
    for c in ["QUANTITE", "TONAGE"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in ["DATE", "DATE ENLEV"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def _filter_ops_by_day(ops_df: pd.DataFrame, navire: str, the_date: date) -> pd.DataFrame:
    if ops_df.empty:
        return ops_df
    df = ops_df.copy()
    df["OP_DATE_ONLY"] = df["OP_DATE"].dt.date
    if navire:
        df = df[df["NAVIRE"] == navire]
    return df[df["OP_DATE_ONLY"] == the_date].drop(columns=["OP_DATE_ONLY"])


# -----------------------------
# Main render function (call from your app)
# -----------------------------
# -----------------------------
# Main render function (call from your app)
# -----------------------------
def render_tracking_ui(
    manifest_df: pd.DataFrame,
    default_navire: Optional[str] = None,
    ops_log_path: Path = DEFAULT_OPS_LOG_PATH,
    locations: Optional[List[str]] = None,
    key_prefix: str = "blt_",
):
    """
    Render the Landing / Received tracking UI inside your app.

    Workflow
    --------
    1.  Select file → NAVIRE → B/L.
    2.  Choosing B/L or toggling Landed / Received **auto-fills** Quantity
        and Tonnage from the manifest (editable before adding).
    3.  Click **Add to pending** → row goes into a virtual temporary table
        shown as an editable ``st.data_editor``.
    4.  Edit / delete rows freely in the temp table.
    5.  Click **Update – Save all to log** → every pending row is appended
        to the operations CSV and the temp table is cleared.

    Returns
    -------
    dict  with keys ``ops_df``, ``summary_df``, ``selected_navire``.
    """

    # Columns used by the virtual temp table
    TEMP_COLS = [
        "NAVIRE", "B/L", "OP_DATE",
        "LANDED_QTY",
        "RECEIVED_QTY",
        "LANDED_TON",
        "LOCATION", "CHASSIS/SERIAL", "REMARKS",
    ]

    # ── session-state initialisation ────────────────────────────────
    temp_key = f"{key_prefix}temp_ops"
    editor_ver_key = f"{key_prefix}editor_ver"
    prev_nav_key = f"{key_prefix}prev_navire"
    prev_file_key = f"{key_prefix}prev_file"

    if temp_key not in st.session_state:
        st.session_state[temp_key] = pd.DataFrame(columns=TEMP_COLS)
    if editor_ver_key not in st.session_state:
        st.session_state[editor_ver_key] = 0

    _empty = {"ops_df": pd.DataFrame(), "summary_df": pd.DataFrame(),
              "selected_navire": None}

    # ── File selection ──────────────────────────────────────────────
    files = os.listdir(UPLOAD_DIR) if os.path.exists(UPLOAD_DIR) else []
    if not files:
        st.warning("No files found in upload directory. "
                   "Please upload a file first.")
        return _empty

    default_index = 0
    if (st.session_state.get("selected_file")
            and st.session_state.selected_file in files):
        default_index = files.index(st.session_state.selected_file)

    selected_file = st.selectbox(
        "Select a ship file to operate on:",
        files,
        index=default_index,
        key=f"{key_prefix}file_selector",
    )
    st.session_state.selected_file = selected_file
    file_path = os.path.join(UPLOAD_DIR, selected_file)

    # Reset temp table when the file changes
    if st.session_state.get(prev_file_key) != selected_file:
        st.session_state[prev_file_key] = selected_file
        st.session_state[temp_key] = pd.DataFrame(columns=TEMP_COLS)
        st.session_state[editor_ver_key] += 1

    # ── Load manifest ───────────────────────────────────────────────
    manifest_df = None
    try:
        if selected_file.endswith(".xlsx"):
            manifest_df = pd.read_excel(file_path)
        elif selected_file.endswith(".csv"):
            manifest_df = pd.read_csv(file_path)
        else:
            st.error(f"Unsupported file format: {selected_file}")
            return _empty
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return _empty

    missing = _validate_manifest_df(manifest_df)
    if missing:
        st.error(f"Tracking disabled – manifest missing columns: {missing}")
        return _empty

    manifest_df = _prep_manifest_df(manifest_df)
    ops_df = read_ops_log(ops_log_path)
    locations = locations or DEFAULT_LOCATIONS

    # ── NAVIRE selection ────────────────────────────────────────────
    navires = sorted(manifest_df["NAVIRE"].dropna().astype(str).unique())
    if not navires:
        st.warning("No NAVIRE values found in the manifest.")
        return {"ops_df": ops_df, "summary_df": pd.DataFrame(),
                "selected_navire": None}

    nav_idx = navires.index(default_navire) if default_navire in navires else 0
    selected_navire = st.selectbox(
        "Select NAVIRE (ship)",
        navires,
        index=nav_idx,
        key=f"{key_prefix}navire_select",
    )

    # B/L list for chosen navire
    bls = sorted(
        manifest_df[manifest_df["NAVIRE"] == selected_navire]["B/L"]
        .dropna().astype(str).unique()
    )

    # ── helper: manifest qty & ton for a given B/L ──────────────────
    def _get_manifest_MV(bl_number: str, manifested: bool = False):
        rows = manifest_df[
            (manifest_df["NAVIRE"] == selected_navire)
            & (manifest_df["B/L"] == str(bl_number))
        ]

        if manifested:
            qty = int(rows.get("QUANTITE", pd.Series()).sum() or 0)
            ton = float(rows.get("TONAGE", pd.Series()).sum() or 0.0)
        else:
            qty = int(rows.get("LANDED_QTY", pd.Series()).sum() or 0)
            ton = int(rows.get("LANDED_TON", pd.Series()).sum() or 0.0)

        return qty, ton

    def _clear_item_fields():
        st.session_state[f"{key_prefix}chs_in"] = ""
        st.session_state[f"{key_prefix}remarks"] = ""
        st.session_state[f"{key_prefix}landed_qty"] = 0
        st.session_state[f"{key_prefix}received_qty"] = 0
        st.session_state[f"{key_prefix}loc"] = locations[0] if locations else ""
        st.session_state[f"{key_prefix}ton"] = 0.0
        st.session_state[f"{key_prefix}bl_select"] = bls[0] if bls else ""
        st.session_state[f"{key_prefix}loc_other"] = ""


    # ── callback: auto-populate qty / ton from manifest ─────────────
    def _on_bl_or_op_change():
        bl = st.session_state.get(f"{key_prefix}bl_select")
        if bl:
            q, t = _get_manifest_MV(bl)
            st.session_state[f"{key_prefix}landed_qty"] = q
            st.session_state[f"{key_prefix}received_qty"] = 0
            st.session_state[f"{key_prefix}ton"] = t

    # ── detect NAVIRE change → reset qty / ton ──────────────────────
    if st.session_state.get(prev_nav_key) != selected_navire:
        st.session_state[prev_nav_key] = selected_navire
        if bls:
            q, t = _get_manifest_MV(bls[0])
            st.session_state[f"{key_prefix}landed_qty"] = q
            st.session_state[f"{key_prefix}received_qty"] = 0
            st.session_state[f"{key_prefix}ton"] = t
        else:
            st.session_state[f"{key_prefix}landed_qty"] = 0
            st.session_state[f"{key_prefix}received_qty"] = 0
            st.session_state[f"{key_prefix}ton"] = 0.0

    # ── Tabs ────────────────────────────────────────────────────────
    tab1, tab2 = st.tabs(["Daily follow-up", "Summary / Export"])

    # ================================================================
    # TAB 1 – input widgets  +  temp table  +  daily log
    # ================================================================
    with tab1:

        # -------- reactive input widgets (no form) ------------------
        st.subheader("➕ Add operation")

        c1, c2, c3 = st.columns(3)

        with c1:
            selected_bl = st.selectbox(
                "B/L", bls,
                key=f"{key_prefix}bl_select",
                on_change=_on_bl_or_op_change,
            )
            landed_qty = st.number_input(
                "Landed Quantity", min_value=0, step=1,
                key=f"{key_prefix}landed_qty",
            )

        with c2:
            op_date = st.date_input(
                "Operation date",
                value=date.today(),
                key=f"{key_prefix}op_date",
            )

            received_qty = st.number_input(
                "Received Quantity", min_value=0, step=1,
                key=f"{key_prefix}received_qty",
            )

        with c3:
            ton = st.number_input(
                "Tonnage", min_value=0.0, step=0.001, format="%.3f",
                key=f"{key_prefix}ton",
            )
            loc = st.selectbox(
                "Location", locations,
                key=f"{key_prefix}loc",
            )

        if loc == "Other":
            loc_other = st.text_input(
                "Enter custom location",
                key=f"{key_prefix}loc_other",
            )
            if loc_other.strip():
                loc = loc_other.strip()

        chs = st.text_input(
            "Chassis / Serial (optional)",
            key=f"{key_prefix}chs_in",
        )
        remarks = st.text_area(
            "Remarks (optional)", height=60,
            key=f"{key_prefix}remarks",
        )

        # Show manifest reference so the user sees what the source says
        if selected_bl:
            mq, mt = _get_manifest_MV(selected_bl, True)

            st.caption(
                f"📦 Manifest reference for **{selected_bl}**: "
                f"Qty = **{mq}**,  Tonnage = **{mt:.3f}**"
            )

        def _add_pending():
            if not selected_bl:
                st.warning("No B/L selected.")
            elif loc == "Other":
                st.warning("Please type a custom location name.")
            else:
                # Read current values from session_state instead of using outer scope variables
                current_landed_qty = st.session_state.get(
                    f"{key_prefix}landed_qty", 0)
                current_received_qty = st.session_state.get(
                    f"{key_prefix}received_qty", 0)
                current_ton = st.session_state.get(f"{key_prefix}ton", 0.0)
                current_op_date = st.session_state.get(
                    f"{key_prefix}op_date", date.today())
                current_loc = st.session_state.get(f"{key_prefix}loc", "")
                current_chs = st.session_state.get(f"{key_prefix}chs_in", "")
                current_remarks = st.session_state.get(
                    f"{key_prefix}remarks", "")
                current_bl = st.session_state.get(
                    f"{key_prefix}bl_select", selected_bl)

                new_row = {
                    "NAVIRE":         selected_navire,
                    "B/L":            str(current_bl),
                    "OP_DATE":        current_op_date.isoformat() if isinstance(current_op_date, date) else current_op_date,
                    "LANDED_QTY":     int(current_landed_qty),
                    "RECEIVED_QTY":   int(current_received_qty),
                    "LANDED_TON":     float(current_ton),
                    "LOCATION":       current_loc,
                    "CHASSIS/SERIAL": current_chs,
                    "REMARKS":        current_remarks,
                }
                st.session_state[temp_key] = pd.concat(
                    [st.session_state[temp_key], pd.DataFrame([new_row])],
                    ignore_index=True,
                )
            _clear_item_fields()
            st.session_state[editor_ver_key] += 1

        st.button(
            "➕ Add to pending operations",
            key=f"{key_prefix}add_pending",
            on_click=_add_pending,
        )

        # -------- virtual pending-operations table ------------------
        st.divider()
        pending = st.session_state[temp_key]

        if not pending.empty:
            st.subheader(
                "make sure to include a checker for data where it checks if qty is less or equal to manifest (for landed and received) ")
            st.subheader(f"📋 Pending Operations  ({len(pending)} row"
                         f"{'s' if len(pending) != 1 else ''})")
            st.caption(
                "✏️ Edit any cell directly.  Delete rows with the "
                "checkbox.  Nothing is saved until you click "
                "**Update – Save all**."
            )

            edited_df = st.data_editor(
                pending,
                num_rows="dynamic",
                width='stretch',
                key=(f"{key_prefix}temp_editor_"
                     f"{st.session_state[editor_ver_key]}"),
            )
            # Keep session state in sync with editor edits
            st.session_state[temp_key] = edited_df

            col_save, col_clear = st.columns(2)

            with col_save:
                if st.button(
                    "✅ Update – Save all to log",
                    type="primary",
                    key=f"{key_prefix}save_all",
                ):
                    saved = 0
                    for _, row in edited_df.iterrows():
                        op_row = row.to_dict()
                        # Normalise date to ISO string
                        try:
                            op_row["OP_DATE"] = datetime.combine(
                                pd.to_datetime(op_row["OP_DATE"]).date(),
                                datetime.min.time(),
                            ).isoformat()
                        except Exception:
                            pass
                        op_row["CREATED_AT"] = (
                            datetime.now().isoformat(timespec="seconds")
                        )
                        append_op_row(op_row, ops_log_path=ops_log_path)
                        saved += 1

                    # Clear temp table
                    st.session_state[temp_key] = pd.DataFrame(
                        columns=TEMP_COLS
                    )
                    st.session_state[editor_ver_key] += 1
                    st.success(f"✅ {saved} operation(s) committed to log!")
                    st.rerun()

            with col_clear:
                if st.button("🗑️ Clear all pending",
                             key=f"{key_prefix}clear_pending"):
                    st.session_state[temp_key] = pd.DataFrame(
                        columns=TEMP_COLS
                    )
                    st.session_state[editor_ver_key] += 1
                    st.rerun()
        else:
            st.info(
                "No pending operations. Use the inputs above to add "
                "entries, then click **Add to pending operations**."
            )

    # ================================================================
    # TAB 2 – Summary / Export  (unchanged logic)
    # ================================================================
    with tab2:
        # -------- global summary log -------------------------------
        st.subheader("Summary for selected NAVIRE")

        # Filter controls in columns
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        with filter_col1:
            # Get unique client names from manifest for selected navire
            navire_manifest = manifest_df[manifest_df["NAVIRE"] == selected_navire].copy(
            )
            client_options = ["All"]
            if not navire_manifest.empty and "CLIENT" in navire_manifest.columns:
                client_options.extend(
                    sorted(navire_manifest["CLIENT"].dropna().astype(
                        str).unique().tolist())
                )

            selected_client = st.selectbox(
                "Client Name",
                client_options,
                key=f"{key_prefix}client_filter",
            )

        with filter_col2:
            # Get unique commodity types from manifest for selected navire
            navire_manifest = manifest_df[manifest_df["NAVIRE"] == selected_navire].copy(
            )
            commodity_types = ["All"]
            if not navire_manifest.empty and "TYPE" in navire_manifest.columns:
                commodity_types.extend(
                    sorted(navire_manifest["TYPE"].dropna().astype(
                        str).unique().tolist())
                )

            selected_commodity = st.selectbox(
                "Commodity Type",
                commodity_types,
                key=f"{key_prefix}commodity_filter",
            )

        with filter_col3:
            # Get unique B/Ls from ops for selected navire
            navire_ops = ops_df[ops_df["NAVIRE"] == selected_navire].copy()
            bl_options = ["All"]
            if not navire_ops.empty:
                bl_options.extend(
                    sorted(
                        navire_ops["B/L"].dropna().astype(str).unique().tolist())
                )

            selected_bl_filter = st.selectbox(
                "B/L",
                bl_options,
                key=f"{key_prefix}bl_filter",
            )

        # Filter operations by navire (no day filter anymore)
        navire_ops = ops_df[ops_df["NAVIRE"] == selected_navire].copy()
        daily_ops = navire_ops

        # Join with manifest to get commodity type and client information
        if not daily_ops.empty and not manifest_df.empty:
            # Merge to get TYPE, DESIGNATION, and CLIENT from manifest
            daily_ops = daily_ops.merge(
                manifest_df[["B/L", "TYPE", "DESIGNATION", "CLIENT"]
                            ].drop_duplicates(subset=["B/L"]),
                on="B/L",
                how="left"
            )

            # Apply client filter
            if selected_client != "All":
                daily_ops = daily_ops[
                    daily_ops["CLIENT"].astype(str) == str(selected_client)
                ]

            # Apply commodity type filter
            if selected_commodity != "All":
                daily_ops = daily_ops[
                    daily_ops["TYPE"].astype(str) == str(selected_commodity)
                ]

            # Apply B/L filter
            if selected_bl_filter != "All":
                daily_ops = daily_ops[
                    daily_ops["B/L"].astype(str) == str(selected_bl_filter)
                ]

        if daily_ops.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Landed qty", 0)
            c2.metric("Received qty", 0)
            c3.metric("Balance (landed - received)", 0)
            st.info("No committed operations for the selected filters.")
        else:
            # Determine operation type from LANDED_QTY and RECEIVED_QTY if OPERATION column doesn't exist
            if "OPERATION" not in daily_ops.columns:
                # Create OPERATION column based on which quantity is non-zero
                daily_ops["OPERATION"] = daily_ops.apply(
                    lambda row: "Landed" if row.get("LANDED_QTY", 0) > 0
                    else ("Received" if row.get("RECEIVED_QTY", 0) > 0 else "Unknown"),
                    axis=1
                )
                # Use QUANTITE if available, otherwise derive from LANDED_QTY/RECEIVED_QTY
                if "QUANTITE" not in daily_ops.columns:
                    daily_ops["QUANTITE"] = daily_ops.apply(
                        lambda row: row.get("LANDED_QTY", 0) if row["OPERATION"] == "Landed"
                        else row.get("RECEIVED_QTY", 0),
                        axis=1
                    )

            landed_qty = daily_ops.loc[
                daily_ops["OPERATION"] == "Landed", "QUANTITE"
            ].sum()
            received_qty = daily_ops.loc[
                daily_ops["OPERATION"] == "Received", "QUANTITE"
            ].sum()
            balance_qty = landed_qty - received_qty

            c1, c2, c3 = st.columns(3)
            c1.metric("Landed qty",  int(landed_qty))
            c2.metric("Received qty", int(received_qty))
            c3.metric("Balance (landed − received)", int(balance_qty))

            show_cols = [
                "B/L", "OP_DATE",
                "RECEIVED_QTY",
                "LOCATION", "CHASSIS/SERIAL",
                "REMARKS", "LANDED_QTY", "CREATED_AT",
            ]
            # Add CLIENT, TYPE and DESIGNATION to display if available
            if "CLIENT" in daily_ops.columns:
                show_cols.insert(3, "CLIENT")
            if "TYPE" in daily_ops.columns:
                show_cols.insert(4, "TYPE")
            if "DESIGNATION" in daily_ops.columns:
                show_cols.insert(5, "DESIGNATION")

             # Filter show_cols to only include columns that actually exist in daily_ops
            show_cols = [col for col in show_cols if col in daily_ops.columns]

            # Ensure OP_DATE is formatted properly if it exists
            if "OP_DATE" in daily_ops.columns and not daily_ops.empty:
                # Convert OP_DATE to datetime if it's not already
                if not pd.api.types.is_datetime64_any_dtype(daily_ops["OP_DATE"]):
                    daily_ops["OP_DATE"] = pd.to_datetime(
                        daily_ops["OP_DATE"], errors="coerce")
        
                # Format for display, handling NaT values
                daily_ops["OP_DATE"] = daily_ops["OP_DATE"].apply(
                    lambda x: x.strftime("%Y-%m-%d") if pd.notna(x) else ""
                )



            st.dataframe(
                daily_ops[show_cols].sort_values(
                    ["OP_DATE", "B/L"]
                ),
                use_container_width=True,
            )
