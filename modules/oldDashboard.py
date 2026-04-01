import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px

# --- HELPER FUNCTIONS (Defined outside the main function) ---

def fetch_port_data():
    """Mock API data - Replace with requests.get(url).json()"""
    return {
        "timestamp": datetime.now(),
        "ships_in_port": [
            {"Name": "PRINCESS FAYZAH", "Stopover": "20250341", "Agent": "GEMA", "Status": "Operated"},
            {"Name": "SKY GATE", "Stopover": "20250347", "Agent": "SARL I.S.M.S", "Status": "Operated"},
            {"Name": "EEMS SUN", "Stopover": "20260002", "Agent": "GEMA", "Status": "Moored"},
            {"Name": "LORENZO", "Stopover": "20250339", "Agent": "SARL GASS", "Status": "Operated"},
        ],
        "ships_at_anchor": [
            {"Name": "MARMARA PRINCESS", "Stopover": "20260001", "Agent": "GEMA", "Wait Time": "2 days"},
            {"Name": "FORTUNE EXPRESS", "Stopover": "20260008", "Agent": "GEMA", "Wait Time": "5 hours"},
        ],
        "ships_expected": [
            {"Name": "MSC AMALFI", "Stopover": "EXP-001", "ETA": "2026-01-15 14:00"},
        ],
        "loading_ops": [ 
            {"Name": "LORENZO", "Stopover": "20250339", "Product": "CLINKER", "Progress": "85%"},
            {"Name": "FORTUNE EXPRESS", "Stopover": "20260008", "Product": "BILLETES D'ACIER", "Progress": "10%"},
        ],
        "landing_ops": [ 
            {"Name": "PRINCESS FAYZAH", "Stopover": "20250341", "Product": "VEHICULES", "Progress": "40%"},
            {"Name": "SKY GATE", "Stopover": "20250347", "Product": "MAIS", "Progress": "100%"},
        ]
    }

@st.dialog("📋 Ship Details List")
def show_details_popup(title, df):
    st.subheader(f"{title}")
    st.dataframe(
        df, 
        width='stretch', 
        hide_index=True,
        column_config={
            "Stopover": st.column_config.TextColumn("Stopover ID", help="Unique Stopover Number"),
        }
    )

def get_cargo_metrics():
    dates = pd.date_range(end=datetime.today(), periods=10)
    return pd.DataFrame({
        "Date": dates,
        "Tonnage": np.random.randint(1000, 5000, size=10),
        "Type": np.random.choice(["Import", "Export"], size=10)
    })

# --- MAIN DASHBOARD FUNCTION ---
def dashboard():
    # Optional: Local CSS for this page
    st.markdown("""
        <style>
            .header-style { background-color: #FFD700; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
            .header-text { color: #000; font-size: 20px; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="header-style"><span class="header-text">⏱️ Djendjen Port Operations Dashboard</span></div>', unsafe_allow_html=True)

    # Fetch Data
    port_data = fetch_port_data()

    # --- 1. METRICS ROW ---
    col_m1, col_m2, col_m3 = st.columns(3)
    
    with col_m1:
        st.metric("Ships in Port", f"{len(port_data['ships_in_port'])}", delta="Active")
        if st.button("🔍 View In-Port List", width='stretch'):
            show_details_popup("Ships Currently in Port", pd.DataFrame(port_data["ships_in_port"]))

    with col_m2:
        st.metric("At Anchor", f"{len(port_data['ships_at_anchor'])}", delta="-1 vs yesterday", delta_color="inverse")
        if st.button("⚓ View Anchor List", width='stretch'):
            show_details_popup("Ships at Anchor", pd.DataFrame(port_data["ships_at_anchor"]))

    with col_m3:
        st.metric("Expected", f"{len(port_data['ships_expected'])}", delta="+2 New")
        if st.button("📅 View Expected List", width='stretch'):
            show_details_popup("Expected Arrivals", pd.DataFrame(port_data["ships_expected"]))

    st.divider()

    # --- 2. OPERATIONAL TABLES ---
    col_land, col_load = st.columns(2)

    with col_land:
        st.subheader("⬇️ Débarquement (Landing)")
        df_land = pd.DataFrame(port_data["landing_ops"])
        if not df_land.empty:
            st.dataframe(df_land, width='stretch', hide_index=True,
                column_config={"Progress": st.column_config.ProgressColumn("Status", format="%d%%", min_value=0, max_value=100)})
        else:
            st.info("No landing operations active.")

    with col_load:
        st.subheader("⬆️ Embarquement (Loading)")
        df_load = pd.DataFrame(port_data["loading_ops"])
        if not df_load.empty:
            st.dataframe(df_load, width='stretch', hide_index=True,
                column_config={"Progress": st.column_config.ProgressColumn("Status", format="%d%%", min_value=0, max_value=100)})
        else:
            st.info("No loading operations active.")

    st.divider()

    # --- 3. ANALYTICS TABS ---
    t1, t2, t3, t4 = st.tabs(["Cargo Flow", "Berth Perf.", "Storage", "Alerts"])
    
    with t1:
        st.caption("Daily Tonnage Movements")
        fig = px.bar(get_cargo_metrics(), x="Date", y="Tonnage", color="Type", barmode="group", color_discrete_sequence=["#FFD700", "#1f77b4"])
        st.plotly_chart(fig, width='stretch')

    with t2:
        c1, c2 = st.columns(2)
        c1.metric("Berth Utilization", "78%", "High Load")
        c2.metric("Avg Service Time", "14h 30m", "-2h")

    with t3:
        st.metric("Cereal Silos", "12,000 T", "80% Full")

    with t4:
        st.warning("⚠️ Customs Hold: Ship 'SKY GATE' pending clearance.")