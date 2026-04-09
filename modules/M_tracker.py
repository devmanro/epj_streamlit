# modules/ManifestTracker.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os
from datetime import datetime
from pathlib import Path
import numpy as np

# --- CONSTANTS ---
DATA_DIR = Path("data/manifests")
DATA_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_FILE = DATA_DIR / "manifests.json"
REMOVALS_FILE = DATA_DIR / "removals.json"
SHIPS_FILE    = DATA_DIR / "ships.json"

CARGO_TYPES = [
    "Coils", "Big Bags", "Materials", "Containers",
    "Bulk", "Machinery", "Steel", "Timber", "Other"
]

COLORS_CARGO = {
    "Coils":      "#FFD700",
    "Big Bags":   "#00C9FF",
    "Materials":  "#FF6B6B",
    "Containers": "#51CF66",
    "Bulk":       "#FF922B",
    "Machinery":  "#CC5DE8",
    "Steel":      "#74C0FC",
    "Timber":     "#A9E34B",
    "Other":      "#868E96",
}

# Palette for clients (auto-assign up to 30 distinct colors)
CLIENT_PALETTE = [
    "#FFD700","#FF6B6B","#51CF66","#00C9FF","#FF922B",
    "#CC5DE8","#74C0FC","#A9E34B","#F06595","#63E6BE",
    "#FFA94D","#4DABF7","#DA77F2","#69DB7C","#FF8787",
    "#FFE066","#66D9E8","#B197FC","#F783AC","#8CE99A",
    "#FFD8A8","#A5D8FF","#E599F7","#C0EB75","#FFA8A8",
    "#96F2D7","#FFEC99","#D0BFFF","#BAC8FF","#FFDEEB",
]

# ============================================================
#  DATA LAYER  (JSON-backed, easy to swap to SQLite/Postgres)
# ============================================================

def _load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def _save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

# ------ SHIPS ------
def load_ships() -> list[dict]:
    return _load_json(SHIPS_FILE, [])

def save_ship(ship: dict):
    ships = load_ships()
    # Update if exists
    for i, s in enumerate(ships):
        if s["id"] == ship["id"]:
            ships[i] = ship
            _save_json(SHIPS_FILE, ships)
            return
    ships.append(ship)
    _save_json(SHIPS_FILE, ships)

def delete_ship(ship_id: str):
    ships = [s for s in load_ships() if s["id"] != ship_id]
    _save_json(SHIPS_FILE, ships)
    # Also delete manifests/removals
    manifests = load_manifests()
    manifests = [m for m in manifests if m["ship_id"] != ship_id]
    _save_json(MANIFEST_FILE, manifests)
    removals = load_removals()
    removals = [r for r in removals if r["ship_id"] != ship_id]
    _save_json(REMOVALS_FILE, removals)

# ------ MANIFESTS (BL entries) ------
def load_manifests() -> list[dict]:
    return _load_json(MANIFEST_FILE, [])

def save_manifest(entry: dict):
    manifests = load_manifests()
    for i, m in enumerate(manifests):
        if m["id"] == entry["id"]:
            manifests[i] = entry
            _save_json(MANIFEST_FILE, manifests)
            return
    manifests.append(entry)
    _save_json(MANIFEST_FILE, manifests)

def delete_manifest(entry_id: str):
    manifests = [m for m in load_manifests() if m["id"] != entry_id]
    _save_json(MANIFEST_FILE, manifests)

# ------ REMOVALS (port removals per BL) ------
def load_removals() -> list[dict]:
    return _load_json(REMOVALS_FILE, [])

def save_removal(entry: dict):
    removals = load_removals()
    for i, r in enumerate(removals):
        if r["id"] == entry["id"]:
            removals[i] = entry
            _save_json(REMOVALS_FILE, removals)
            return
    removals.append(entry)
    _save_json(REMOVALS_FILE, removals)

def delete_removal(entry_id: str):
    removals = [r for r in load_removals() if r["id"] != entry_id]
    _save_json(REMOVALS_FILE, removals)

# ============================================================
#  COMPUTATION HELPERS
# ============================================================

