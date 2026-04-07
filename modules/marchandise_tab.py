import streamlit as st
import pandas as pd
from tools.utils.calculations import (
    calculate_marchandises_surface,
    get_marchandises_total,
    get_marchandises_total_plus20,
)

def render_marchandises_tab(marc_df: pd.DataFrame) -> pd.DataFrame:
    """Render the general merchandise tab."""

    st.markdown("""
    <div style='background: linear-gradient(90deg, #1a3a5c, #2e6da4);
                padding: 15px; border-radius: 10px; margin-bottom: 20px;'>
        <h2 style='color: white; text-align: center; margin: 0;'>
            📦 SURFACES DES MARCHANDISES
        </h2>
    </div>
    """, unsafe_allow_html=True)

    # ── Controls ─────────────────────────────────────────────────────────────
    st.markdown("### ⚡ Saisie rapide")
    col_reset, col_info = st.columns([1, 3])
    with col_reset:
        if st.button("🔄 Réinitialiser tout", key="reset_marc", use_container_width=True):
            for i in range(len(marc_df)):
                st.session_state[f"marc_qty_{i}"] = 0
            st.rerun()
    with col_info:
        st.info("💡 Surface = (Surface/P ÷ Gerbage) × Quantité  |  +20% = Surface × 1.20")

    st.markdown("---")

    # ── Column headers ───────────────────────────────────────────────────────
    h1, h2, h3, h4, h5, h6 = st.columns([3, 1.2, 1.2, 1.2, 1.5, 1.5])
    h1.markdown("**📦 MARCHANDISE**")
    h2.markdown("**📐 Surf/P M²**")
    h3.markdown("**🗂️ GERBAGE**")
    h4.markdown("**🔢 QUANTITE**")
    h5.markdown("**📊 SURFACE M²**")
    h6.markdown("**➕ +20%**")
    st.markdown("---")

    # ── Data rows ────────────────────────────────────────────────────────────
    updated_rows = []
    for i, row in marc_df.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([3, 1.2, 1.2, 1.2, 1.5, 1.5])

        qty_key = f"marc_qty_{i}"
        if qty_key not in st.session_state:
            st.session_state[qty_key] = int(row.get("quantite", 0))

        gerbage = row["gerbage"]

        with c1:
            st.markdown(
                f"<div style='padding:8px; font-weight:500;'>{row['marchandise']}</div>",
                unsafe_allow_html=True
            )
        with c2:
            st.markdown(
                f"<div style='padding:8px; text-align:center; "
                f"background:#f0f8ff; border-radius:5px;'>{row['surface_per_unit']:.2f}</div>",
                unsafe_allow_html=True
            )
        with c3:
            st.markdown(
                f"<div style='padding:8px; text-align:center; "
                f"background:#f0fff0; border-radius:5px;'>{gerbage}</div>",
                unsafe_allow_html=True
            )
        with c4:
            qty = st.number_input(
                "", min_value=0, step=1,
                key=qty_key, label_visibility="collapsed"
            )

        # Calculate surface
        if gerbage and gerbage > 0:
            surface = (row["surface_per_unit"] / gerbage) * qty
            plus20  = surface * 1.20
        else:
            surface = 0.0
            plus20  = 0.0

        with c5:
            color = "#ffd700" if surface > 0 else "#f0f0f0"
            text_color = "#333" if surface > 0 else "#999"
            st.markdown(
                f"<div style='padding:8px; text-align:center; background:{color}; "
                f"border-radius:5px; font-weight:bold; color:{text_color};'>"
                f"{surface:.2f}</div>",
                unsafe_allow_html=True
            )
        with c6:
            color2 = "#90EE90" if plus20 > 0 else "#f0f0f0"
            st.markdown(
                f"<div style='padding:8px; text-align:center; background:{color2}; "
                f"border-radius:5px; font-weight:bold; color:#333;'>"
                f"{plus20:.2f}</div>",
                unsafe_allow_html=True
            )

        updated_rows.append({
            "marchandise":    row["marchandise"],
            "surface_per_unit": row["surface_per_unit"],
            "gerbage":        gerbage,
            "quantite":       qty,
            "surface":        surface,
            "plus_20_percent": plus20,
        })

    # ── Build updated DataFrame & compute totals ─────────────────────────────
    updated_df = pd.DataFrame(updated_rows)
    total       = get_marchandises_total(updated_df)
    total_plus20 = get_marchandises_total_plus20(updated_df)

    st.markdown("---")

    # ── Total row ────────────────────────────────────────────────────────────
    _, _, _, t_label, t_surface, t_plus20 = st.columns([3, 1.2, 1.2, 1.2, 1.5, 1.5])
    t_label.markdown("**TOTAL**")
    t_surface.markdown(
        f"<div style='padding:10px; text-align:center; "
        f"background:linear-gradient(135deg,#ffd700,#ffaa00); "
        f"border-radius:8px; font-weight:bold; color:#333;'>{total:.2f} M²</div>",
        unsafe_allow_html=True
    )
    t_plus20.markdown(
        f"<div style='padding:10px; text-align:center; "
        f"background:linear-gradient(135deg,#90EE90,#32CD32); "
        f"border-radius:8px; font-weight:bold; color:#333;'>{total_plus20:.2f} M²</div>",
        unsafe_allow_html=True
    )

    # ── Summary metric cards ─────────────────────────────────────────────────
    st.markdown("### 📊 Résumé")
    m1, m2, m3, m4 = st.columns(4)
    active = updated_df[updated_df["surface"] > 0]
    m1.metric("📦 Types actifs",    len(active))
    m2.metric("🔢 Total unités",    int(updated_df["quantite"].sum()))
    m3.metric("📐 Surface totale",  f"{total:.2f} M²")
    m4.metric("➕ +20% total",      f"{total_plus20:.2f} M²")

    return updated_df