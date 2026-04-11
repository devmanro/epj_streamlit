import io
import pandas as pd
from datetime import datetime
from assets.constants.merchandise_data import RORO_ITEMS, MARCHANDISES_ITEMS
from modules.roro_tab import render_roro_tab
from modules.marchandise_tab import render_marchandises_tab
from modules.summary_tab import render_summary_tab  



def utilities(st):
    """
    Main function to render the Port Surface Calculator inside 
    an existing Streamlit application menu.
    """
    
    # ── Custom CSS (Scoped for this tool) ───────────────────────────────────
    st.markdown("""
    <style>
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0; 
            border-radius: 10px; padding: 4px;

        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 8px; 
            padding: 8px 32px;
            font-weight: 600; font-size: 0.95rem;
            color: #555; background: transparent;
        }
        .stTabs [aria-selected="true"] {
            
            color: #1a472a !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.12);
        }

        /* Cards */
        .card {
          border-radius: 12px;
            padding: 20px; margin-bottom: 16px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
            
        }
        .section-title {
            font-size: 0.75rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: 1px;
            color: #888; margin-bottom: 12px;
        }

        /* Metric */
        div[data-testid="metric-container"] {
           border: 1px solid #e9ecef;
            border-radius: 10px; padding: 12px 16px;
        }

        /* Surface badge */
        .surface-badge {
            display: inline-block; background: #ffd700;
            color: #333; font-weight: 700;
            padding: 4px 12px; border-radius: 20px;
            font-size: 1.05rem;
        }
        .surface-badge-blue {
            background: #cce5ff; color: #004085;
        }

        /* Total bar */
        .total-bar {
            background: linear-gradient(135deg, #1a472a, #2d6a4f);
            color: white; border-radius: 12px;
            padding: 16px 24px; display: flex;
            justify-content: space-between; align-items: center;
            margin-top: 8px;
        }
        .total-bar-blue {
            background: linear-gradient(135deg, #1a3a5c, #2e6da4);
        }
    </style>
    """, unsafe_allow_html=True)

    # ── Session State Initialization ────────────────────────────────────────
    if "roro_entries" not in st.session_state:
        st.session_state.roro_entries = []
    if "marc_entries" not in st.session_state:
        st.session_state.marc_entries = []

    # ── Header ──────────────────────────────────────────────────────────────



    tab_roro, tab_marc, tab_resume = st.tabs(["🚗  RoRo", "📦  Marchandises", "📊  Résumé & Export"])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1 — RORO
    # ════════════════════════════════════════════════════════════════════════
    with tab_roro:
        roro_lookup = {item["marchandise"]: item["surface_per_unit"] for item in RORO_ITEMS}
        roro_names  = [item["marchandise"] for item in RORO_ITEMS]

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">➕ Nouvelle entrée</div>', unsafe_allow_html=True)

        r1, r2, r3, r4 = st.columns([3, 1.2, 1.5, 1.2])
        with r1:
            roro_selected = st.selectbox("Type de marchandise", options=roro_names, key="roro_select")
        with r2:
            surf_unit = roro_lookup.get(roro_selected, 0)
            st.markdown(f"<div style='margin-top:28px;'><div class='section-title'>Surface/unité</div><span class='surface-badge surface-badge-blue'>{surf_unit:.2f} M²</span></div>", unsafe_allow_html=True)
        with r3:
            roro_bl = st.text_input("N° BL", key="roro_bl", value="BL-XXX-XXX", placeholder="ex: BL-XXX-XXX")
        with r4:
            roro_qty = st.number_input("Quantité", min_value=1, step=1, value=1, key="roro_qty")

        preview_surface = surf_unit * roro_qty
        st.markdown(f"<div style='display:flex; align-items:center; gap:10px; margin:10px 0 14px; padding:10px 14px; border-radius:8px;'><span style='color:#888; font-size:0.9rem;'>Surface calculée :</span><span class='surface-badge'>{preview_surface:.2f} M²</span></div>", unsafe_allow_html=True)

        if st.button("💾  Enregistrer", key="save_roro", type="primary"):
            if not roro_bl.strip():
                st.warning("⚠️ Veuillez saisir un numéro de BL.")
            else:
                st.session_state.roro_entries.append({
                    "type": "RoRo", "marchandise": roro_selected, "bl": roro_bl.strip(),
                    "quantite": roro_qty, "surface_per_unit": surf_unit, "surface": preview_surface
                })
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.roro_entries:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            df_roro = pd.DataFrame(st.session_state.roro_entries)
            
            # Simplified row display
            for idx, row in df_roro.iterrows():
                c1, c2, c3, c4 = st.columns([4, 2, 2, 0.5])
                c1.markdown(f"**{row['marchandise']}** (x{int(row['quantite'])})")
                c2.markdown(f"BL: `{row['bl']}`")
                c3.markdown(f"<span class='surface-badge'>{row['surface']:.2f} M²</span>", unsafe_allow_html=True)
                if c4.button("🗑️", key=f"del_roro_{idx}"):
                    st.session_state.roro_entries.pop(idx)
                    st.rerun()

            total_roro = df_roro["surface"].sum()
            st.markdown(f"<div class='total-bar'><span>{len(df_roro)} entrée(s)</span><span>Total : {total_roro:.2f} M²</span></div>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2 — MARCHANDISES
    # ════════════════════════════════════════════════════════════════════════
    with tab_marc:
        marc_lookup = {item["marchandise"]: {"surface_per_unit": item["surface_per_unit"], "gerbage": item["gerbage"]} for item in MARCHANDISES_ITEMS}
        marc_names = [item["marchandise"] for item in MARCHANDISES_ITEMS]

        st.markdown('<div class="card">', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns([3, 1.2, 1.5, 1.2])
        with m1:
            marc_selected = st.selectbox("Type de marchandise", options=marc_names, key="marc_select")
        
        m_data = marc_lookup.get(marc_selected, {"surface_per_unit": 0, "gerbage": 1})
        m_surf_unit, m_gerbage = m_data["surface_per_unit"], m_data["gerbage"]

        with m2:
            st.markdown(f"<div style='margin-top:28px;'><span class='surface-badge surface-badge-blue'>{m_surf_unit:.2f} / {m_gerbage}</span></div>", unsafe_allow_html=True)
        with m3:
            marc_bl = st.text_input("N° BL", key="marc_bl", value="BL-XXX-XXX", placeholder="ex: BL-XXX-XXX")
        with m4:
            marc_qty = st.number_input("Quantité", min_value=1, value=1, key="marc_qty")

        m_surface = (m_surf_unit / m_gerbage) * marc_qty
        m_plus20_preview = m_surface * 1.20
        
        st.markdown(f"<div style='display:flex; align-items:center; gap:10px; margin:10px 0 14px; padding:10px 14px; border-radius:8px;'><span style='color:#888; font-size:0.9rem;'>Surface calculée :</span><span class='surface-badge'>{m_plus20_preview:.2f} M²</span></div>", unsafe_allow_html=True)
        if st.button("💾  Enregistrer", key="save_marc", type="primary"):
            if not marc_bl.strip():
                st.warning("⚠️ BL requis.")
            else:
                st.session_state.marc_entries.append({
                    "type": "Marchandise", "marchandise": marc_selected, "bl": marc_bl.strip(),
                    "quantite": marc_qty, "surface_per_unit": m_surf_unit, "gerbage": m_gerbage,
                    "surface": m_surface, "surface_plus_20": m_plus20_preview
                })
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        if st.session_state.marc_entries:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            df_marc = pd.DataFrame(st.session_state.marc_entries)
            for idx, row in df_marc.iterrows():
                c1, c2, c3, c4 = st.columns([4, 2, 2, 0.5])
                c1.markdown(f"**{row['marchandise']}** (G:{row['gerbage']})")
                c2.markdown(f"BL: `{row['bl']}`")
                c3.markdown(f"<span class='surface-badge' style='background:#c3f0ca;'>{row['surface_plus_20']:.2f} M²</span>", unsafe_allow_html=True)
                if c4.button("🗑️", key=f"del_marc_{idx}"):
                    st.session_state.marc_entries.pop(idx)
                    st.rerun()
            total_march = df_marc["surface_plus_20"].sum()
            st.markdown(f"<div class='total-bar'><span>{len(df_marc)} entrée(s)</span><span>Total : {total_march:.2f} M²</span></div>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3 — RÉSUMÉ & EXPORT
    # ════════════════════════════════════════════════════════════════════════
    with tab_resume:
        all_roro = st.session_state.roro_entries
        all_marc = st.session_state.marc_entries
        
        roro_total = sum(e["surface"] for e in all_roro)
        marc_total_20 = sum(e["surface_plus_20"] for e in all_marc)
        
        k1, k2, k3 = st.columns(3)
        k1.metric("🚗 RoRo Total", f"{roro_total:.2f} M²")
        k2.metric("📦 Marchandises (+20%)", f"{marc_total_20:.2f} M²")
        k3.metric("📐 Global", f"{roro_total + marc_total_20:.2f} M²")

        if all_roro or all_marc:
            # Excel Export Logic (Buffered)
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
                if all_roro: pd.DataFrame(all_roro).to_excel(writer, sheet_name="RoRo", index=False)
                if all_marc: pd.DataFrame(all_marc).to_excel(writer, sheet_name="Marchandises", index=False)
            
            st.download_button(
                "📥 Télécharger le rapport Excel",
                data=buf.getvalue(),
                file_name=f"surfaces_port_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            if st.button("🔴 Réinitialiser toutes les données"):
                st.session_state.roro_entries = []
                st.session_state.marc_entries = []
                st.rerun()

# ── To call this in your main script: ──────────────────────────────────────
# elif choice == "Logistics Tools":
#     utilities(st)