def get_ship_summary(ship_id: str) -> pd.DataFrame:
    """
    Returns a DataFrame with columns:
    client, bl_number, cargo_type, manifested_qty, unit,
    landed_qty, removed_qty, left_qty, landed_pct, left_pct
    """
    manifests = [m for m in load_manifests() if m["ship_id"] == ship_id]
    removals  = load_removals()

    rows = []
    for m in manifests:
        bl_removals = [
            r for r in removals
            if r["ship_id"] == ship_id
            and r["bl_number"] == m["bl_number"]
            and r["cargo_type"] == m["cargo_type"]
        ]
        removed_qty = sum(r["qty"] for r in bl_removals)
        manifested  = m["manifested_qty"]
        landed      = m["landed_qty"]
        left        = max(0, landed - removed_qty)
        landed_pct  = round((landed / manifested * 100), 1) if manifested > 0 else 0
        left_pct    = round((left   / manifested * 100), 1) if manifested > 0 else 0

        rows.append({
            "id":             m["id"],
            "client":         m["client"],
            "bl_number":      m["bl_number"],
            "cargo_type":     m["cargo_type"],
            "manifested_qty": manifested,
            "landed_qty":     landed,
            "removed_qty":    removed_qty,
            "left_qty":       left,
            "unit":           m.get("unit", "T"),
            "landed_pct":     landed_pct,
            "left_pct":       left_pct,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "id","client","bl_number","cargo_type",
        "manifested_qty","landed_qty","removed_qty",
        "left_qty","unit","landed_pct","left_pct"
    ])

def assign_client_colors(clients: list[str]) -> dict:
    return {c: CLIENT_PALETTE[i % len(CLIENT_PALETTE)] for i, c in enumerate(sorted(set(clients)))}

# ============================================================
#  CHART BUILDERS
# ============================================================

