# Djendjen Port Logistics Portal

## Overview
A Streamlit-based port logistics management application for Port Djendjen. Handles ship manifests, cargo tracking, workforce management, and port operations.

## Tech Stack
- **Language**: Python 3.12
- **Framework**: Streamlit
- **Data**: Pandas, Excel (openpyxl, xlsxwriter)
- **Visualization**: Plotly, Pydeck
- **Documents**: python-docx

## Project Structure
- `main.py` - Main Streamlit app entry point
- `modules/` - Feature modules (Dashboard, Manifest Tracker, State Manager, Port Map, Workforce Tracking, Logistics Tools)
- `assets/` - Static assets, constants, templates, port map image
- `assets/constants/constants.py` - App-wide constants (paths, column definitions, cargo types)
- `tools/tools.py` - Shared utility functions (document generation, data processing)
- `data/` - Runtime data directory (uploads, database.xlsx, archive)
- `reports/` - Generated reports (bordereaux, pvs, debarqs)
- `.streamlit/config.toml` - Streamlit server configuration (port 5000, host 0.0.0.0)

## Key Data Paths
- `data/database.xlsx` - Master ship/cargo database
- `data/uploads/` - Uploaded manifest files
- `data/workforce1.xlsx` - Workforce tracking data
- `assets/map/port_map.png` - Port map image

## Navigation Modules
1. **Dashboard** - Port overview, ship status
2. **Manifest Tracker** - B/L tracking and cargo verification
3. **State Manager** - Global/single file loading manager
4. **Port Map** - Interactive ship position map
5. **Workforce Tracking** - Staff/tally shift management
6. **Logistics Tools** - Surface area calculators

## Running
The app runs via the "Start application" workflow:
```
streamlit run main.py
```
Served on port 5000 at `0.0.0.0`.
