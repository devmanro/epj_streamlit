# modules/M_tracker.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os
import math
from datetime import datetime
from pathlib import Path

# ============================================================
#  COLUMN CONSTANTS
# ============================================================

COL_ESCALE         = "ESCALE"
COL_NAVIRE         = "NAVIRE"
COL_DATE           = "DATE"
COL_BL             = "B/L"
COL_DESIGNATION    = "DESIGNATION"
COL_QUANTITE       = "QUANTITE"
COL_TONAGE         = "TONAGE"
COL_CLIENT         = "CLIENT"
COL_CHASSIS_SERIAL = "CHASSIS/SERIAL"
COL_RESTE_TP       = "RESTE T/P"
COL_TYPE           = "TYPE"
COL_PRODUIT        = "PRODUIT"
COL_SITUATION      = "SITUATION"
COL_OBSERVATION    = "OBSERVATION"
COL_POSITION       = "POSITION"
COL_TRANSIT        = "TRANSIT"
COL_CLES           = "CLES"
COL_SURFACE        = "SURFACE"
COL_DRB_TYPE       = "DRB_TYPE"
COL_DATE_ENLEV     = "DATE ENLEV"
COL_CARGO_TYPE     = "CARGO_TYPE"

# ============================================================
#  PATHS & PERSISTENCE
# ============================================================

DATA_DIR      = Path("data/manifests")
DATA_DIR.mkdir(parents=True, exist_ok=True)
REMOVALS_FILE = DATA_DIR / "removals.json"

# ============================================================
#  COLORS
# ============================================================

CARGO_TYPE_COLORS = {
    "divers":       "#FFD700",
    "roro":         "#00C9FF",
    "conteneur":    "#51CF66",
    "vrac":         "#FF922B",
    "hydrocarbure": "#FF6B6B",
    "other":        "#868E96",
}

CLIENT_PALETTE = [
    "#FFD700","#FF6B6B","#51CF66","#00C9FF","#FF922B",
    "#CC5DE8","#74C0FC","#A9E34B","#F06595","#63E6BE",
    "#FFA94D","#4DABF7","#DA77F2","#69DB7C","#FF8787",
    "#FFE066","#66D9E8","#B197FC","#F783AC","#8CE99A",
    "#FFD8A8","#A5D8FF","#E599F7","#C0EB75","#FFA8A8",
    "#96F2D7","#FFEC99","#D0BFFF","#BAC8FF","#FFDEEB",
]

def assign_client_colors(clients) -> dict:
    return {
        c: CLIENT_PALETTE[i % len(CLIENT_PALETTE)]
        for i, c in enumerate(sorted(set(clients)))
    }

def _cargo_color(cargo_type: str) -> str:
    return CARGO_TYPE_COLORS.get(str(cargo_type).lower().strip(), "#868E96")

def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{alpha})"