def build_manifested_chart(df: pd.DataFrame, ship_name: str) -> go.Figure:
    """
    Big donut per cargo_type, slice = client, 
    inner label = landed % of manifested.
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No manifest data", x=0.5, y=0.5,
                           showarrow=False, font=dict(color="white", size=18))
        fig.update_layout(paper_bgcolor="#0d1117", plot_bgcolor="#0d1117")
        return fig

    cargo_types  = df["cargo_type"].unique().tolist()
    n            = len(cargo_types)
    cols         = min(n, 3)
    rows         = (n + cols - 1) // cols

    specs  = [[{"type": "domain"} for _ in range(cols)] for _ in range(rows)]
    titles = []
    for i, ct in enumerate(cargo_types):
        sub       = df[df["cargo_type"] == ct]
        total_m   = sub["manifested_qty"].sum()
        total_l   = sub["landed_qty"].sum()
        pct       = round(total_l / total_m * 100, 1) if total_m > 0 else 0
        unit      = sub["unit"].iloc[0] if not sub.empty else ""
        titles.append(f"<b>{ct}</b><br>{pct}% Landed<br>({total_l:,.0f}/{total_m:,.0f} {unit})")

    # Pad titles if grid not full
    while len(titles) < rows * cols:
        titles.append("")

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=specs,
        subplot_titles=titles,
        vertical_spacing=0.12,
        horizontal_spacing=0.05,
    )

    client_colors = assign_client_colors(df["client"].tolist())

    for idx, ct in enumerate(cargo_types):
        row = idx // cols + 1
        col = idx % cols  + 1
        sub = df[df["cargo_type"] == ct]

        labels  = sub["client"].tolist()
        values  = sub["landed_qty"].tolist()
        colors  = [client_colors[c] for c in labels]

        # Add "not yet landed" slice
        total_m = sub["manifested_qty"].sum()
        total_l = sub["landed_qty"].sum()
        not_landed = max(0, total_m - total_l)
        if not_landed > 0:
            labels.append("Not Yet Landed")
            values.append(not_landed)
            colors.append("#2a2a3e")

        hover = []
        for i, lbl in enumerate(labels):
            if lbl == "Not Yet Landed":
                hover.append(f"Not Yet Landed<br>{not_landed:,.0f}")
            else:
                row_data = sub[sub["client"] == lbl].iloc[0]
                hover.append(
                    f"<b>{lbl}</b><br>"
                    f"BL: {row_data['bl_number']}<br>"
                    f"Landed: {row_data['landed_qty']:,.0f}<br>"
                    f"Manifested: {row_data['manifested_qty']:,.0f}<br>"
                    f"Landed %: {row_data['landed_pct']}%"
                )

        fig.add_trace(
            go.Pie(
                labels=labels,
                values=values,
                hole=0.52,
                marker=dict(
                    colors=colors,
                    line=dict(color="#0d1117", width=2)
                ),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover,
                textinfo="percent",
                textfont=dict(size=12, color="white"),
                insidetextorientation="radial",
                showlegend=False,
            ),
            row=row, col=col
        )

    h = max(500, rows * 420)
    fig.update_layout(
        title=dict(
            text=f"🚢 <b>{ship_name}</b> — Manifested vs Landed by Cargo Type",
            font=dict(color="#FFD700", size=20),
            x=0.5,
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="white", family="Inter"),
        margin=dict(t=120, b=40, l=20, r=20),
        height=h,
    )
    # Style subplot titles
    for ann in fig.layout.annotations:
        ann.font = dict(color="#FFD700", size=13)

    return fig


def build_left_on_port_chart(
    df: pd.DataFrame, ship_name: str, selected_client: str
) -> go.Figure:
    """
    One donut per BL for the selected client.
    Slice = cargo_type, inner text = left on port qty & pct.
    Also shows a summary sunburst for "All Clients".
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", x=0.5, y=0.5,
                           showarrow=False, font=dict(color="white", size=18))
        fig.update_layout(paper_bgcolor="#0d1117")
        return fig

    if selected_client == "— All Clients —":
        return build_all_clients_left_chart(df, ship_name)

    client_df = df[df["client"] == selected_client]
    if client_df.empty:
        fig = go.Figure()
        fig.add_annotation(text=f"No data for {selected_client}",
                           x=0.5, y=0.5, showarrow=False,
                           font=dict(color="white", size=16))
        fig.update_layout(paper_bgcolor="#0d1117")
        return fig

    bls   = client_df["bl_number"].unique().tolist()
    n     = len(bls)
    cols  = min(n, 3)
    rows  = (n + cols - 1) // cols
    specs = [[{"type": "domain"} for _ in range(cols)] for _ in range(rows)]

    titles = []
    for bl in bls:
        sub      = client_df[client_df["bl_number"] == bl]
        tot_left = sub["left_qty"].sum()
        tot_man  = sub["manifested_qty"].sum()
        unit     = sub["unit"].iloc[0]
        pct      = round(tot_left / tot_man * 100, 1) if tot_man > 0 else 0
        titles.append(
            f"<b>BL: {bl}</b><br>"
            f"Left on Port: {tot_left:,.0f} {unit} ({pct}%)"
        )
    while len(titles) < rows * cols:
        titles.append("")

    fig = make_subplots(
        rows=rows, cols=cols,
        specs=specs,
        subplot_titles=titles,
        vertical_spacing=0.14,
        horizontal_spacing=0.05,
    )

    for idx, bl in enumerate(bls):
        r   = idx // cols + 1
        c   = idx %  cols + 1
        sub = client_df[client_df["bl_number"] == bl]

        labels = sub["cargo_type"].tolist()
        values = sub["left_qty"].tolist()
        colors = [COLORS_CARGO.get(ct, "#868E96") for ct in labels]

        # Add "Removed" slice
        tot_removed = sub["removed_qty"].sum()
        if tot_removed > 0:
            labels.append("Removed")
            values.append(tot_removed)
            colors.append("#3a3a4e")

        hover = []
        for i, lbl in enumerate(labels):
            if lbl == "Removed":
                hover.append(f"Already Removed<br>{tot_removed:,.0f}")
            else:
                rd = sub[sub["cargo_type"] == lbl].iloc[0]
                hover.append(
                    f"<b>{lbl}</b><br>"
                    f"Left: {rd['left_qty']:,.0f} {rd['unit']}<br>"
                    f"Landed: {rd['landed_qty']:,.0f}<br>"
                    f"Removed: {rd['removed_qty']:,.0f}<br>"
                    f"Manifested: {rd['manifested_qty']:,.0f}<br>"
                    f"Left %: {rd['left_pct']}%"
                )

        fig.add_trace(
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors, line=dict(color="#0d1117", width=2)),
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover,
                textinfo="label+percent",
                textfont=dict(size=11, color="white"),
                insidetextorientation="radial",
                showlegend=False,
            ),
            row=r, col=c
        )

    h = max(500, rows * 450)
    fig.update_layout(
        title=dict(
            text=(f"🚢 <b>{ship_name}</b> — Left on Port · "
                  f"Client: <span style='color:#00C9FF'>{selected_client}</span>"),
            font=dict(color="#FFD700", size=20),
            x=0.5,
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="white", family="Inter"),
        margin=dict(t=130, b=40, l=20, r=20),
        height=h,
    )
    for ann in fig.layout.annotations:
        ann.font = dict(color="#00C9FF", size=13)

    return fig


