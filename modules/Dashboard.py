import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
from io import StringIO

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Djendjen Port Dashboard",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CONSTANTS ---
BASE_URL = "https://djendjen-port.dz/custom-scripts/situations"
URLS = {
    "berthed": f"{BASE_URL}/berthed.php",
    "anchored": f"{BASE_URL}/anchored.php",
    "expected": f"{BASE_URL}/expected.php",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# --- CSS STYLING ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    .main { background-color: #0a0a0a; }
    
    .dashboard-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        border-left: 5px solid #FFD700;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .dashboard-header h1 {
        color: #FFD700;
        font-family: 'Inter', sans-serif;
        font-size: 1.8rem;
        margin: 0;
    }
    .dashboard-header p {
        color: #aab;
        font-size: 0.9rem;
        margin: 0.3rem 0 0 0;
    }
    
    .source-badge {
        background: #1a3a1a;
        color: #00ff88;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        border: 1px solid #00ff8844;
    }
    
    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, #1a1a2e, #1e2a3e);
        border: 1px solid #333;
        border-radius: 10px;
        padding: 1rem;
    }
    
    div[data-testid="stTabs"] button {
        color: #ccc !important;
        font-weight: 600;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #FFD700 !important;
        border-bottom-color: #FFD700 !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
#  1. FREE TIER API LAYER (Datalastic)
# ============================================================

class DatalasticAPI:
    """Uses Datalastic Free Tier (100 req/month) for UN/LOCODE DZDJE"""
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.datalastic.com/api/v0"
        self.locode = "DZDJE"

    def get_all_data(self) -> dict:
        data = {
            "berthed": pd.DataFrame(),
            "anchored": pd.DataFrame(),
            "expected": pd.DataFrame()
        }
        
        if not self.api_key:
            return data

        try:
            # 1. Get Vessels in Port (Berthed & Anchored)
            port_url = f"{self.base_url}/port_vessels"
            port_resp = requests.get(port_url, params={"api-key": self.api_key, "locode": self.locode}, timeout=10)
            if port_resp.status_code == 200:
                port_json = port_resp.json().get("data", [])
                if port_json:
                    df_port = pd.DataFrame(port_json)
                    # Filter by navigation status (1/5 = Moored/Berthed, 1/2 = Anchored)
                    data["berthed"] = df_port[df_port.get("navigation_status", 0).isin([1, 5])]
                    data["anchored"] = df_port[df_port.get("navigation_status", 0).isin([2])]

            # 2. Get Expected Arrivals
            eta_url = f"{self.base_url}/vessel_expected_arrivals"
            eta_resp = requests.get(eta_url, params={"api-key": self.api_key, "locode": self.locode}, timeout=10)
            if eta_resp.status_code == 200:
                eta_json = eta_resp.json().get("data", [])
                if eta_json:
                    data["expected"] = pd.DataFrame(eta_json)

        except Exception as e:
            st.sidebar.warning(f"API Error: {e}")

        return data


# ============================================================
#  2. WEB SCRAPER FALLBACK (Unlimited Free Data)
# ============================================================

class DjendjenScraper:
    """Scrapes live vessel data directly from the port website as a free fallback."""
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = False  # Ignore SSL warnings for this site

    def _fetch_page(self, url: str) -> BeautifulSoup | None:
        try:
            import urllib3
            urllib3.disable_warnings() # Suppress warnings
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return None

    def _parse_html_table(self, soup: BeautifulSoup) -> pd.DataFrame:
        if not soup: return pd.DataFrame()
        try:
            tables = pd.read_html(StringIO(str(soup)))
            if tables:
                return tables[0]
        except Exception:
            pass
        return pd.DataFrame()

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {
            "nom": "Vessel Name", "navire": "Vessel Name",
            "escale": "Stopover", "quai": "Berth",
            "agent": "Agent", "marchandise": "Cargo",
            "tonnage": "Tonnage", "eta": "ETA",
            "provenance": "Origin", "pavillon": "Flag",
            "situation": "Status", "obs": "Remarks"
        }
        new_cols = {}
        for col in df.columns:
            col_lower = str(col).strip().lower()
            for fr, en in rename_map.items():
                if fr in col_lower:
                    new_cols[col] = en
                    break
        return df.rename(columns=new_cols)

    def get_all_data(self) -> dict:
        data = {}
        for key, url in URLS.items():
            soup = self._fetch_page(url)
            df = self._parse_html_table(soup)
            if not df.empty:
                df = self._standardize_columns(df)
            data[key] = df
        return data


# ============================================================
#  DASHBOARD UI
# ============================================================

def dashboard():
    # --- HEADER ---
    st.markdown("""
        <div class="dashboard-header">
            <h1>🚢 Port de Djendjen — Live Operations</h1>
            <p>Real-time vessel data: Berthed, Anchored, and Expected Arrivals</p>
        </div>
    """, unsafe_allow_html=True)

    # --- SIDEBAR CONFIG ---
    with st.sidebar:
        st.header("⚙️ Configuration")
        st.caption("Enter a free API key, or leave blank to use the web scraper.")
        
        api_key = st.text_input(
            "Datalastic API Key (Optional)",
            type="password",
            help="Get 100 free requests/month at datalastic.com"
        )
        
        st.divider()
        auto_refresh = st.toggle("Auto-refresh", value=False)
        refresh_interval = st.slider("Refresh interval (seconds)", 30, 300, 60)
        
        if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()

    # --- FETCH DATA ---
    @st.cache_data(ttl=60, show_spinner=False)
    def load_data(key: str):
        # 1. Try API if key is provided
        if key:
            api = DatalasticAPI(key)
            data = api.get_all_data()
            if not data["berthed"].empty or not data["expected"].empty:
                data["source"] = "Datalastic API"
                data["timestamp"] = datetime.now()
                return data

        # 2. Fallback to Scraper (Unlimited Free Tier)
        scraper = DjendjenScraper()
        data = scraper.get_all_data()
        data["source"] = "Official Port Scraper"
        data["timestamp"] = datetime.now()
        return data

    with st.spinner("📡 Fetching port data..."):
        port_data = load_data(api_key)

    df_berthed = port_data.get("berthed", pd.DataFrame())
    df_anchored = port_data.get("anchored", pd.DataFrame())
    df_expected = port_data.get("expected", pd.DataFrame())

    # --- SOURCE INDICATOR ---
    col_status1, col_status2 = st.columns([3, 1])
    with col_status1:
        st.success(f"🟢 Data Source: **{port_data['source']}**")
    with col_status2:
        st.caption(f"🕐 Updated: {port_data['timestamp']:%H:%M:%S}")

    st.divider()

    # --- METRICS ROW ---
    col1, col2, col3 = st.columns(3)
    col1.metric("🚢 Ships Berthed", len(df_berthed), delta="Currently in port", delta_color="normal")
    col2.metric("⚓ Ships at Anchor", len(df_anchored), delta="Waiting at anchorage", delta_color="off")
    col3.metric("📅 Expected Arrivals", len(df_expected), delta="Incoming vessels", delta_color="normal")

    st.divider()

    # --- MAIN DATA TABLES ---
    tab_berthed, tab_anchored, tab_expected = st.tabs([
        "🚢 Ships Berthed", "⚓ Ships at Anchor", "📅 Expected Arrivals"
    ])
    
    with tab_berthed:
        if not df_berthed.empty:
            st.dataframe(df_berthed, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("No berthed vessels at this time.")
    
    with tab_anchored:
        if not df_anchored.empty:
            st.dataframe(df_anchored, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("No anchored vessels at this time.")
    
    with tab_expected:
        if not df_expected.empty:
            st.dataframe(df_expected, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("No expected arrivals at this time.")

    # --- AUTO REFRESH ---
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

