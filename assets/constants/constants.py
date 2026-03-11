
from pathlib import Path

PATH_BRDX = "reports/bordereaux"
PATH_PVS = "reports/pvs"
PATH_TEMPLATES = "assets/templates"
FIXED_STAFF_PATH = "assets/templates/staff_template.csv"

WORKFORCE_DB = "data/workforce1.xlsx"

DEFAULT_OPS_LOG_PATH = Path("data/ops_log.csv")

PATH_DEBRQ = "data/debarqs"
UPLOAD_DIR = "data/uploads"
DB_PATH = "data/database.xlsx"
MAP_IMAGE_PATH = "assets/map/port_map.png"

COLUMNS = [
    "ESCALE",
    "NAVIRE",
    "DATE",
    "B/L",
    "DESIGNATION",
    "QUANTITE",
    "TONAGE",
    "CLIENT",
    "CHASSIS/SERIAL",
    "RESTE T/P",
    "TYPE",
    "SITUATION",
    "OBSERVATION",
    "POSITION",
    "TRANSIT",
    "CLES",
    "SURFACE",
    "DAEMO BREAKER (DRB) TOP BOX TYPE",
    "DATE ENLEV",
    "CARGO_TYPE",
]

COMMODITY_TYPES = ["PLYWOOD", "BIGBAG", "TUBE", 
                   "BEAMS", "FIL M", "COIL"]

GOODS__TYPES={"PLYWOOD", "BIG BAG", "TUBE","BEAMS", "FIL M", "COIL","BOB","CTP"}

# "OTHERS"
(   COL_ESCALE,
    COL_NAVIRE,
    COL_DATE,
    COL_BL,
    COL_DESIGNATION,
    COL_QUANTITE,
    COL_TONAGE,
    COL_CLIENT,
    COL_CHASSIS_SERIAL,
    COL_RESTE_TP,
    COL_TYPE,
    COL_SITUATION,
    COL_OBSERVATION,
    COL_POSITION,
    COL_TRANSIT,
    COL_CLES,
    COL_SURFACE,
    COL_DRB_TYPE,
    COL_DATE_ENLEV,
    COL_CARGO_TYPE,
) = COLUMNS

# "UNITS", "PACKAGES"
UNITS_TYPES = {"UNITS", "LOURD","ENGIN","GRUE","EXV","CAM","RMQ","NVL"}
PACKAGES_TYPES = {"COLI", "UNITS", "PACKAGE", "CAISSE"}



DEFAULT_LOCATIONS = [
    "Quay",
    "Hangar",
    "Air area",
    "Yard A",
    "Yard B",
    "Warehouse 1",
    "Warehouse 2",
    "Other"
]



# 1. Numeric Group (Must be float/int, handles math)
numeric_cols = ["QUANTITE", "TONAGE", "RESTE T/P", "SURFACE"]

# 2. Date Group (Must be datetime objects or None)
date_cols = ["DATE", "DATE ENLEV"]

# 3. Selection Group (Must match your SelectboxColumn options)
category_cols = ["TYPE", "SITUATION", "CLES"]

# 4. Text Group (Everything else - must be forced to String/Object)
text_cols = [
    "NAVIRE", "B/L", "DESIGNATION", "CLIENT", "CHASSIS/SERIAL", 
    "OBSERVATION", "POSITION", "TRANSIT", "DAEMO BREAKER (DRB) TOP BOX TYPE"
]