def build_all_clients_left_chart(df: pd.DataFrame, ship_name: str) -> go.Figure:
    """Sunburst: Client → BL → Cargo Type (left on port)."""
    if df.empty:
        return go.Figure()

    ids, labels, parents, values, colors_list = [], [], [], [], []

    client_colors = assign_client_colors(df["client"].tolist())

    # Root
    ids.append("root")
    labels.append("PORT STOCK")
    parents.append("")
    values.append(df["left_qty"].sum())
    colors_list.append("#1a1a2e")

    for client in df["client"].unique():
        c_df   = df[df["client"] == client]
        c_id   = f"c_{client}"
        c_val  = c_df["left_qty"].sum()
        ids.append(c_id); labels.append(client)
        parents.append("root"); values.append(c_val)
        colors_list.append(client_colors[client])

        for bl in c_df["bl_number"].unique():
            b_df  = c_df[c_df["bl_number"] == bl]
            b_id  = f"bl_{client}_{bl}"
            b_val = b_df["left_qty"].sum()
            ids.append(b_id); labels.append(f"BL {bl}")
            parents.append(c_id); values.append(b_val)
            colors_list.append(client_colors[client] + "cc")

            for _, row in b_df.iterrows():
                leaf_id = f"lf_{client}_{bl}_{row['cargo_type']}"
                ids.append(leaf_id)
                labels.append(row["cargo_type"])
                parents.append(b_id)
                values.append(row["left_qty"])
                colors_list.append(COLORS_CARGO.get(row["cargo_type"], "#868E96"))

    fig = go.Figure(go.Sunburst(
        ids=ids, labels=labels, parents=parents, values=values,
        marker=dict(colors=colors_list, line=dict(color="#0d1117", width=1)),
        branchvalues="total",
        hovertemplate="<b>%{label}</b><br>Left: %{value:,.0f}<br>%{percentRoot:.1%} of total<extra></extra>",
        textfont=dict(size=12, color="white"),
        insidetextorientation="radial",
        maxdepth=3,
    ))

    fig.update_layout(
        title=dict(
            text=f"🚢 <b>{ship_name}</b> — All Clients · Left on Port Overview",
            font=dict(color="#FFD700", size=20), x=0.5,
        ),
        paper_bgcolor="#0d1117",
        font=dict(color="white", family="Inter"),
        margin=dict(t=100, b=20, l=20, r=20),
        height=750,
    )
    return fig


# ============================================================
#  SUMMARY TABLE with colored bars
# ============================================================

def styled_summary_table(df: pd.DataFrame):
    if df.empty:
        st.info("No manifest data for this ship.")
        return

    display = df[[
        "client","bl_number","cargo_type","unit",
        "manifested_qty","landed_qty","removed_qty","left_qty",
        "landed_pct","left_pct"
    ]].copy()

    display.columns = [
        "Client","BL Number","Cargo Type","Unit",
        "Manifested","Landed","Removed","Left on Port",
        "Landed %","Left %"
    ]

    st.dataframe(
        display.style
            .format({
                "Manifested": "{:,.0f}", "Landed": "{:,.0f}",
                "Removed": "{:,.0f}", "Left on Port": "{:,.0f}",
                "Landed %": "{:.1f}%", "Left %": "{:.1f}%",
            })
            .background_gradient(subset=["Landed %"],   cmap="YlGn",  vmin=0, vmax=100)
            .background_gradient(subset=["Left %"],     cmap="YlOrRd",vmin=0, vmax=100)
            .set_properties(**{"background-color": "#1a1a2e", "color": "white",
                               "border-color": "#333"}),
        use_container_width=True,
        hide_index=True,
        height=400,
    )


# ============================================================
#  FORMS  (Add Ship / Add BL / Add Removal)
# ============================================================