def darken(hex_color: str, factor: float = 0.55) -> str:
    h = hex_color.lstrip("#")
    r = int(int(h[0:2],16) * factor)
    g = int(int(h[2:4],16) * factor)
    b = int(int(h[4:6],16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

# ============================================================
#  JSON PERSISTENCE
# ============================================================

def _load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def _save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

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
#  FILE LOADER
# ============================================================

@st.cache_data(ttl=120, show_spinner=False)
def load_ship_file(file_path: str) -> pd.DataFrame:
    try:
        if file_path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
        df.columns = [str(c).strip() for c in df.columns]
        for col in [COL_QUANTITE, COL_TONAGE]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        for col in [COL_CLIENT, COL_BL, COL_TYPE,
                    COL_CARGO_TYPE, COL_SITUATION,
                    COL_CHASSIS_SERIAL, COL_DESIGNATION]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"Could not load file: {e}")
        return pd.DataFrame()

# ============================================================
#  SUMMARY BUILDER
# ============================================================

def get_bl_summary(df: pd.DataFrame, ship_key: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    removals      = load_removals()
    ship_removals = [r for r in removals if r["ship_key"] == ship_key]

    landed_map, removed_map = {}, {}
    for r in ship_removals:
        key = (r["bl_number"], r["client"])
        if r.get("record_type") == "landed":
            landed_map[key]  = landed_map.get(key, 0)  + r["qty"]
        else:
            removed_map[key] = removed_map.get(key, 0) + r["qty"]

    rows = []
    for (bl, client), grp in df.groupby([COL_BL, COL_CLIENT], sort=False):
        header       = grp[grp[COL_CHASSIS_SERIAL].astype(str).str.strip() == "-"]
        vehicle_rows = grp[grp[COL_CHASSIS_SERIAL].astype(str).str.strip() != "-"]

        manifest_qty  = header[COL_QUANTITE].sum() if not header.empty else 0
        manifest_tons = grp[COL_TONAGE].sum()
        cond          = header[COL_TYPE].iloc[0]        if not header.empty else "-"
        cargo_type    = header[COL_CARGO_TYPE].iloc[0]  if not header.empty else "-"
        designation   = header[COL_DESIGNATION].iloc[0] if not header.empty else "-"

        key         = (bl, client)
        landed_qty  = landed_map.get(key, 0)
        removed_qty = removed_map.get(key, 0)
        left_qty    = max(0.0, landed_qty - removed_qty)

        rows.append({
            "bl_number":       bl,
            "client":          client,
            "cargo_type":      cargo_type,
            "conditionnement": cond,
            "designation":     designation,
            "manifest_qty":    manifest_qty,
            "manifest_tons":   manifest_tons,
            "n_vehicles":      len(vehicle_rows),
            "landed_qty":      landed_qty,
            "removed_qty":     removed_qty,
            "left_qty":        left_qty,
            "landed_pct":      round(landed_qty  / manifest_qty * 100, 1) if manifest_qty else 0,
            "left_pct":        round(left_qty    / manifest_qty * 100, 1) if manifest_qty else 0,
            "removed_pct":     round(removed_qty / manifest_qty * 100, 1) if manifest_qty else 0,
        })

    return pd.DataFrame(rows)

# ============================================================
#  CIRCULAR BAR PLOT  — core chart
#
#  Layout (from centre outward):
#
#  r=0.00 → 0.05   dead centre  (clean space)
#  r=0.05 → 0.25   REMOVED bars  (brightest — cargo gone from port)
#  r=0.25 → 0.50   LEFT bars     (medium    — cargo still on port)
#  r=0.50 → 0.75   LANDED bars   (vivid     — cargo discharged)
#  r=0.75 → 1.00   MANIFEST bars (full ring — total declared)
#
#  Each client = one angular sector.
#  Bars fill inward from their max radius proportionally.
#  Centre label: ship totals.
# ============================================================

def _bar_path(
    theta_start: float,
    theta_end:   float,
    r_inner:     float,
    r_outer:     float,
    n_pts:       int = 80,
) -> str:
    """Annular sector as SVG path. Angles in degrees."""
    fwd = [theta_start + (theta_end - theta_start)*i/(n_pts-1) for i in range(n_pts)]
    rev = fwd[::-1]

    def pt(a, r):
        rad = math.radians(a)
        return r * math.cos(rad), r * math.sin(rad)

    outer = [pt(a, r_outer) for a in fwd]
    inner = [pt(a, r_inner) for a in rev]
    all_pts = outer + inner

    d = f"M {all_pts[0][0]:.5f},{all_pts[0][1]:.5f} "
    for x, y in all_pts[1:]:
        d += f"L {x:.5f},{y:.5f} "
    d += "Z"
    return d


def _label_pos(theta_mid: float, r: float) -> tuple[float, float]:
    """Paper coords [0,1] from polar, mapping [-1,1]→[0,1]."""
    rad = math.radians(theta_mid)
    x   = math.cos(rad) * r
    y   = math.sin(rad) * r
    # scale to paper: ±1 maps to [0.05, 0.95]
    return 0.5 + x * 0.45, 0.5 + y * 0.45


def build_circular_barplot(
    df: pd.DataFrame,
    ship_name: str,
    show_clients: list[str],
    mode: str = "manifested",   # "manifested" | "left"
) -> go.Figure:
    """
    Pure SVG circular bar chart rendered on a Plotly scatter canvas.
    One angular band per client.
    Three concentric bar layers per client:
      manifested (outermost) → landed → removed/left (innermost)
    """

    if df.empty:
        return _empty_fig("No manifest data for this ship")

    plot_df = df[df["client"].isin(show_clients)] \
              if show_clients else df.copy()
    if plot_df.empty:
        return _empty_fig("No data for selected clients")

    # ── Aggregate per client ──
    agg = plot_df.groupby("client", as_index=False).agg(
        manifest_qty =("manifest_qty",  "sum"),
        manifest_tons=("manifest_tons", "sum"),
        landed_qty   =("landed_qty",    "sum"),
        removed_qty  =("removed_qty",   "sum"),
        left_qty     =("left_qty",      "sum"),
        n_bls        =("bl_number",     "nunique"),
    )
    agg = agg[agg["manifest_qty"] > 0].reset_index(drop=True)
    if agg.empty:
        return _empty_fig("All selected clients have zero manifested qty")

    n_clients     = len(agg)
    client_colors = assign_client_colors(agg["client"].tolist())
    total_manifest = agg["manifest_qty"].sum()

    # ── Radii ──────────────────────────────────────────────
    # Concentric rings (normalised 0-1):
    #   0.00–0.10  dead centre
    #   0.10–0.40  innermost bar  (removed / left_on_port)
    #   0.40–0.70  middle bar     (landed)
    #   0.70–1.00  outer bar      (manifest / background)
    #
    R_CENTRE_MAX = 0.10   # clear inner disc
    R_IN_INNER   = 0.12   # removed / left bar inner edge
    R_IN_OUTER   = 0.38   # removed / left bar outer edge
    R_MID_INNER  = 0.42   # landed bar inner edge
    R_MID_OUTER  = 0.68   # landed bar outer edge
    R_OUT_INNER  = 0.72   # manifest bar inner edge
    R_OUT_OUTER  = 0.98   # manifest bar outer edge

    GAP_DEG   = 1.2       # gap between clients
    START_DEG = 90.0      # top of circle, clockwise

    # ── Compute angular sectors ──
    sectors = []
    total_span = 360.0 - GAP_DEG * n_clients
    cum = 0.0
    for _, row in agg.iterrows():
        share   = row["manifest_qty"] / total_manifest
        span    = share * total_span
        t_start = START_DEG - cum                  # clockwise → subtract
        t_end   = START_DEG - cum - span
        sectors.append({
            "client":    row["client"],
            "color":     client_colors[row["client"]],
            "t_start":   t_start,
            "t_end":     t_end,
            "t_mid":     (t_start + t_end) / 2,
            "manifest":  row["manifest_qty"],
            "tons":      row["manifest_tons"],
            "landed":    row["landed_qty"],
            "removed":   row["removed_qty"],
            "left":      row["left_qty"],
            "n_bls":     row["n_bls"],
            "l_pct":     round(row["landed_qty"]  / row["manifest_qty"] * 100, 1)
                         if row["manifest_qty"] else 0,
            "rem_pct":   round(row["removed_qty"] / row["manifest_qty"] * 100, 1)
                         if row["manifest_qty"] else 0,
            "lft_pct":   round(row["left_qty"]    / row["manifest_qty"] * 100, 1)
                         if row["manifest_qty"] else 0,
        })
        cum += span + GAP_DEG

    # ============================================================
    #  BUILD FIGURE  (scatter canvas + shapes)
    # ============================================================
    fig = go.Figure()

    # Invisible scatter to define canvas & enable hover
    hover_x, hover_y, hover_text, hover_colors = [], [], [], []

    shapes = []

    for s in sectors:
        color     = s["color"]
        t_s       = s["t_start"]
        t_e       = s["t_end"]
        t_m       = s["t_mid"]
        manifest  = s["manifest"]
        landed    = s["landed"]
        removed   = s["removed"]
        left      = s["left"]

        # ── LAYER 1: manifest background ring (full span, dim) ──
        shapes.append(dict(
            type="path",
            path=_bar_path(t_e, t_s, R_OUT_INNER, R_OUT_OUTER),
            fillcolor=hex_to_rgba(color, 0.18),
            line=dict(color=hex_to_rgba(color, 0.40), width=1),
            xref="x", yref="y",
        ))

        # ── LAYER 2: manifest vivid bar (full — it's the max) ──
        shapes.append(dict(
            type="path",
            path=_bar_path(t_e, t_s, R_OUT_INNER, R_OUT_OUTER),
            fillcolor=hex_to_rgba(color, 0.85),
            line=dict(color=color, width=1.5),
            xref="x", yref="y",
        ))

        # ── LAYER 3: landed middle ring background (dim) ──
        shapes.append(dict(
            type="path",
            path=_bar_path(t_e, t_s, R_MID_INNER, R_MID_OUTER),
            fillcolor=hex_to_rgba(color, 0.12),
            line=dict(color="rgba(0,0,0,0)", width=0),  # ← was 'transparent'
            xref="x", yref="y",
        ))

        # ── LAYER 4: landed fill — proportional to manifest ──
        if landed > 0 and manifest > 0:
            span_total = t_s - t_e          # positive degrees
            landed_span = span_total * (landed / manifest)
            t_landed_end = t_s - landed_span
            shapes.append(dict(
                type="path",
                path=_bar_path(t_landed_end, t_s, R_MID_INNER, R_MID_OUTER),
                fillcolor=hex_to_rgba(color, 0.80),
                line=dict(color=color, width=1),
                xref="x", yref="y",
            ))

        # ── LAYER 5: inner ring background (dim) ──
        shapes.append(dict(
            type="path",
            path=_bar_path(t_e, t_s, R_IN_INNER, R_IN_OUTER),
            fillcolor=hex_to_rgba(color, 0.08),
            line=dict(color="rgba(0,0,0,0)", width=0),  # ← was 'transparent'
            xref="x", yref="y",
        ))

        # ── LAYER 6: innermost fill ──
        #   mode=manifested → show removed (how much left port)
        #   mode=left       → show left_qty (how much still on port)
        inner_val = removed if mode == "manifested" else left
        inner_lbl = "Removed" if mode == "manifested" else "Left on Port"

        if inner_val > 0 and manifest > 0:
            span_total  = t_s - t_e
            inner_span  = span_total * (inner_val / manifest)
            t_inner_end = t_s - inner_span
            inner_color = "#FF922B" if mode == "manifested" else "#00C9FF"
            shapes.append(dict(
                type="path",
                path=_bar_path(t_inner_end, t_s, R_IN_INNER, R_IN_OUTER),
                fillcolor=hex_to_rgba(inner_color, 0.90),
                line=dict(color=inner_color, width=1),
                xref="x", yref="y",
            ))

        # ── Hover point at midpoint of middle ring ──
        r_hover = (R_MID_INNER + R_MID_OUTER) / 2
        hx = math.cos(math.radians(t_m)) * r_hover
        hy = math.sin(math.radians(t_m)) * r_hover
        hover_x.append(hx)
        hover_y.append(hy)
        hover_colors.append(color)

        if mode == "manifested":
            htxt = (
                f"<b>{s['client']}</b><br>"
                f"━━━━━━━━━━━━━━━━━<br>"
                f"📦 Manifest:  <b>{manifest:,.0f}</b> colis "
                f"({s['tons']:,.1f} T)<br>"
                f"BLs: {s['n_bls']}<br>"
                f"━━━━━━━━━━━━━━━━━<br>"
                f"✅ Landed:    <b>{landed:,.0f}</b>  ({s['l_pct']}%)<br>"
                f"🚛 Removed:   <b>{removed:,.0f}</b> ({s['rem_pct']}%)<br>"
                f"⏳ Not landed:<b>{max(0,manifest-landed):,.0f}</b>"
            )
        else:
            htxt = (
                f"<b>{s['client']}</b><br>"
                f"━━━━━━━━━━━━━━━━━<br>"
                f"📦 Manifest:  <b>{manifest:,.0f}</b> colis<br>"
                f"BLs: {s['n_bls']}<br>"
                f"━━━━━━━━━━━━━━━━━<br>"
                f"✅ Landed:    <b>{landed:,.0f}</b>  ({s['l_pct']}%)<br>"
                f"🏗️ On Port:   <b>{left:,.0f}</b>   ({s['lft_pct']}%)<br>"
                f"🚛 Removed:   <b>{removed:,.0f}</b> ({s['rem_pct']}%)"
            )
        hover_text.append(htxt)

        # ── Client label ──
        r_lbl   = R_OUT_OUTER + 0.07
        lx      = math.cos(math.radians(t_m)) * r_lbl
        ly      = math.sin(math.radians(t_m)) * r_lbl
        short   = s["client"][:10] + "…" if len(s["client"]) > 10 else s["client"]
        shr_pct = round(manifest / total_manifest * 100, 1)

        # Rotate label to follow the arc tangent
        angle_text = t_m
        if -180 <= angle_text < -90 or 90 < angle_text <= 180:
            angle_text += 180   # flip labels on left half

        if shr_pct >= 1.5:
            fig.add_annotation(
                x=lx, y=ly,
                xref="x", yref="y",
                text=f"<b>{short}</b><br><span style='color:#888;font-size:9px'>"
                     f"{shr_pct}%</span>",
                showarrow=False,
                font=dict(size=9, color=color, family="Inter"),
                align="center",
                textangle=-angle_text,
            )

    # ── Invisible hover scatter ──
    fig.add_trace(go.Scatter(
        x=hover_x, y=hover_y,
        mode="markers",
        marker=dict(size=22, color=hover_colors,
                    opacity=0.0, line=dict(width=0)),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_text,
        showlegend=False,
    ))

    fig.update_layout(shapes=shapes)

    # ── Centre disc & labels ──
    total_l   = agg["landed_qty"].sum()
    total_m   = agg["manifest_qty"].sum()
    total_r   = agg["removed_qty"].sum()
    total_lft = agg["left_qty"].sum()
    total_t   = agg["manifest_tons"].sum()

    # Draw centre white disc
    fig.add_shape(
        type="circle",
        x0=-R_CENTRE_MAX, y0=-R_CENTRE_MAX,
        x1= R_CENTRE_MAX, y1= R_CENTRE_MAX,
        fillcolor="#0d1117",
        line=dict(color="#FFD700", width=1.5),
        xref="x", yref="y",
    )

    if mode == "manifested":
        pct_l = round(total_l / total_m * 100, 1) if total_m else 0
        centre_lines = [
            (f"{pct_l}%",               "#51CF66", 16, True),
            ("Landed",                  "#888888", 9,  False),
            (f"{total_l:,.0f} colis",   "#AAAAAA", 9,  False),
            (f"{total_t:,.0f} T",       "#666666", 8,  False),
        ]
    else:
        pct_p = round(total_lft / total_m * 100, 1) if total_m else 0
        centre_lines = [
            (f"{pct_p}%",               "#00C9FF", 16, True),
            ("On Port",                 "#888888", 9,  False),
            (f"{total_lft:,.0f} colis", "#AAAAAA", 9,  False),
            (f"{total_r:,.0f} removed", "#FF922B", 8,  False),
        ]

    y_offsets = [0.055, 0.015, -0.025, -0.060]
    for (txt, clr, sz, bold), yo in zip(centre_lines, y_offsets):
        fig.add_annotation(
            x=0, y=yo, xref="x", yref="y",
            text=f"<b>{txt}</b>" if bold else txt,
            showarrow=False,
            font=dict(size=sz, color=clr, family="Inter"),
            align="center",
        )

    # ── Ring labels (inner / mid / outer) ──
    label_angle = START_DEG + 8   # just after the gap at top
    for r_mid, lbl, clr in [
        ((R_IN_INNER + R_IN_OUTER)/2,
         "Removed" if mode=="manifested" else "Left", "#FF922B" if mode=="manifested" else "#00C9FF"),
        ((R_MID_INNER + R_MID_OUTER)/2, "Landed",   "#51CF66"),
        ((R_OUT_INNER + R_OUT_OUTER)/2, "Manifest", "#FFD700"),
    ]:
        rx = math.cos(math.radians(label_angle)) * r_mid * 1.0
        ry = math.sin(math.radians(label_angle)) * r_mid * 1.0
        fig.add_annotation(
            x=rx, y=ry, xref="x", yref="y",
            text=f"<b>{lbl}</b>",
            showarrow=False,
            font=dict(size=8, color=clr, family="Inter"),
            bgcolor=hex_to_rgba("#0d1117", 0.7),
            borderpad=2,
            align="center",
        )

    # ── Legend box ──
    if mode == "manifested":
        legend_items = [
            ("█ Manifest (outer)",  "#FFD700", 0.85),
            ("█ Landed  (middle)",  "#51CF66", 0.80),
            ("█ Removed (inner)",   "#FF922B", 0.90),
            ("░ Not yet landed",    "#444444", 1.00),
        ]
    else:
        legend_items = [
            ("█ Manifest (outer)",  "#FFD700", 0.85),
            ("█ Landed  (middle)",  "#51CF66", 0.80),
            ("█ On Port (inner)",   "#00C9FF", 0.90),
            ("░ Not landed",        "#444444", 1.00),
        ]

    for i, (lbl, clr, op) in enumerate(legend_items):
        fig.add_annotation(
            x=1.18, y=0.92 - i * 0.09,
            xref="paper", yref="paper",
            text=f"<span style='color:{clr}'>{lbl}</span>",
            showarrow=False,
            font=dict(size=11, color=clr, family="Inter"),
            xanchor="left", align="left",
        )

    # ── Final layout ──
    pad = 1.25
    title_sfx = (
        f" <span style='color:#888;font-size:13px'>"
        f"({len(show_clients)} clients)</span>"
        if show_clients else ""
    )
    if mode == "manifested":
        title = f"📦 <b>{ship_name}</b> — Manifested vs Landed{title_sfx}"
    else:
        title = f"🏗️ <b>{ship_name}</b> — Left on Port{title_sfx}"

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(color="#FFD700", size=18, family="Inter"),
            x=0.5, xanchor="center",
        ),
        xaxis=dict(
            visible=False,
            range=[-pad, pad * 1.45],
            scaleanchor="y",
        ),
        yaxis=dict(
            visible=False,
            range=[-pad, pad],
        ),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="white", family="Inter"),
        margin=dict(t=80, b=20, l=20, r=180),
        height=700,
        hovermode="closest",
    )

    return fig


