from pathlib import Path

#PATH_REPORTS="reports/"
PATH_BRDX = "reports/bordereaux"
PATH_PVS = "reports/pvs"
PATH_DEBRQ = "reports/debarqs"

#PATH_ASSETS="assets/"
PATH_TEMPLATES = "assets/templates"
FIXED_STAFF_PATH = "assets/templates/staff_template.csv"
MAP_IMAGE_PATH = "assets/map/port_map.png"


DEFAULT_OPS_LOG_PATH = Path("data/ops_log.csv")
WORKFORCE_DB = "data/workforce1.xlsx"
#DATA_PATH = "data/"
DATA_PATH_ARCH = "data/archive"
UPLOAD_DIR = "data/uploads"
DB_PATH = "data/database.xlsx"



# Use .parent for file paths to get their containing directory
LIST_OF_PATHS = [
    PATH_BRDX, 
    PATH_PVS, 
    PATH_TEMPLATES, 
    PATH_DEBRQ, 
    UPLOAD_DIR, 
    DATA_PATH_ARCH,
]

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
    "PRODUIT",
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

COMMODITY_TYPES = ["CTP","MDF","PLYWOOD","BIGBAG", "TUBE", "BEAMS", "FIL M", "COIL","FORMWORK","PIPE","METAL SHEET"]

#GOODS__TYPES={"CTP","MDF","PLYWOOD", "BIG BAG" ,"BAG", "TUBE","PIPE","BEAMS", "FIL M","FIL", "COIL","BOB","FORMWORK","METAL SHEET"}
GOODS__TYPES = {"COIL", "METAL SHEET", "STEEL BEAMS", "FIL M", "FORMWORK", "MDF", "CTP", "PIPE",  "BIG BAG", }
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
    COL_PRODUIT,
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


# Define cargo type categories based on KEYWORD_RULES
UNIT_CARGO_TYPES = {
    "BUS", "MIXER_TRUCK", "CTRN_TRUCK", "DUMP_TRUCK", "TRACTOR_TRUCK",
    "SPECIAL_TRUCK", "MINING_TRUCK", "LIGHT_TRUCK", "CARGO_TRUCK",
    "LOWBED_TRAILER", "DUMP_TRAILER", "CEMENT_TRAILER", "CTRN", "SEMI_TRAILER",
    "EXCAVATOR", "LOADER", "BULLDOZER", "ROLLER", "GRADER", "CRANE",
    "FORKLIFT", "CONCRETE_PUMP", "CRUSHER", "DRILLING_RIG", "BACKHOE",
    "ASPHALT_EQUIP", "SELF_LOADER", "BREAKER",
    "WELL_LOG_TRUCK", "PUMP_SKID", "CAMP",  "LOURD","ENGIN","GRUE","EXV","CAM","RMQ","NVL",
}

PACKAGE_CARGO_TYPES = {
    "SPARE_PARTS", "WELDING_EQUIP", "ROLLER_PAD", "COOLED_PANEL", "ZINC_KETTLE",
    "COLI", "PACKAGE","PKGS" ,"CAISSE"
}




#  "PACKAGES"
UNITS_TYPES = { "LOURD","ENGIN","GRUE","EXV","CAM","RMQ","NVL"}
PACKAGES_TYPES = {"COLI",  "PACKAGE", "CAISSE"}


