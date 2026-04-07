
# from modules.processor import calculate_daily_totals,calculate_surface


# def utilities(st):
#     with st.expander("Surface Area Calculator"):
#         type_good = st.selectbox("Type of Good", ["Bulk", "Containers", "Steel Pipes"])
#         inp_qty=st.number_input("Quantity/Weight", min_value=1)
#         surface=calculate_surface(inp_qty)
#         st.success(f"Estimated Surface Needed: {surface} m²")

    



import streamlit as st
import pandas as pd
from data.merchandise_data import RORO_ITEMS, MARCHANDISES_ITEMS
from modules.roro_tab import render_roro_tab
from modules.marchandise_tab import render_marchandises_tab
from modules.summary_tab import render_summary_tab  


def utilities(st):
    # 1. Initialize data if not already in session state
    # (Uses the imports from your main file like RORO_ITEMS)
    if "roro_df" not in st.session_state:
        df = pd.DataFrame(RORO_ITEMS)
        df["quantite"] = 0
        df["surface"]  = 0.0
        st.session_state.roro_df = df

    if "marc_df" not in st.session_state:
        df = pd.DataFrame(MARCHANDISES_ITEMS)
        df["quantite"] = 0
        df["surface"]  = 0.0
        df["plus_20_percent"] = 0.0
        st.session_state.marc_df = df

    # 2. Render the Tabs inside the "Logistics Tools" section
    tab1, tab2, tab3 = st.tabs([
        "🚢 RoRo",
        "📦 Marchandises",
        "📊 Résumé & Export",
    ])

    with tab1:
        # Note: Ensure render_roro_tab is imported where utilities is defined
        updated_roro = render_roro_tab(st.session_state.roro_df)
        st.session_state.roro_df = updated_roro

    with tab2:
        updated_marc = render_marchandises_tab(st.session_state.marc_df)
        st.session_state.marc_df = updated_marc

    with tab3:
        render_summary_tab(
            st.session_state.roro_df,
            st.session_state.marc_df,
        )