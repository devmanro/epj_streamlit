import streamlit as st
import pandas as pd
from tools.utils.calculations import calculate_roro_surface, get_roro_total

def render_roro_tab(roro_df: pd.DataFrame) -> pd.DataFrame:
    """Render the RoRo merchandise tab."""

    st.markdown("""
    <div style='background: linear-gradient(90deg, #1a472a, #2d6a4f); 
                padding: 15px; border-radius: 10px; margin-bottom: 20px;'>
        <h2 style='color: white; text-align: center; margin: 0;'>
            🚢 SURFACES DES MARCHANDISES RORO
        </h2>
    </div>
    """, unsafe_allow_html=True)

    # ── Quick-fill controls ──────────────────────────────────────────────────
    st.markdown("### ⚡ Saisie rapide")
    col_reset, col_info = st.columns([1, 3])
    with col_reset:
        if st.button("🔄 Réinitialiser tout", key="reset_roro", use_container_width=True):
            for i in range(len(roro_df)):
                st.session_state[f"roro_qty_{i}"] = 0
            st.rerun()
    with col_info:
        st.info("💡 Entrez les quantités pour chaque type de véhicule/équipement")

    st.markdown("---")

    # ── Column headers ───────────────────────────────────────────────────────
    h1, h2, h3, h4 = st.columns([3, 1.5, 1.5, 1.5])
    h1.markdown("**📦 MARCHANDISE**")
    h2.markdown("**📐 Surface/P (M²)**")
    h3.markdown("**🔢 QUANTITE**")
    h4.markdown("**📊 SURFACE (M²)**")
    st.markdown("---")

    # ── Data rows ────────────────────────────────────────────────────────────
    updated_rows = []
    for i, row in roro_df.iterrows():
        c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])

        qty_key = f"roro_qty_{i}"
        if qty_key not in st.session_state:
            st.session_state[qty_key] = int(row.get("quantite", 0))

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
            qty = st.number_input(
                "", min_value=0, step=1,
                key=qty_key, label_visibility="collapsed"
            )
        with c4:
            surface = row["surface_per_unit"] * qty
            color = "#ffd700" if surface > 0 else "#f0f0f0"
            text_color = "#333" if surface > 0 else "#999"
            st.markdown(
                f"<div style='padding:8px; text-align:center; background:{color}; "
                f"border-radius:5px; font-weight:bold; color:{text_color};'>"
                f"{surface:.2f}</div>",
                unsafe_allow_html=True
            )

        updated_rows.append({
            "marchandise":    row["marchandise"],
            "surface_per_unit": row["surface_per_unit"],
            "quantite":       qty,
            "surface":        surface,
        })

    # ── Build updated DataFrame & compute total ──────────────────────────────
    updated_df = pd.DataFrame(updated_rows)
    total = get_roro_total(updated_df)

    st.markdown("---")

    # ── Total row ────────────────────────────────────────────────────────────
    _, _, t_label, t_value = st.columns([3, 1.5, 1.5, 1.5])
    t_label.markdown("**TOTAL**")
    t_value.markdown(
        f"<div style='padding:10px; text-align:center; "
        f"background:linear-gradient(135deg,#ffd700,#ffaa00); "
        f"border-radius:8px; font-weight:bold; font-size:1.1em; color:#333;'>"
        f"{total:.2f} M²</div>",
        unsafe_allow_html=True
    )

    # ── Summary metric cards ─────────────────────────────────────────────────
    st.markdown("### 📊 Résumé")
    m1, m2, m3 = st.columns(3)

    active = updated_df[updated_df["surface"] > 0]
    m1.metric("🚗 Types actifs",       len(active))
    m2.metric("📦 Total véhicules",    int(updated_df["quantite"].sum()))
    m3.metric("📐 Surface totale",     f"{total:.2f} M²")

    return updated_df