def form_add_ship():
    with st.form("form_add_ship", clear_on_submit=True):
        st.markdown("#### ➕ Register New Ship")
        c1, c2 = st.columns(2)
        name   = c1.text_input("Ship Name (Navire) *")
        imo    = c2.text_input("IMO Number")
        c3, c4 = st.columns(2)
        flag   = c3.text_input("Flag")
        agent  = c4.text_input("Agent")
        c5, c6 = st.columns(2)
        arrived = c5.date_input("Arrived Date", value=datetime.today())
        berth   = c6.text_input("Berth")
        notes   = st.text_area("Notes")
        submitted = st.form_submit_button("💾 Save Ship", type="primary", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Ship name is required.")
            else:
                ship = {
                    "id":      f"ship_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "name":    name.strip(),
                    "imo":     imo.strip(),
                    "flag":    flag.strip(),
                    "agent":   agent.strip(),
                    "berth":   berth.strip(),
                    "arrived": str(arrived),
                    "notes":   notes.strip(),
                    "created": str(datetime.now()),
                }
                save_ship(ship)
                st.success(f"✅ Ship **{name}** registered!")
                st.rerun()


def form_add_manifest(ship_id: str, ship_name: str):
    with st.form(f"form_manifest_{ship_id}", clear_on_submit=True):
        st.markdown(f"#### ➕ Add BL Entry — *{ship_name}*")
        c1, c2 = st.columns(2)
        client  = c1.text_input("Client / Consignee *")
        bl_num  = c2.text_input("BL Number *")
        c3, c4, c5 = st.columns(3)
        cargo   = c3.selectbox("Cargo Type", CARGO_TYPES)
        unit    = c4.selectbox("Unit", ["T","MT","KG","Units","Rolls","Bags","M3"])
        c6, c7  = st.columns(2)
        man_qty = c6.number_input("Manifested Qty *", min_value=0.0, step=1.0)
        lan_qty = c7.number_input("Landed Qty",       min_value=0.0, step=1.0)
        desc    = st.text_input("Description (optional)")
        submitted = st.form_submit_button("💾 Save BL Entry", type="primary", use_container_width=True)
        if submitted:
            if not client.strip() or not bl_num.strip() or man_qty == 0:
                st.error("Client, BL Number and Manifested Qty are required.")
            else:
                entry = {
                    "id":             f"mfst_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "ship_id":        ship_id,
                    "client":         client.strip(),
                    "bl_number":      bl_num.strip(),
                    "cargo_type":     cargo,
                    "unit":           unit,
                    "manifested_qty": man_qty,
                    "landed_qty":     lan_qty,
                    "description":    desc.strip(),
                    "created":        str(datetime.now()),
                }
                save_manifest(entry)
                st.success(f"✅ BL **{bl_num}** added for **{client}**!")
                st.rerun()


def form_add_removal(ship_id: str, ship_name: str):
    manifests = [m for m in load_manifests() if m["ship_id"] == ship_id]
    if not manifests:
        st.info("Add BL entries first before recording removals.")
        return

    clients  = sorted(set(m["client"]    for m in manifests))
    bls_map  = {}
    for m in manifests:
        bls_map.setdefault(m["client"], {}).setdefault(
            m["bl_number"], []
        ).append(m["cargo_type"])

    with st.form(f"form_removal_{ship_id}", clear_on_submit=True):
        st.markdown(f"#### ➖ Record Port Removal — *{ship_name}*")
        c1, c2 = st.columns(2)
        client  = c1.selectbox("Client", clients)
        bls     = list(bls_map.get(client, {}).keys())
        bl_num  = c2.selectbox("BL Number", bls)
        cargos  = bls_map.get(client, {}).get(bl_num, [])
        c3, c4, c5 = st.columns(3)
        cargo   = c3.selectbox("Cargo Type", cargos)
        qty     = c4.number_input("Quantity Removed *", min_value=0.0, step=1.0)
        rem_date = c5.date_input("Removal Date", value=datetime.today())
        ref     = st.text_input("Reference / Truck / Document")
        submitted = st.form_submit_button("💾 Record Removal", type="primary", use_container_width=True)
        if submitted:
            if qty == 0:
                st.error("Quantity must be > 0.")
            else:
                entry = {
                    "id":        f"rem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                    "ship_id":   ship_id,
                    "client":    client,
                    "bl_number": bl_num,
                    "cargo_type":cargo,
                    "qty":       qty,
                    "date":      str(rem_date),
                    "reference": ref.strip(),
                    "created":   str(datetime.now()),
                }
                save_removal(entry)
                st.success(f"✅ Removal of {qty} recorded for BL **{bl_num}**!")
                st.rerun()


# ============================================================
#  MAIN ENTRY POINT
# ============================================================

def manifest_tracker():
    # ---- CSS overrides ----
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg,#0d1117 0%,#161b22 100%) !important;
        border-right: 1px solid #30363d;
    }
    .ship-card {
        background: linear-gradient(135deg,#1a1a2e,#1e2a3e);
        border: 1px solid #333;
        border-left: 4px solid #FFD700;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.6rem;
        cursor: pointer;
        transition: all 0.2s;
    }
    .ship-card:hover { border-left-color:#00C9FF; background:#1e2f45; }
    .ship-card.active { border-left-color:#51CF66; background:#1a2e1a; }
    .kpi-box {
        background: linear-gradient(145deg,#1a1a2e,#1e2a3e);
        border:1px solid #333; border-radius:10px;
        padding:1rem; text-align:center;
    }
    .kpi-value { font-size:2rem; font-weight:700; color:#FFD700; }
    .kpi-label { font-size:0.8rem; color:#888; margin-top:4px; }
    .section-title {
        color:#FFD700; font-size:1.1rem; font-weight:700;
        border-bottom:1px solid #333; padding-bottom:6px; margin-bottom:12px;
    }
    div[data-testid="stTabs"] button { color:#ccc !important; font-weight:600; }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color:#FFD700 !important; border-bottom-color:#FFD700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ---- Header ----
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);
                padding:1.2rem 2rem;border-radius:12px;
                border-left:5px solid #FFD700;margin-bottom:1rem;">
        <h2 style="color:#FFD700;margin:0;font-family:Inter,sans-serif;">
            📦 Ship Manifest Tracker
        </h2>
        <p style="color:#aab;margin:4px 0 0 0;font-size:0.88rem;">
            Track manifested cargo, landed quantities, and port removals per ship & BL
        </p>
    </div>
    """, unsafe_allow_html=True)

    ships = load_ships()

    # ================================================================
    #  SIDEBAR — Ship list + Add ship button
    # ================================================================
    with st.sidebar:
        st.markdown(
            "<div style='color:#FFD700;font-weight:700;font-size:1rem;"
            "margin-bottom:8px;'>🚢 Ships Registry</div>",
            unsafe_allow_html=True
        )

        if not ships:
            st.info("No ships registered yet.")

        # Ship selector
        ship_names  = [s["name"] for s in ships]
        selected_idx = st.session_state.get("selected_ship_idx", 0)

        if ship_names:
            selected_name = st.radio(
                "Select a Ship",
                ship_names,
                index=min(selected_idx, len(ship_names)-1),
                label_visibility="collapsed",
            )
            st.session_state["selected_ship_idx"] = ship_names.index(selected_name)
            selected_ship = next(s for s in ships if s["name"] == selected_name)
        else:
            selected_ship = None

        st.divider()
        if st.button("➕ Register New Ship", use_container_width=True, type="primary"):
            st.session_state["show_add_ship"] = True

    # ================================================================
    #  ADD SHIP FORM (top of page when triggered)
    # ================================================================
    if st.session_state.get("show_add_ship"):
        with st.container():
            form_add_ship()
            if st.button("✖ Cancel"):
                st.session_state["show_add_ship"] = False
                st.rerun()
        st.divider()

    # ================================================================
    #  NO SHIP SELECTED
    # ================================================================
    if not selected_ship:
        st.markdown("""
        <div style="text-align:center;padding:4rem;color:#555;">
            <div style="font-size:4rem;">🚢</div>
            <div style="font-size:1.2rem;margin-top:1rem;">
                Register a ship using the sidebar to get started.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ================================================================
    #  SHIP DETAIL AREA
    # ================================================================
    ship_id   = selected_ship["id"]
    ship_name = selected_ship["name"]

    # Ship info bar
    c1, c2, c3, c4, c5 = st.columns([3,2,2,2,1])
    c1.markdown(f"### 🚢 {ship_name}")
    c2.markdown(f"**IMO:** `{selected_ship.get('imo','—')}`")
    c3.markdown(f"**Berth:** `{selected_ship.get('berth','—')}`")
    c4.markdown(f"**Agent:** `{selected_ship.get('agent','—')}`")
    with c5:
        if st.button("🗑️", help="Delete this ship", type="secondary"):
            st.session_state["confirm_delete_ship"] = ship_id

    if st.session_state.get("confirm_delete_ship") == ship_id:
        st.warning(f"⚠️ Delete **{ship_name}** and ALL its data?")
        dc1, dc2 = st.columns(2)
        if dc1.button("✅ Yes, Delete", type="primary"):
            delete_ship(ship_id)
            st.session_state.pop("confirm_delete_ship", None)
            st.session_state["selected_ship_idx"] = 0
            st.success("Ship deleted.")
            st.rerun()
        if dc2.button("❌ Cancel"):
            st.session_state.pop("confirm_delete_ship", None)
            st.rerun()

    st.divider()

    # Compute summary
    df = get_ship_summary(ship_id)

    # ---- KPI row ----
    total_m = df["manifested_qty"].sum() if not df.empty else 0
    total_l = df["landed_qty"].sum()     if not df.empty else 0
    total_r = df["removed_qty"].sum()    if not df.empty else 0
    total_lft = df["left_qty"].sum()     if not df.empty else 0
    n_clients = df["client"].nunique()   if not df.empty else 0
    n_bls     = df["bl_number"].nunique()if not df.empty else 0

    k1,k2,k3,k4,k5,k6 = st.columns(6)
    for col, val, label, color in [
        (k1, f"{total_m:,.0f}",  "Total Manifested", "#FFD700"),
        (k2, f"{total_l:,.0f}",  "Total Landed",     "#51CF66"),
        (k3, f"{total_r:,.0f}",  "Total Removed",    "#FF922B"),
        (k4, f"{total_lft:,.0f}","Left on Port",     "#00C9FF"),
        (k5, str(n_clients),     "Clients",          "#CC5DE8"),
        (k6, str(n_bls),         "Bills of Lading",  "#F06595"),
    ]:
        col.markdown(
            f"""<div class="kpi-box">
                <div class="kpi-value" style="color:{color}">{val}</div>
                <div class="kpi-label">{label}</div>
            </div>""",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ================================================================
    #  MAIN TABS
    # ================================================================
    tab_charts, tab_left, tab_data, tab_manage = st.tabs([
        "📊 Manifested vs Landed",
        "🏗️ Left on Port",
        "📋 Data Table",
        "⚙️ Manage Data",
    ])

    # ----------------------------------------------------------------
    #  TAB 1 — Manifested vs Landed
    # ----------------------------------------------------------------
    with tab_charts:
        if df.empty:
            st.info("No manifest data yet. Go to **Manage Data** to add BL entries.")
        else:
            st.markdown(
                "<div class='section-title'>Landed Quantities as % of Manifested — by Cargo Type & Client</div>",
                unsafe_allow_html=True
            )
            fig1 = build_manifested_chart(df, ship_name)
            st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

            # Legend table
            st.markdown("<div class='section-title'>Client Colour Legend</div>", unsafe_allow_html=True)
            if not df.empty:
                cc = assign_client_colors(df["client"].tolist())
                legend_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;'>"
                for cli, clr in cc.items():
                    legend_html += (
                        f"<span style='background:{clr};color:#000;padding:3px 10px;"
                        f"border-radius:12px;font-size:0.8rem;font-weight:600;'>{cli}</span>"
                    )
                legend_html += "</div>"
                st.markdown(legend_html, unsafe_allow_html=True)

    # ----------------------------------------------------------------
    #  TAB 2 — Left on Port
    # ----------------------------------------------------------------
    with tab_left:
        if df.empty:
            st.info("No manifest data yet. Go to **Manage Data** to add BL entries.")
        else:
            # Right-side client dropdown
            col_chart, col_ctrl = st.columns([5, 1])
            with col_ctrl:
                st.markdown("<br><br>", unsafe_allow_html=True)
                clients_list = ["— All Clients —"] + sorted(df["client"].unique().tolist())
                selected_client = st.selectbox(
                    "🔍 Filter by Client",
                    clients_list,
                    key="left_client_filter"
                )
                st.markdown("<br>", unsafe_allow_html=True)

                # Stats for selected client
                if selected_client != "— All Clients —":
                    c_df = df[df["client"] == selected_client]
                    st.metric("BLs", c_df["bl_number"].nunique())
                    st.metric("Left on Port",
                              f"{c_df['left_qty'].sum():,.0f}")
                    st.metric("Removed",
                              f"{c_df['removed_qty'].sum():,.0f}")

            with col_chart:
                st.markdown(
                    "<div class='section-title'>"
                    "Cargo Left on Port — per BL / Client"
                    "</div>",
                    unsafe_allow_html=True
                )
                fig2 = build_left_on_port_chart(df, ship_name, selected_client)
                st.plotly_chart(fig2, use_container_width=True,
                                config={"displayModeBar": False})

    # ----------------------------------------------------------------
    #  TAB 3 — Data Table
    # ----------------------------------------------------------------
    with tab_data:
        st.markdown("<div class='section-title'>Full Manifest Summary</div>",
                    unsafe_allow_html=True)
        styled_summary_table(df)

        st.divider()

        # Removals sub-table
        st.markdown("<div class='section-title'>Removal History</div>",
                    unsafe_allow_html=True)
        removals = [r for r in load_removals() if r["ship_id"] == ship_id]
        if removals:
            df_rem = pd.DataFrame(removals)[[
                "date","client","bl_number","cargo_type","qty","reference"
            ]]
            df_rem.columns = ["Date","Client","BL","Cargo","Qty Removed","Reference"]
            st.dataframe(df_rem.sort_values("Date", ascending=False),
                         use_container_width=True, hide_index=True, height=300)
        else:
            st.info("No removals recorded yet.")

    # ----------------------------------------------------------------
    #  TAB 4 — Manage Data
    # ----------------------------------------------------------------
    with tab_manage:
        m_tab1, m_tab2, m_tab3 = st.tabs([
            "📄 BL Entries", "➖ Record Removal", "✏️ Edit / Delete"
        ])

        with m_tab1:
            form_add_manifest(ship_id, ship_name)

        with m_tab2:
            form_add_removal(ship_id, ship_name)

        with m_tab3:
            st.markdown("<div class='section-title'>Edit / Delete BL Entries</div>",
                        unsafe_allow_html=True)
            manifests = [m for m in load_manifests() if m["ship_id"] == ship_id]
            if not manifests:
                st.info("No BL entries to edit.")
            else:
                for m in manifests:
                    with st.expander(
                        f"📄 BL: {m['bl_number']} | {m['client']} | "
                        f"{m['cargo_type']} | {m['manifested_qty']} {m['unit']}"
                    ):
                        ec1,ec2,ec3 = st.columns(3)
                        new_landed = ec1.number_input(
                            "Update Landed Qty",
                            value=float(m["landed_qty"]),
                            min_value=0.0, step=1.0,
                            key=f"edit_l_{m['id']}"
                        )
                        new_man = ec2.number_input(
                            "Update Manifested Qty",
                            value=float(m["manifested_qty"]),
                            min_value=0.0, step=1.0,
                            key=f"edit_m_{m['id']}"
                        )
                        if ec1.button("💾 Update", key=f"upd_{m['id']}"):
                            m["landed_qty"]     = new_landed
                            m["manifested_qty"] = new_man
                            save_manifest(m)
                            st.success("Updated!")
                            st.rerun()
                        if ec3.button("🗑️ Delete BL", key=f"del_{m['id']}", type="secondary"):
                            delete_manifest(m["id"])
                            st.warning("BL entry deleted.")
                            st.rerun()

            st.divider()
            st.markdown("<div class='section-title'>Edit / Delete Removals</div>",
                        unsafe_allow_html=True)
            removals = [r for r in load_removals() if r["ship_id"] == ship_id]
            if not removals:
                st.info("No removals to edit.")
            else:
                for r in removals:
                    with st.expander(
                        f"➖ {r['date']} | BL: {r['bl_number']} | "
                        f"{r['client']} | {r['cargo_type']} | {r['qty']}"
                    ):
                        rc1, rc2 = st.columns(2)
                        new_qty = rc1.number_input(
                            "Update Qty",
                            value=float(r["qty"]),
                            min_value=0.0, step=1.0,
                            key=f"edit_rq_{r['id']}"
                        )
                        if rc1.button("💾 Update", key=f"upd_r_{r['id']}"):
                            r["qty"] = new_qty
                            save_removal(r)
                            st.success("Updated!")
                            st.rerun()
                        if rc2.button("🗑️ Delete", key=f"del_r_{r['id']}", type="secondary"):
                            delete_removal(r["id"])
                            st.warning("Removal deleted.")
                            st.rerun()