# ============================================================
#  EMPTY FIGURE
# ============================================================

def _empty_fig(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=msg, x=0.5, y=0.5, showarrow=False,
        font=dict(color="#888", size=16, family="Inter"),
    )
    fig.update_layout(
        paper_bgcolor="#0d1117", height=520,
        font=dict(color="white", family="Inter"),
    )
    return fig


# ============================================================
#  KPI CARDS
# ============================================================

def _kpi_card(label: str, value: str, sub: str, color: str) -> str:
    return f"""
    <div style="
        background:linear-gradient(145deg,#1a1a2e,#1e2a3e);
        border:1px solid #2a3a4e;
        border-top:3px solid {color};
        border-radius:10px;
        padding:12px 14px;
        text-align:center;
        margin-bottom:7px;
    ">
        <div style="font-size:1.4rem;font-weight:700;
                    color:{color};font-family:Inter,sans-serif;
                    line-height:1.15;">{value}</div>
        <div style="font-size:0.71rem;color:#888;margin-top:3px;">{label}</div>
        <div style="font-size:0.67rem;color:#555;margin-top:2px;">{sub}</div>
    </div>"""


def render_kpi_column(df: pd.DataFrame):
    if df.empty:
        return
    tot_m   = df["manifest_qty"].sum()
    tot_t   = df["manifest_tons"].sum()
    tot_l   = df["landed_qty"].sum()
    tot_r   = df["removed_qty"].sum()
    tot_lft = df["left_qty"].sum()
    n_cli   = df["client"].nunique()
    n_bls   = df["bl_number"].nunique()
    l_pct   = round(tot_l   / tot_m * 100, 1) if tot_m else 0
    lft_pct = round(tot_lft / tot_m * 100, 1) if tot_m else 0

    for label, val, sub, color in [
        ("Manifested",      f"{tot_m:,.0f}",   "colis total",           "#FFD700"),
        ("Weight",          f"{tot_t:,.1f}",   "tons",                  "#FFA94D"),
        ("Landed",          f"{tot_l:,.0f}",   f"{l_pct}% of manifest", "#51CF66"),
        ("Removed",         f"{tot_r:,.0f}",   "taken from port",       "#FF922B"),
        ("Left on Port",    f"{tot_lft:,.0f}", f"{lft_pct}% remains",   "#00C9FF"),
        ("Clients",         str(n_cli),        "consignees",            "#CC5DE8"),
        ("Bills of Lading", str(n_bls),        "total BLs",             "#F06595"),
    ]:
        st.markdown(_kpi_card(label, val, sub, color), unsafe_allow_html=True)