KEYWORD_RULES = [
    # ══════════════════════════════════════════════════════════
    # ORDER MATTERS! More specific rules MUST come first.
    # Each tuple: ( [list_of_keywords], "CARGO_TYPE" )
    # ══════════════════════════════════════════════════════════

    # ── INDUSTRIAL / MISC ─────────────────────────────────────
    (["WELDING MACHINE", "HOISTING EQUIPMENT"], "WELDING_EQUIP"),
    (["WELL LOGGING"], "WELL_LOG_TRUCK"),
    (["CEMENTING SKID", "FUEL SUPPLY"], "PUMP_SKID"),
    (["COOLED PANEL"], "COOLED_PANEL"),
    (["CAMP"], "CAMP"),
    (["ZINC KETTLE"], "ZINC_KETTLE"),
    (["ROLLER FOOT PAD", "FOOT PAD"], "ROLLER_PAD"),
    # ── SPARE PARTS ───────────────────────────────────────────
    (["PKGS","SPARE PART", "TRUCK PART", "TRANSMISSION",
      "BUCKET"], "SPARE_PARTS"),
    # ── STRUCTURAL / BRIDGE ───────────────────────────────────
    (["BRIDGE", "GIRDER ERECTION", 
      "COMPONENTS FOR BRIDGE"], "BRIDGE_COMP"),


    # ── UTILITIES (specific → generic) ─────────────────────────
    (["UNITS","AUTOBUS", "AUTOCAR", "MINI BUS", "MINIBUS", "MICRO BUS",
      "19 SEAT", "15 SEAT", "BUS"], "BUS"),

    (["CONCRETE MIXER", "MIXER TRUCK", "MIXER"], "MIXER_TRUCK"),

    (["WATER TANKER", "WATER TANK TRUCK", "WATER SPRINKLER",
      "SPRINKLER", "FUEL TRUCK", "FUEL TANKER"], "CTRN_TRUCK"),

    (["DUMP TRUCK", "TIPPER TRUCK", "TIPPER", "BENNE",
      "CAMION AC A BENNE"], "DUMP_TRUCK"),

    (["TRACTOR TRUCK", "TRACTOR", "TRACTEUR ROUTIER",
      "TRACTEUR"], "TRACTOR_TRUCK"),

    (["FRIGORIFIQUE", "REFRIGER", "PLATEAU AVEC GRUE","TRI-AXLELOWEBED"], "SPECIAL_TRUCK"),

    (["MINING DUMP", "MINING DUMPER", "OFF ROAD MINING"], "MINING_TRUCK"),

    (["LIGHT TRUCK", "PICKUP", "DFSK", "K02L"], "LIGHT_TRUCK"),

    (["CARGO TRUCK", "FLATBED TRUCK", "CHASSIS TRUCK",
      "CAMION PLATEAU", "CAMION CHASSIS", "CABIN CARGO",
      "CARGO TRUCK CHASSIS", "CABIN SINGLE", "CABIN DOUBLE",
      "DOUBLE CABINE", "SINGLE CABIN CARGO","FREIGHT","SHACMAN","TRUCK"], "CARGO_TRUCK"),

    # ── TRAILERS (specific → generic) ─────────────────────────
    (["LOW BED", "LOWBED"], "LOWBED_TRAILER"),

    (["SIDE DUMPING", "REAR DUMP SEMI", "DUMP TRAILER",
      "DUMPING TRAILER", "DUMP SEMI"], "DUMP_TRAILER"),

    (["BULK CEMENT", "CEMENT TRAILER", "CEMENT SEMI"], "CEMENT_TRAILER"),

    (["CITERNE"], "CTRN"),

    (["SEMI TRAILER", "SEMI REMORQUE", "CURTAIN TRAILER",
      "SIDEWALL TRAILER", "CARGO TRAILER", "FLATBED SEMI",
      "DROPSIDE SEMI", "CARGO SEMI","semi-trailer ","SEMI"], "SEMI_TRAILER"),

    # ── CONSTRUCTION EQUIPMENT ────────────────────────────────
    (["EXCAVATOR", "PELLE HYDRAUL", "CRAWLER EXCAVATOR"], "EXCAVATOR"),

    (["WHEEL LOADER", "CHARGEUR WHEEL", "CHARGEUR"], "LOADER"),

    (["BULLDOZER"], "BULLDOZER"),

    (["ROAD ROLLER", "TYRE COMPACTOR", "PNEUMATIC ROLLER",
      "TYRE ROAD ROLLER", "COMPACTOR XP", "ROLLER XP",
      "ROLLER XS", "ROLLER XD","PAVER"], "ROLLER"),

    (["GRADER", "NIVELEUSE"], "GRADER"),

    (["TRUCK CRANE", "MOBILE CRANE"], "CRANE"),

    (["FORKLIFT", "CHARIOT ELEVATEUR"], "FORKLIFT"),

    (["CONCRETE PUMP", "POMPE A BETON", "TRUCK PUMP",
      "CONCRETTE PUMP"], "CONCRETE_PUMP"),

    (["CRUSHING PLANT", "CRUSHER"], "CRUSHER"),

    (["DRILLING RIG", "FORAGE", "COMPRESSEURS"], "DRILLING_RIG"),

    (["BACKHOE", "BACHOE"], "BACKHOE"),

    (["ASPHALT DISTRIBUTOR"], "ASPHALT_EQUIP"),

    (["SELF LOADING MIXER", "SELF-LOADING"], "SELF_LOADER"),

    (["BREAKER", "HAMMER"], "BREAKER"),

    # ── STEEL PRODUCTS ────────────────────────────────────────
    ([ "BOB","STEEL COIL", "ROLLED STEEL COIL", "ROLLED COIL",
      "PREPAINTED STEEL COIL", "GALVANIZED STEEL COIL",
      "GALVANISED STEEL COIL", "GALVANIZED COIL",
      "ZINC-ALUMINIUM-STEEL COIL", "COLD ROLLED COIL",
      "HOT ROLLED COIL", "PRE-PAINTED STEEL COIL",
      "PREPAINTED GALVAN","COIL","STEEL STRIP", "GI STEEL STRIP", "GALVANIZED STEEL STRIP",
      "GALVANISED STEEL STRIP", "GALVANIZED STRIP",
      "HOT DIP GALVANIZED STEEL STRIP",
      "HOT DIPPED GALVANISED STEEL STRIP"], "COIL"),


    (["SHEET STEEL", "STEEL SHEET", "TOLE LAMIN","TOLE"], "METAL SHEET"),

    (["H-BEAM", "STEEL H-BEAM", "STEEL CHANNEL",
      "HOT ROLLED STEEL H","BEAMS","ANGLE BARS" ], "STEEL BEAMS"),
    
    (["FIL MACHINE","FIL M","FIL","STEEL WIRE", "COIL TUBING", "WIRE ROD",
      "CARBON STEEL COIL TUBING"], "FIL M"),

    (["STEEL FORMWORK","FORMWORK","STEEL MOULDS", "STEEL TEMPLATE",
      "HOLLOW PIER STEEL"], "FORMWORK"),

    # ── WOOD / PANEL PRODUCTS ─────────────────────────────────
    (["PLYWOOD","FILM","FILM FACED","COMMERCIAL","MDF"], "MDF"),
    (["VENEER","EDGE GLUED","BLOCKBOARD","CTP"], "CTP"),

    # ── TUBES ─────────────────────────────────────────────────
    (["TUBE", "SEAMLESS BOILER","ECHAFFAUDAGE",
      "STEEL PIPE", "GALVANIZED STEEL PIPE","PIPE"], "PIPE"),


    # ── RAW MATERIALS ─────────────────────────────────────────
    
    (["BIG BAG","BAG","RESINE","CHEMICAL" ,"PET", "POLYESTER CHIPS","QUARTZ SAND", "ANTHRACITE COAL","Anthracite","Coal", "CALCINED"], "BIG BAG"),

    

]



























