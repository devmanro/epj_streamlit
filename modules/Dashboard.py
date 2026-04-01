# app.py
import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import time
import json
import re
from io import StringIO

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Djendjen Port Dashboard",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CONSTANTS ---
BASE_URL = "https://djendjen-port.dz/custom-scripts/situations"
URLS = {
    "berthed": f"{BASE_URL}/berthed.php",
    "anchored": f"{BASE_URL}/anchored.php",     # adjust if different
    "expected": f"{BASE_URL}/expected.php",      # adjust if different
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://djendjen-port.dz/",
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
    
    .status-card {
        background: linear-gradient(145deg, #1e1e2e, #252540);
        border-radius: 12px;
        padding: 1.2rem;
        border: 1px solid #333;
        transition: transform 0.2s;
    }
    .status-card:hover { transform: translateY(-2px); }
    
    .live-dot {
        display: inline-block;
        width: 10px; height: 10px;
        background: #00ff88;
        border-radius: 50%;
        animation: pulse 1.5s infinite;
        margin-right: 8px;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(0,255,136,0.7); }
        50% { opacity: 0.7; box-shadow: 0 0 0 8px rgba(0,255,136,0); }
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
    
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    
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
#  SCRAPING LAYER
# ============================================================

class DjendjenScraper:
    """Scrapes live vessel data from djendjen-port.dz public pages."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = True  # Set False if SSL issues
    
    # ---------- generic helpers ----------
    
    def _fetch_page(self, url: str, timeout: int = 15) -> BeautifulSoup | None:
        """Fetch and parse a page, return BeautifulSoup or None."""
        try:
            resp = self.session.get(url, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "html.parser")
        except requests.exceptions.SSLError:
            # Retry without SSL verification
            try:
                resp = self.session.get(url, timeout=timeout, verify=False)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                return BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                st.warning(f"SSL fallback failed for {url}: {e}")
                return None
        except Exception as e:
            st.warning(f"Failed to fetch {url}: {e}")
            return None
    
    def _parse_html_table(self, soup: BeautifulSoup) -> pd.DataFrame:
        """
        Extract the FIRST <table> found in the page.
        Handles rowspan/colspan, cleans whitespace.
        """
        if soup is None:
            return pd.DataFrame()
        
        # Try multiple table-finding strategies
        table = None
        
        # Strategy 1: Look for <table> with class
        for cls in ["table", "tableau", "data-table", "vessels"]:
            table = soup.find("table", class_=re.compile(cls, re.I))
            if table:
                break
        
        # Strategy 2: Just get first table
        if not table:
            table = soup.find("table")
        
        if not table:
            # Strategy 3: Try to read all tables via pandas
            try:
                tables = pd.read_html(StringIO(str(soup)))
                if tables:
                    return tables[0]
            except Exception:
                pass
            return pd.DataFrame()
        
        # Parse manually for better control
        rows = table.find_all("tr")
        if not rows:
            return pd.DataFrame()
        
        # Extract headers
        header_row = rows[0]
        headers = []
        for th in header_row.find_all(["th", "td"]):
            text = th.get_text(strip=True)
            headers.append(text if text else f"Col_{len(headers)}")
        
        # Extract data rows
        data = []
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            row_data = [cell.get_text(strip=True) for cell in cells]
            if row_data and any(cell.strip() for cell in row_data):
                data.append(row_data)
        
        if not data:
            return pd.DataFrame()
        
        # Align columns
        max_cols = max(len(headers), max(len(r) for r in data) if data else 0)
        headers.extend([f"Col_{i}" for i in range(len(headers), max_cols)])
        
        aligned_data = []
        for row in data:
            row.extend([""] * (max_cols - len(row)))
            aligned_data.append(row[:max_cols])
        
        return pd.DataFrame(aligned_data, columns=headers[:max_cols])
    
    # ---------- specific endpoints ----------
    
    def get_berthed(self) -> pd.DataFrame:
        """Ships currently berthed in port."""
        soup = self._fetch_page(URLS["berthed"])
        df = self._parse_html_table(soup)
        if not df.empty:
            df = self._standardize_columns(df, "berthed")
        return df
    
    def get_anchored(self) -> pd.DataFrame:
        """Ships at anchor / waiting."""
        # Try the anchored URL; if it fails try common variations
        for suffix in ["anchored.php", "anchorage.php", "rade.php", "mouillage.php"]:
            url = f"{BASE_URL}/{suffix}"
            soup = self._fetch_page(url)
            if soup:
                df = self._parse_html_table(soup)
                if not df.empty:
                    df = self._standardize_columns(df, "anchored")
                    return df
        return pd.DataFrame()
    
    def get_expected(self) -> pd.DataFrame:
        """Ships expected to arrive."""
        for suffix in ["expected.php", "attendus.php", "prevus.php"]:
            url = f"{BASE_URL}/{suffix}"
            soup = self._fetch_page(url)
            if soup:
                df = self._parse_html_table(soup)
                if not df.empty:
                    df = self._standardize_columns(df, "expected")
                    return df
        return pd.DataFrame()
    
    def _standardize_columns(self, df: pd.DataFrame, category: str) -> pd.DataFrame:
        """Try to rename French columns to English for consistency."""
        rename_map = {
            # French -> English mappings (case-insensitive matching)
            "navire": "Vessel Name",
            "nom": "Vessel Name",
            "nom du navire": "Vessel Name",
            "name": "Vessel Name",
            "escale": "Stopover",
            "n° escale": "Stopover",
            "quai": "Berth",
            "poste": "Berth",
            "agent": "Agent",
            "consignataire": "Agent",
            "marchandise": "Cargo",
            "produit": "Cargo",
            "nature": "Cargo",
            "tonnage": "Tonnage",
            "poids": "Tonnage",
            "date arrivée": "Arrival",
            "arrivée": "Arrival",
            "date accostage": "Berthing Date",
            "accostage": "Berthing Date",
            "eta": "ETA",
            "date prévue": "ETA",
            "provenance": "Origin",
            "destination": "Destination",
            "pavillon": "Flag",
            "flag": "Flag",
            "longueur": "Length",
            "tirant d'eau": "Draft",
            "te": "Draft",
            "opération": "Operation",
            "operation": "Operation",
            "situation": "Status",
            "etat": "Status",
            "état": "Status",
            "status": "Status",
            "obs": "Remarks",
            "observation": "Remarks",
        }
        
        new_cols = {}
        for col in df.columns:
            col_lower = col.strip().lower()
            for fr, en in rename_map.items():
                if fr in col_lower:
                    new_cols[col] = en
                    break
        
        if new_cols:
            df = df.rename(columns=new_cols)
        
        df["Category"] = category.capitalize()
        return df
    
    def get_all_data(self) -> dict:
        """Fetch all three categories and return as dict of DataFrames."""
        return {
            "berthed": self.get_berthed(),
            "anchored": self.get_anchored(),
            "expected": self.get_expected(),
            "timestamp": datetime.now(),
        }


# ============================================================
#  AIS API LAYER (Free Tier Fallbacks)
# ============================================================

class AISDataFetcher:
    """
    Fetches vessel data from free AIS APIs as supplement/fallback.
    Tries multiple sources in order of reliability.
    """
    
    # Djendjen Port coordinates
    PORT_LAT = 36.8206
    PORT_LON = 5.7525
    PORT_RADIUS_KM = 15  # radius to capture anchored vessels
    
    def fetch_from_aishub(self, api_key: str = None) -> pd.DataFrame:
        """
        AISHub API (free tier: register at aishub.net)
        Free tier: share your AIS data, get access to global data
        """
        if not api_key:
            return pd.DataFrame()
        
        url = "http://data.aishub.net/ws.php"
        params = {
            "username": api_key,
            "format": "1",  # JSON
            "output": "json",
            "compress": "0",
            "latmin": self.PORT_LAT - 0.15,
            "latmax": self.PORT_LAT + 0.15,
            "lonmin": self.PORT_LON - 0.15,
            "lonmax": self.PORT_LON + 0.15,
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if isinstance(data, list) and len(data) > 1:
                vessels = data[1]
                df = pd.DataFrame(vessels)
                return self._process_ais_data(df)
        except Exception as e:
            st.caption(f"AISHub: {e}")
        return pd.DataFrame()
    
    def fetch_from_datalastic(self, api_key: str = None) -> pd.DataFrame:
        """
        Datalastic API (free tier: 100 req/month)
        Register at datalastic.com
        """
        if not api_key:
            return pd.DataFrame()
        
        url = "https://api.datalastic.com/api/v0/vessel_inradius"
        params = {
            "api-key": api_key,
            "latitude": self.PORT_LAT,
            "longitude": self.PORT_LON,
            "radius": self.PORT_RADIUS_KM,
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if "data" in data:
                df = pd.DataFrame(data["data"])
                return self._process_ais_data(df)
        except Exception as e:
            st.caption(f"Datalastic: {e}")
        return pd.DataFrame()
    
    def fetch_from_myshiptracking(self) -> pd.DataFrame:
        """
        Scrape MyShipTracking (no API key needed).
        Port of Djendjen area.
        """
        url = f"https://www.myshiptracking.com/requests/vesselsonmap.php"
        params = {
            "type": "json",
            "minlat": self.PORT_LAT - 0.1,
            "maxlat": self.PORT_LAT + 0.1,
            "minlon": self.PORT_LON - 0.1,
            "maxlon": self.PORT_LON + 0.1,
        }
        
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = resp.json()
            if data:
                df = pd.DataFrame(data)
                return self._process_ais_data(df)
        except Exception:
            pass
        return pd.DataFrame()
    
    def fetch_from_marinetraffic_embed(self) -> pd.DataFrame:
        """
        Scrape basic data from MarineTraffic's free embed/widget data.
        Very limited but sometimes works.
        """
        url = f"https://www.marinetraffic.com/en/data/?asset_type=vessels&columns=flag,shipname,photo,recognized_next_port,reported_eta,reported_destination,current_port,imo,ship_type,show_on_live_map,time_of_latest_position,lat_of_latest_position,lon_of_latest_position,notes&current_port_in|begins|DJENDJEN|port_id=2789"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            # This is heavily protected but sometimes basic data leaks
            script_tags = soup.find_all("script")
            for script in script_tags:
                if "vessels" in str(script):
                    # Try to extract JSON
                    match = re.search(r'\[{.*}\]', str(script))
                    if match:
                        data = json.loads(match.group())
                        return pd.DataFrame(data)
        except Exception:
            pass
        return pd.DataFrame()
    
    def _process_ais_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize AIS data columns."""
        rename = {
            "SHIPNAME": "Vessel Name",
            "NAME": "Vessel Name",
            "name": "Vessel Name",
            "vessel_name": "Vessel Name",
            "MMSI": "MMSI",
            "mmsi": "MMSI",
            "IMO": "IMO",
            "imo": "IMO",
            "LATITUDE": "Lat",
            "LONGITUDE": "Lon",
            "lat": "Lat",
            "lon": "Lon",
            "latitude": "Lat",
            "longitude": "Lon",
            "SOG": "Speed (kn)",
            "speed": "Speed (kn)",
            "COG": "Course",
            "HEADING": "Heading",
            "DESTINATION": "Destination",
            "destination": "Destination",
            "ETA": "ETA",
            "eta": "ETA",
            "TYPE_NAME": "Ship Type",
            "type_name": "Ship Type",
            "vessel_type": "Ship Type",
            "FLAG": "Flag",
            "flag": "Flag",
            "DRAUGHT": "Draft",
            "draught": "Draft",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        return df
    
    def get_best_available(self, aishub_key=None, datalastic_key=None) -> pd.DataFrame:
        """Try all free sources, return first successful result."""
        # Priority order
        sources = [
            ("AISHub", lambda: self.fetch_from_aishub(aishub_key)),
            ("Datalastic", lambda: self.fetch_from_datalastic(datalastic_key)),
            ("MyShipTracking", self.fetch_from_myshiptracking),
        ]
        
        for name, fetcher in sources:
            try:
                df = fetcher()
                if not df.empty:
                    st.caption(f"✅ AIS data from: {name}")
                    return df
            except Exception:
                continue
        
        return pd.DataFrame()


# ============================================================
#  FALLBACK MOCK DATA (when all sources fail)
# ============================================================

def get_fallback_data() -> dict:
    """Provides realistic mock data when scraping fails."""
    return {
        "berthed": pd.DataFrame([
            {"Vessel Name": "PRINCESS FAYZAH", "Stopover": "20250341", "Agent": "GEMA",
             "Berth": "Q1", "Cargo": "VEHICULES", "Status": "Operated"},
            {"Vessel Name": "SKY GATE", "Stopover": "20250347", "Agent": "SARL I.S.M.S",
             "Berth": "Q3", "Cargo": "MAIS", "Status": "Operated"},
            {"Vessel Name": "EEMS SUN", "Stopover": "20260002", "Agent": "GEMA",
             "Berth": "Q5", "Cargo": "ACIER", "Status": "Moored"},
            {"Vessel Name": "LORENZO", "Stopover": "20250339", "Agent": "SARL GASS",
             "Berth": "Q7", "Cargo": "CLINKER", "Status": "Operated"},
        ]),
        "anchored": pd.DataFrame([
            {"Vessel Name": "MARMARA PRINCESS", "Stopover": "20260001", "Agent": "GEMA",
             "Wait Time": "2 days", "Cargo": "BOIS"},
            {"Vessel Name": "FORTUNE EXPRESS", "Stopover": "20260008", "Agent": "GEMA",
             "Wait Time": "5 hours", "Cargo": "BILLETES D'ACIER"},
        ]),
        "expected": pd.DataFrame([
            {"Vessel Name": "MSC AMALFI", "ETA": "2026-01-15 14:00",
             "Origin": "GENOVA", "Cargo": "CONTAINERS"},
            {"Vessel Name": "NORDIC STAVANGER", "ETA": "2026-01-16 08:00",
             "Origin": "ISKENDERUN", "Cargo": "ACIER"},
        ]),
        "timestamp": datetime.now(),
        "source": "fallback"
    }


# ============================================================
#  DASHBOARD UI
# ============================================================

@st.dialog("📋 Vessel Details")
def show_details_popup(title: str, df: pd.DataFrame):
    st.subheader(title)
    if df.empty:
        st.info("No data available")
        return
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Download button
    csv = df.to_csv(index=False)
    st.download_button(
        "📥 Download CSV",
        csv,
        f"djendjen_{title.lower().replace(' ', '_')}_{datetime.now():%Y%m%d}.csv",
        "text/csv"
    )


def render_vessel_map(ais_df: pd.DataFrame):
    """Render vessel positions on a map."""
    if ais_df.empty or "Lat" not in ais_df.columns:
        # Show static port location
        map_df = pd.DataFrame({
            "lat": [36.8206],
            "lon": [5.7525],
            "name": ["Port of Djendjen"]
        })
        st.map(map_df, latitude="lat", longitude="lon", zoom=12)
        return
    
    # Plot AIS positions
    fig = px.scatter_mapbox(
        ais_df,
        lat="Lat",
        lon="Lon",
        hover_name="Vessel Name" if "Vessel Name" in ais_df.columns else None,
        hover_data={c: True for c in ["Speed (kn)", "Destination", "Ship Type"] if c in ais_df.columns},
        color="Ship Type" if "Ship Type" in ais_df.columns else None,
        zoom=12,
        height=400,
        title="Vessels near Djendjen Port"
    )
    fig.update_layout(
        mapbox_style="carto-darkmatter",
        margin={"r": 0, "t": 30, "l": 0, "b": 0},
        paper_bgcolor="#0a0a0a",
        font_color="#ccc",
    )
    st.plotly_chart(fig, use_container_width=True)


def dashboard():
    # --- HEADER ---
    st.markdown("""
        <div class="dashboard-header">
            <h1>🚢 Port de Djendjen — Live Operations</h1>
            <p>
                <span class="live-dot"></span>
                Real-time vessel tracking &amp; port operations
                <span class="source-badge" style="margin-left: 12px;">LIVE DATA</span>
            </p>
        </div>
    """, unsafe_allow_html=True)

    # --- SIDEBAR CONFIG ---
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        st.subheader("🔑 API Keys (Optional)")
        st.caption("Add free API keys for AIS vessel tracking data")
        aishub_key = st.text_input(
            "AISHub API Key",
            type="password",
            help="Register free at aishub.net (requires sharing AIS data)"
        )
        datalastic_key = st.text_input(
            "Datalastic API Key",
            type="password",
            help="Register free at datalastic.com (100 req/month)"
        )
        
        st.divider()
        
        auto_refresh = st.toggle("Auto-refresh", value=True)
        refresh_interval = st.select_slider(
            "Refresh interval",
            options=[30, 60, 120, 300, 600],
            value=120,
            format_func=lambda x: f"{x//60}m {x%60}s" if x >= 60 else f"{x}s"
        )
        
        st.divider()
        
        show_map = st.toggle("Show vessel map", value=True)
        show_ais = st.toggle("Show AIS data", value=True)
        
        st.divider()
        if st.button("🔄 Refresh Now", use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()

    # --- FETCH DATA ---
    @st.cache_data(ttl=120, show_spinner=False)
    def load_port_data():
        scraper = DjendjenScraper()
        data = scraper.get_all_data()
        
        # Check if we got real data
        has_data = any(
            not data[k].empty for k in ["berthed", "anchored", "expected"]
        )
        
        if has_data:
            data["source"] = "live"
        else:
            data = get_fallback_data()
            data["source"] = "fallback"
        
        return data
    
    @st.cache_data(ttl=300, show_spinner=False)
    def load_ais_data(_aishub_key, _datalastic_key):
        fetcher = AISDataFetcher()
        return fetcher.get_best_available(_aishub_key, _datalastic_key)

    # Show loading status
    with st.spinner("📡 Fetching port data..."):
        port_data = load_port_data()
    
    ais_df = pd.DataFrame()
    if show_ais:
        with st.spinner("📡 Fetching AIS data..."):
            ais_df = load_ais_data(aishub_key, datalastic_key)

    # --- SOURCE INDICATOR ---
    col_status1, col_status2, col_status3 = st.columns([2, 1, 1])
    with col_status1:
        if port_data.get("source") == "live":
            st.success("🟢 Connected to djendjen-port.dz — Live data")
        else:
            st.warning("🟡 Using cached/demo data — Port website may be unavailable")
    with col_status2:
        st.caption(f"🕐 Updated: {port_data['timestamp']:%H:%M:%S}")
    with col_status3:
        if not ais_df.empty:
            st.caption(f"🛰️ AIS: {len(ais_df)} vessels tracked")

    st.divider()

    # --- METRICS ROW ---
    df_berthed = port_data.get("berthed", pd.DataFrame())
    df_anchored = port_data.get("anchored", pd.DataFrame())
    df_expected = port_data.get("expected", pd.DataFrame())

    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "🚢 Ships Berthed",
            len(df_berthed),
            delta="In Port",
            delta_color="normal"
        )
        if not df_berthed.empty:
            if st.button("🔍 View Details", key="btn_berthed", use_container_width=True):
                show_details_popup("Ships Currently Berthed", df_berthed)
    
    with col2:
        st.metric(
            "⚓ At Anchor",
            len(df_anchored),
            delta="Waiting",
            delta_color="off"
        )
        if not df_anchored.empty:
            if st.button("🔍 View Details", key="btn_anchored", use_container_width=True):
                show_details_popup("Ships at Anchor", df_anchored)
    
    with col3:
        st.metric(
            "📅 Expected",
            len(df_expected),
            delta="Incoming",
            delta_color="normal"
        )
        if not df_expected.empty:
            if st.button("🔍 View Details", key="btn_expected", use_container_width=True):
                show_details_popup("Expected Arrivals", df_expected)
    
    with col4:
        total = len(df_berthed) + len(df_anchored) + len(df_expected)
        st.metric(
            "📊 Total Vessels",
            total,
            delta="All categories"
        )

    st.divider()

    # --- VESSEL MAP ---
    if show_map:
        st.subheader("🗺️ Vessel Positions")
        render_vessel_map(ais_df)
        st.divider()

    # --- MAIN DATA TABLES ---
    tab_berthed, tab_anchored, tab_expected, tab_ais = st.tabs([
        "🚢 Berthed", "⚓ Anchored", "📅 Expected", "🛰️ AIS Live"
    ])
    
    with tab_berthed:
        st.subheader("Ships Currently Berthed")
        if not df_berthed.empty:
            # Color-code status if available
            st.dataframe(
                df_berthed,
                use_container_width=True,
                hide_index=True,
                height=400,
            )
        else:
            st.info("No berthed vessel data available")
    
    with tab_anchored:
        st.subheader("Ships at Anchor / Waiting")
        if not df_anchored.empty:
            st.dataframe(
                df_anchored,
                use_container_width=True,
                hide_index=True,
                height=400,
            )
        else:
            st.info("No anchored vessel data available")
    
    with tab_expected:
        st.subheader("Expected Arrivals")
        if not df_expected.empty:
            st.dataframe(
                df_expected,
                use_container_width=True,
                hide_index=True,
                height=400,
            )
        else:
            st.info("No expected vessel data available")
    
    with tab_ais:
        st.subheader("AIS Vessel Tracking Data")
        if not ais_df.empty:
            st.dataframe(
                ais_df,
                use_container_width=True,
                hide_index=True,
                height=400,
            )
        else:
            st.info(
                "No AIS data. Add API keys in sidebar or check free sources:\n\n"
                "- **AISHub**: [aishub.net](https://www.aishub.net/) — Free with data sharing\n"
                "- **Datalastic**: [datalastic.com](https://datalastic.com/) — 100 free req/month\n"
            )

    st.divider()

    # --- ANALYTICS ---
    st.subheader("📊 Port Analytics")
    
    t_cargo, t_berth, t_timeline = st.tabs(["Cargo Analysis", "Berth Utilization", "Timeline"])
    
    with t_cargo:
        if not df_berthed.empty and "Cargo" in df_berthed.columns:
            cargo_counts = df_berthed["Cargo"].value_counts().reset_index()
            cargo_counts.columns = ["Cargo Type", "Count"]
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                fig = px.pie(
                    cargo_counts, names="Cargo Type", values="Count",
                    title="Cargo Distribution (Berthed Ships)",
                    color_discrete_sequence=px.colors.sequential.YlOrBr,
                    hole=0.4,
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#ccc",
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col_c2:
                fig = px.bar(
                    cargo_counts, x="Cargo Type", y="Count",
                    title="Cargo Counts",
                    color="Count",
                    color_continuous_scale="YlOrBr",
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#ccc",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            # Generate synthetic data for demo
            dates = pd.date_range(end=datetime.today(), periods=14)
            cargo_df = pd.DataFrame({
                "Date": dates,
                "Tonnage": np.random.randint(2000, 8000, size=14),
                "Type": np.random.choice(["Import", "Export"], size=14),
            })
            fig = px.bar(
                cargo_df, x="Date", y="Tonnage", color="Type",
                barmode="group",
                title="Daily Cargo Flow (Simulated)",
                color_discrete_sequence=["#FFD700", "#4169E1"],
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ccc",
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with t_berth:
        col_b1, col_b2, col_b3 = st.columns(3)
        
        # Calculate berth utilization from real data
        total_berths = 14  # Djendjen has ~14 berths
        occupied = len(df_berthed) if not df_berthed.empty else 0
        utilization = (occupied / total_berths) * 100
        
        col_b1.metric("Berth Utilization", f"{utilization:.0f}%",
                      delta="High" if utilization > 70 else "Normal")
        col_b2.metric("Available Berths", f"{total_berths - occupied}",
                      delta=f"of {total_berths} total")
        col_b3.metric("Vessels Waiting", f"{len(df_anchored)}",
                      delta="At anchor")
        
        # Berth gauge
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=utilization,
            title={"text": "Port Capacity Usage (%)"},
            delta={"reference": 75},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#FFD700"},
                "steps": [
                    {"range": [0, 50], "color": "#1a3a1a"},
                    {"range": [50, 75], "color": "#3a3a1a"},
                    {"range": [75, 100], "color": "#3a1a1a"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 3},
                    "thickness": 0.8,
                    "value": 90,
                },
            },
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#ccc",
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with t_timeline:
        st.caption("Expected arrivals timeline")
        if not df_expected.empty and "ETA" in df_expected.columns:
            try:
                df_timeline = df_expected.copy()
                df_timeline["ETA_parsed"] = pd.to_datetime(df_timeline["ETA"], errors="coerce")
                df_timeline = df_timeline.dropna(subset=["ETA_parsed"])
                
                if not df_timeline.empty:
                    name_col = "Vessel Name" if "Vessel Name" in df_timeline.columns else df_timeline.columns[0]
                    fig = px.timeline(
                        df_timeline,
                        x_start="ETA_parsed",
                        x_end="ETA_parsed",
                        y=name_col,
                        title="Expected Arrivals",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Could not parse ETA dates")
            except Exception as e:
                st.info(f"Timeline unavailable: {e}")
        else:
            st.info("No ETA data to display")

    # --- FOOTER ---
    st.divider()
    st.markdown(f"""
        <div style="text-align: center; color: #555; font-size: 0.8rem; padding: 1rem;">
            📡 Data sources: djendjen-port.dz (primary) | AIS APIs (supplementary)<br>
            Last refresh: {port_data['timestamp']:%Y-%m-%d %H:%M:%S} | 
            Source: <span class="source-badge">{port_data.get('source', 'unknown').upper()}</span>
        </div>
    """, unsafe_allow_html=True)

    # --- AUTO REFRESH ---
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