def render_client_kpi(df: pd.DataFrame, selected_clients: list[str]):
    c_df = df[df["client"].isin(selected_clients)] if selected_clients else df
    if c_df.empty:
        return
    tot_m   = c_df["manifest_qty"].sum()
    tot_t   = c_df["manifest_tons"].sum()
    tot_l   = c_df["landed_qty"].sum()
    tot_r   = c_df["removed_qty"].sum()
    tot_lft = c_df["left_qty"].sum()
    l_pct   = round(tot_l / tot_m * 100, 1) if tot_m else 0

    for label, val, sub, color in [
        ("BLs",          str(c_df["bl_number"].nunique()), "filtered BLs", "#F06595"),
        ("Manifested",   f"{tot_m:,.0f}",   "colis",                "#FFD700"),
        ("Weight",       f"{tot_t:,.1f}",   "tons",                 "#FFA94D"),
        ("Landed",       f"{tot_l:,.0f}",   f"{l_pct}%",            "#51CF66"),
        ("Removed",      f"{tot_r:,.0f}",   "from port",            "#FF922B"),
        ("Left on Port", f"{tot_lft:,.0f}", "still here",           "#00C9FF"),
    ]:
        st.markdown(_kpi_card(label, val, sub, color), unsafe_allow_html=True)


