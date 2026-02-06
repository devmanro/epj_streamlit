# bl_tracking.py
# Lightweight tracking UI for "Landed" / "Received" operations
# Integrates into your existing Streamlit app without touching your upload logic.

from __future__ import annotations

from pathlib import Path
from datetime import datetime, date
from typing import Optional, List

import pandas as pd
import streamlit as st


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

DEFAULT_LOCATIONS = [
    "Quay",
    "Hangar",
    "Air area",
    "Yard A",
    "Yard B",
    "Warehouse 1",
    "Warehouse 2",
    "Other"
]

DEFAULT_OPS_LOG_PATH = Path("data/ops_log.csv")


# -----------------------------
# Storage helpers
# -----------------------------
def _ensure_ops_log(ops_log_path: Path) -> None:
    ops_log_path.parent.mkdir(parents=True, exist_ok=True)
    if not ops_log_path.exists():
        cols = [
            "NAVIRE", "B/L", "OP_DATE", "OPERATION", "LOCATION",
            "QUANTITE", "TONAGE", "CHASSIS/SERIAL", "REMARKS", "CREATED_AT"
        ]
        pd.DataFrame(columns=cols).to_csv(ops_log_path, index=False, encoding="utf-8-sig")


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


def build_summary(manifest_df: pd.DataFrame, ops_df: pd.DataFrame, navire: str) -> pd.DataFrame:
    man = manifest_df[manifest_df["NAVIRE"] == navire].copy()
    if man.empty:
        return pd.DataFrame()

    # Aggregate manifest per B/L
    agg = man.groupby("B/L", as_index=False).agg({
        "QUANTITE": "sum",
        "TONAGE": "sum",
        "CLIENT": "first",
        "DESIGNATION": lambda x: " | ".join(pd.Series(x).dropna().astype(str).unique())
    }).rename(columns={
        "QUANTITE": "MANIFEST_QTY",
        "TONAGE": "MANIFEST_TON"
    })

    if ops_df.empty:
        agg["LANDED_QTY"] = 0
        agg["LANDED_TON"] = 0.0
        agg["RECEIVED_QTY"] = 0
        agg["RECEIVED_TON"] = 0.0
        agg["TO_LAND_QTY"] = agg["MANIFEST_QTY"]
        agg["TO_LAND_TON"] = agg["MANIFEST_TON"]
        agg["TO_RECEIVE_QTY"] = 0
        agg["TO_RECEIVE_TON"] = 0.0
        return agg[[
            "B/L", "CLIENT", "DESIGNATION",
            "MANIFEST_QTY", "MANIFEST_TON",
            "LANDED_QTY", "LANDED_TON",
            "RECEIVED_QTY", "RECEIVED_TON",
            "TO_LAND_QTY", "TO_LAND_TON",
            "TO_RECEIVE_QTY", "TO_RECEIVE_TON"
        ]]

    ops_navire = ops_df[ops_df["NAVIRE"] == navire].copy()

    landed = ops_navire[ops_navire["OPERATION"] == "Landed"].groupby("B/L", as_index=False).agg({
        "QUANTITE": "sum",
        "TONAGE": "sum"
    }).rename(columns={"QUANTITE": "LANDED_QTY", "TONAGE": "LANDED_TON"})

    received = ops_navire[ops_navire["OPERATION"] == "Received"].groupby("B/L", as_index=False).agg({
        "QUANTITE": "sum",
        "TONAGE": "sum"
    }).rename(columns={"QUANTITE": "RECEIVED_QTY", "TONAGE": "RECEIVED_TON"})

    out = agg.merge(landed, on="B/L", how="left").merge(received, on="B/L", how="left")
    for c in ["LANDED_QTY", "LANDED_TON", "RECEIVED_QTY", "RECEIVED_TON"]:
        out[c] = out[c].fillna(0)

    out["TO_LAND_QTY"] = (out["MANIFEST_QTY"] - out["LANDED_QTY"]).clip(lower=0)
    out["TO_LAND_TON"] = (out["MANIFEST_TON"] - out["LANDED_TON"]).clip(lower=0)
    out["TO_RECEIVE_QTY"] = (out["LANDED_QTY"] - out["RECEIVED_QTY"]).clip(lower=0)
    out["TO_RECEIVE_TON"] = (out["LANDED_TON"] - out["RECEIVED_TON"]).clip(lower=0)

    return out[[
        "B/L", "CLIENT", "DESIGNATION",
        "MANIFEST_QTY", "MANIFEST_TON",
        "LANDED_QTY", "LANDED_TON",
        "RECEIVED_QTY", "RECEIVED_TON",
        "TO_LAND_QTY", "TO_LAND_TON",
        "TO_RECEIVE_QTY", "TO_RECEIVE_TON"
    ]]


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
def render_tracking_ui(
    manifest_df: pd.DataFrame,
    default_navire: Optional[str] = None,
    ops_log_path: Path = DEFAULT_OPS_LOG_PATH,
    locations: Optional[List[str]] = None,
    key_prefix: str = "blt_",
):
    """
    Render the Landing / Received tracking UI inside your app.
    - manifest_df: the DataFrame you already loaded (must contain REQUIRED_COLUMNS).
    - default_navire: optional navire pre-selection.
    - ops_log_path: CSV file used to store operations.
    - locations: optional list of location names (falls back to DEFAULT_LOCATIONS).
    - key_prefix: streamlit key prefix to avoid collisions.

    Returns: dict with "ops_df", "summary_df", "selected_navire".
    """

    # Validate and prep manifest
    missing = _validate_manifest_df(manifest_df)
    if missing:
        st.error(f"Tracking disabled. Manifest missing required columns: {missing}")
        return {"ops_df": pd.DataFrame(), "summary_df": pd.DataFrame(), "selected_navire": None}

    manifest_df = _prep_manifest_df(manifest_df)
    ops_df = read_ops_log(ops_log_path)
    locations = locations or DEFAULT_LOCATIONS

    # NAVIRE selection
    navires = sorted(manifest_df["NAVIRE"].dropna().astype(str).unique())
    if not navires:
        st.warning("No NAVIRE values found in the manifest.")
        return {"ops_df": ops_df, "summary_df": pd.DataFrame(), "selected_navire": None}

    if default_navire in navires:
        nav_idx = navires.index(default_navire)
    else:
        nav_idx = 0

    selected_navire = st.selectbox(
        "Select NAVIRE (ship)",
        navires,
        index=nav_idx,
        key=f"{key_prefix}navire_select",
    )

    # B/L list for selected NAVIRE
    bls = sorted(
        manifest_df[manifest_df["NAVIRE"] == selected_navire]["B/L"].dropna().astype(str).unique()
    )

    # Tabs within the tracking UI
    tab1, tab2 = st.tabs(["Daily follow-up", "Summary / Export"])

    with tab1:
        st.subheader("Add operation")
        with st.form(key=f"{key_prefix}op_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                selected_bl = st.selectbox("B/L", bls, key=f"{key_prefix}bl_select")
                op_type = st.radio("Operation", ["Landed", "Received"], horizontal=True, key=f"{key_prefix}op_type")
            with c2:
                op_date = st.date_input("Operation date", value=date.today(), key=f"{key_prefix}op_date")
                qty = st.number_input("Quantity", min_value=0, step=1, value=0, key=f"{key_prefix}qty")
            with c3:
                ton = st.number_input("Tonnage", min_value=0.0, step=0.001, value=0.0, format="%.3f", key=f"{key_prefix}ton")
                loc = st.selectbox("Location", locations, key=f"{key_prefix}loc")

            if loc == "Other":
                loc_other = st.text_input("Enter custom location", key=f"{key_prefix}loc_other")
                if loc_other.strip():
                    loc = loc_other.strip()

            chs = st.text_input("Chassis/Serial (optional)", value="", key=f"{key_prefix}chs")
            remarks = st.text_area("Remarks (optional)", value="", height=60, key=f"{key_prefix}remarks")

            submitted = st.form_submit_button("Save operation")
            if submitted:
                row = {
                    "NAVIRE": selected_navire,
                    "B/L": str(selected_bl),
                    "OP_DATE": datetime.combine(op_date, datetime.min.time()).isoformat(),
                    "OPERATION": op_type,
                    "LOCATION": loc,
                    "QUANTITE": int(qty),
                    "TONAGE": float(ton),
                    "CHASSIS/SERIAL": chs,
                    "REMARKS": remarks,
                    "CREATED_AT": datetime.now().isoformat(timespec="seconds"),
                }
                append_op_row(row, ops_log_path=ops_log_path)
                st.success("Operation saved.")
                ops_df = read_ops_log(ops_log_path)  # refresh after save

        st.subheader("Today's follow-up")
        daily_date = st.date_input("Select day", value=date.today(), key=f"{key_prefix}daily_pick")
        daily_ops = _filter_ops_by_day(ops_df, selected_navire, daily_date)

        if daily_ops.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Landed qty", 0)
            c2.metric("Received qty", 0)
            c3.metric("Balance (landed - received)", 0)
            st.info("No operations for the selected day.")
        else:
            landed_qty = daily_ops[daily_ops["OPERATION"] == "Landed"]["QUANTITE"].sum()
            received_qty = daily_ops[daily_ops["OPERATION"] == "Received"]["QUANTITE"].sum()
            balance_qty = landed_qty - received_qty
            c1, c2, c3 = st.columns(3)
            c1.metric("Landed qty", int(landed_qty))
            c2.metric("Received qty", int(received_qty))
            c3.metric("Balance (landed - received)", int(balance_qty))

            show_cols = ["OP_DATE", "OPERATION", "LOCATION", "B/L", "QUANTITE", "TONAGE", "CHASSIS/SERIAL", "REMARKS", "CREATED_AT"]
            st.dataframe(daily_ops[show_cols].sort_values(["OP_DATE", "OPERATION", "B/L"]), use_container_width=True)

    with tab2:
        st.subheader("Summary by B/L for selected NAVIRE")
        summary_df = build_summary(manifest_df, ops_df, selected_navire)
        if summary_df.empty:
            st.info("No summary available yet for this NAVIRE.")
        else:
            st.dataframe(summary_df, use_container_width=True)

            # Downloads (per selected NAVIRE)
            nav_ops = ops_df[ops_df["NAVIRE"] == selected_navire].copy()
            nav_ops_csv = nav_ops.to_csv(index=False).encode("utf-8-sig")
            sum_csv = summary_df.to_csv(index=False).encode("utf-8-sig")

            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    "Download detailed operations (CSV)",
                    data=nav_ops_csv,
                    file_name=f"{selected_navire}_operations.csv",
                    mime="text/csv",
                    key=f"{key_prefix}dl_ops"
                )
            with c2:
                st.download_button(
                    "Download summary by B/L (CSV)",
                    data=sum_csv,
                    file_name=f"{selected_navire}_summary.csv",
                    mime="text/csv",
                    key=f"{key_prefix}dl_summary"
                )

    return {"ops_df": ops_df, "summary_df": (build_summary(manifest_df, ops_df, selected_navire) if selected_navire else pd.DataFrame()), "selected_navire": selected_navire}