# ============================================================
#  SHIP BANNER
# ============================================================

def render_ship_banner(df: pd.DataFrame):
    if df.empty:
        return
    row        = df.iloc[0]
    ship_name  = str(row.get(COL_NAVIRE,     "—"))
    escale     = str(row.get(COL_ESCALE,     "—"))
    date_man   = str(row.get(COL_DATE,       "—"))
    cargo_type = str(row.get(COL_CARGO_TYPE, "—"))
    ct_color   = _cargo_color(cargo_type)

    st.markdown(f"""
    <div style="
        background:linear-gradient(135deg,#1a1a2e 0%,#0f2a40 100%);
        border:1px solid #2a3a4e;border-left:5px solid #FFD700;
        border-radius:12px;padding:1rem 1.8rem;margin-bottom:1rem;
        display:flex;flex-wrap:wrap;gap:2rem;align-items:center;">
        <div>
            <div style="font-size:1.6rem;font-weight:700;
                        color:#FFD700;font-family:Inter,sans-serif;">
                🚢 {ship_name}
            </div>
            <span style="background:{ct_color}22;color:{ct_color};
                         padding:2px 12px;border-radius:10px;
                         font-size:0.78rem;font-weight:600;
                         border:1px solid {ct_color}55;
                         margin-top:6px;display:inline-block;">
                {cargo_type.upper()}
            </span>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:2.5rem;
                    flex:1;justify-content:flex-end;color:#aaa;">
            <div>
                <span style="color:#555;font-size:0.72rem;">ESCALE</span><br>
                <b style="color:white;font-size:0.95rem;">{escale}</b>
            </div>
            <div>
                <span style="color:#555;font-size:0.72rem;">DATE MANIFESTE</span><br>
                <b style="color:white;font-size:0.95rem;">{date_man}</b>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
#  REMOVAL HISTORY
# ============================================================

def render_removal_history(ship_key: str):
    removals = [
        r for r in load_removals()
        if r["ship_key"] == ship_key
        and r.get("record_type", "removal") == "removal"
    ]

    st.markdown("""
    <div style="color:#FFD700;font-weight:700;font-size:1rem;
                border-bottom:1px solid #333;
                padding-bottom:6px;margin:20px 0 10px 0;">
        📋 Removal History
    </div>""", unsafe_allow_html=True)

    if not removals:
        st.markdown("""
        <div style="color:#555;text-align:center;padding:1.5rem;
                    border:1px dashed #333;border-radius:8px;
                    font-size:0.88rem;">
            No removals recorded for this ship yet.
        </div>""", unsafe_allow_html=True)
        return

    df_rem  = pd.DataFrame(removals)
    wanted  = ["date","client","bl_number","conditionnement",
               "qty","reference","created"]
    present = [c for c in wanted if c in df_rem.columns]
    df_rem  = df_rem[present].sort_values("date", ascending=False)
    df_rem.columns = [c.replace("_"," ").title() for c in df_rem.columns]

    st.dataframe(
        df_rem.style
            .set_properties(**{
                "background-color": "#0d1117",
                "color":            "white",
                "border-color":     "#1e2a3e",
                "font-size":        "0.84rem",
            })
            .apply(lambda x: [
                "background-color:#12192a" if i%2==0
                else "background-color:#0d1117"
                for i in range(len(x))
            ], axis=0)
            .format({"Qty": "{:,.0f}"}),
        use_container_width=True,
        hide_index=True,
        height=240,
    )

    with st.expander("🗑️ Delete a removal record"):
        del_ids = {
            f"{r['date']} | {r['client']} | BL {r['bl_number']} | {r['qty']}": r["id"]
            for r in removals
        }
        chosen = st.selectbox("Select record", list(del_ids.keys()),
                              key=f"del_rem_{ship_key}")
        if st.button("🗑️ Confirm Delete",
                     key=f"del_btn_{ship_key}", type="secondary"):
            delete_removal(del_ids[chosen])
            st.cache_data.clear()
            st.success("Deleted.")
            st.rerun()


# ============================================================
#  FORMS
# ============================================================

def render_forms(ship_key: str, df_summary: pd.DataFrame):
    if df_summary.empty:
        return

    with st.expander("✏️ Record Landed Qty / Port Removal", expanded=False):
        f_tab1, f_tab2 = st.tabs(["📥 Update Landed Qty", "➖ Record Removal"])
        clients = sorted(df_summary["client"].unique().tolist())

        with f_tab1:
            fc1, fc2 = st.columns(2)
            client  = fc1.selectbox("Client", clients, key=f"lnd_cli_{ship_key}")
            bls     = sorted(df_summary[
                df_summary["client"]==client]["bl_number"].unique())
            bl_num  = fc2.selectbox("BL", bls, key=f"lnd_bl_{ship_key}")
            fc3, fc4, fc5 = st.columns(3)
            qty     = fc3.number_input("Qty Landed (colis)", min_value=0.0,
                                       step=1.0, key=f"lnd_qty_{ship_key}")
            date_l  = fc4.date_input("Date", value=datetime.today(),
                                     key=f"lnd_date_{ship_key}")
            ref     = fc5.text_input("Reference", key=f"lnd_ref_{ship_key}")
            if st.button("💾 Save Landed", type="primary",
                         use_container_width=True, key=f"lnd_save_{ship_key}"):
                if qty <= 0:
                    st.error("Quantity must be > 0")
                else:
                    save_removal({
                        "id":          f"lnd_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        "ship_key":    ship_key,
                        "record_type": "landed",
                        "client":      client,
                        "bl_number":   bl_num,
                        "qty":         qty,
                        "date":        str(date_l),
                        "reference":   ref.strip(),
                        "created":     str(datetime.now()),
                    })
                    st.cache_data.clear()
                    st.success(f"✅ {qty:,.0f} colis landed for BL {bl_num}")
                    st.rerun()

        with f_tab2:
            rc1, rc2 = st.columns(2)
            r_client = rc1.selectbox("Client", clients, key=f"rem_cli_{ship_key}")
            r_bls    = sorted(df_summary[
                df_summary["client"]==r_client]["bl_number"].unique())
            r_bl     = rc2.selectbox("BL", r_bls, key=f"rem_bl_{ship_key}")
            rc3, rc4, rc5 = st.columns(3)
            r_qty    = rc3.number_input("Qty Removed (colis)", min_value=0.0,
                                        step=1.0, key=f"rem_qty_{ship_key}")
            r_date   = rc4.date_input("Date", value=datetime.today(),
                                      key=f"rem_date_{ship_key}")
            r_ref    = rc5.text_input("Reference", key=f"rem_ref_{ship_key}")
            if st.button("💾 Save Removal", type="primary",
                         use_container_width=True, key=f"rem_save_{ship_key}"):
                if r_qty <= 0:
                    st.error("Quantity must be > 0")
                else:
                    save_removal({
                        "id":          f"rem_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        "ship_key":    ship_key,
                        "record_type": "removal",
                        "client":      r_client,
                        "bl_number":   r_bl,
                        "qty":         r_qty,
                        "date":        str(r_date),
                        "reference":   r_ref.strip(),
                        "created":     str(datetime.now()),
                    })
                    st.cache_data.clear()
                    st.success(f"✅ {r_qty:,.0f} removed for BL {r_bl}")
                    st.rerun()


# ============================================================
#  MAIN ENTRY POINT
# ============================================================

def manifest_tracker(upload_dir: str):

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    div[data-testid="stTabs"] button {
        color:#ccc !important;font-weight:600;font-family:Inter,sans-serif;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color:#FFD700 !important;
        border-bottom:3px solid #FFD700 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="margin-bottom:1rem;">
        <h2 style="color:#FFD700;font-family:Inter,sans-serif;margin:0;">
            📦 Ship Manifest Tracker
        </h2>
        <p style="color:#888;font-size:0.85rem;margin:4px 0 0 0;">
            Manifested · Landed · Port removals — per ship & Bill of Lading
        </p>
    </div>
    """, unsafe_allow_html=True)

    try:
        all_files = [
            f for f in os.listdir(upload_dir)
            if f.endswith((".xlsx", ".xls", ".csv"))
        ]
    except FileNotFoundError:
        st.error(f"Upload directory not found: {upload_dir}")
        return

    if not all_files:
        st.warning("No ship files found.")
        return

    # ── SIDEBAR ──
    with st.sidebar:
        st.markdown("""
        <div style="color:#FFD700;font-weight:700;font-size:0.88rem;
                    letter-spacing:0.5px;margin:6px 0 4px 0;">
            📦 MANIFEST TRACKER
        </div>""", unsafe_allow_html=True)

        selected_file = st.selectbox(
            "Ship File",
            options=all_files,
            index=st.session_state.get("manifest_file_idx", 0),
            key="manifest_ship_select",
            label_visibility="collapsed",
        )
        st.session_state["manifest_file_idx"] = all_files.index(selected_file)

        file_path  = os.path.join(upload_dir, selected_file)
        df_raw     = load_ship_file(file_path)
        ship_key   = selected_file
        df_summary = get_bl_summary(df_raw, ship_key)

        all_clients = sorted(
            df_summary["client"].unique().tolist()
            if not df_summary.empty else []
        )

        st.markdown("""
        <div style="color:#FFD700;font-weight:700;font-size:0.88rem;
                    letter-spacing:0.5px;margin:10px 0 2px 0;">
            🔍 CLIENT FILTER
        </div>
        <div style="color:#555;font-size:0.74rem;margin-bottom:6px;">
            Deselect to hide from chart
        </div>""", unsafe_allow_html=True)

        selected_clients = st.multiselect(
            "Clients",
            options=all_clients,
            default=all_clients,
            key="manifest_client_multisel",
            label_visibility="collapsed",
        )

        st.divider()

        if selected_clients and len(selected_clients) < len(all_clients):
            render_client_kpi(df_summary, selected_clients)
        else:
            render_kpi_column(df_summary)

    # ── Ship name & banner ──
    ship_name = (
        str(df_raw.iloc[0][COL_NAVIRE])
        if not df_raw.empty and COL_NAVIRE in df_raw.columns
        else os.path.splitext(selected_file)[0].upper()
    )
    render_ship_banner(df_raw)

    show_clients = selected_clients if selected_clients else all_clients

    # ── Client colour legend ──
    cc   = assign_client_colors(all_clients)
    html = "<div style='display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px;'>"
    for cli in all_clients:
        clr = cc[cli]
        op  = "1" if cli in show_clients else "0.2"
        html += (
            f"<span style='background:{clr};color:#000;opacity:{op};"
            f"padding:3px 11px;border-radius:12px;"
            f"font-size:0.76rem;font-weight:600;'>{cli}</span>"
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

    # ================================================================
    #  TWO TABS
    # ================================================================
    tab1, tab2 = st.tabs([
        "📊  Manifested vs Landed",
        "🏗️  Left on Port",
    ])

    with tab1:
        col_chart, col_kpi = st.columns([5, 1], gap="medium")
        with col_kpi:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            if selected_clients and len(selected_clients) < len(all_clients):
                render_client_kpi(df_summary, selected_clients)
            else:
                render_kpi_column(df_summary)
        with col_chart:
            fig1 = build_circular_barplot(
                df_summary, ship_name, show_clients, mode="manifested"
            )
            st.plotly_chart(fig1, use_container_width=True,
                            config={"displayModeBar": False})

    with tab2:
        col_chart2, col_kpi2 = st.columns([5, 1], gap="medium")
        with col_kpi2:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            if selected_clients and len(selected_clients) < len(all_clients):
                render_client_kpi(df_summary, selected_clients)
            else:
                render_kpi_column(df_summary)
        with col_chart2:
            fig2 = build_circular_barplot(
                df_summary, ship_name, show_clients, mode="left"
            )
            st.plotly_chart(fig2, use_container_width=True,
                            config={"displayModeBar": False})

        st.markdown(
            "<hr style='border-color:#1e2a3e;margin:16px 0'>",
            unsafe_allow_html=True,
        )
        # render_forms(ship_key, df_summary)
        # render_removal_history(ship_key)