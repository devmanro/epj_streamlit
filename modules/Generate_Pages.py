# ============================================================
# PAGE: Generate_Sheets
# ============================================================

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import date
import os
import re
import io
import threading
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TODAY        = date.today()
TODAY_STR    = TODAY.strftime("%d-%m-%Y")
RST_SHEET_NAME = "RST-10-10-2026"
SOURCE_FILE  = "manifest_source.xlsx"
OUTPUT_FILE  = "output_omar.xlsx"

# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------
TYPE_MAP = {
    "MARCHANDISES DIVERS": [
        "COLIS","ENGIN","CABINES","CAISSES","LEGER","LOURD",
        "UTILITAIRE","PALLETES","CITERNE","UNITES","PACKAGES",
    ],
    "MINERAIS ET PRODUITS METALLURGIQUES": [
        "TUBES","CORNIERES","FIL MACHINE","ROND A BETON","BOBINES",
        "POUTRELLES","CHARPENTE METALIQUE","COUDES","ELINGUES",
        "TOLES EN PLAQUES","BILLETTES","FER PLAT","RAILS","TOLES",
        "BARRES","IRON ORE","PELLETS","HBI","CDRI","BITUME",
        "CONTENEUR","ENGINES","MDF","PLYWOOD","BOIS",
    ],
    "PRODUITS AGRICOLES / DENREES ALIMENTAIRES": [
        "BLE","HUILE DE SOJA","AVOINE","MAIS","HARICOT",
    ],
    "MINERAUX ET MATERIAUX DE CONSTRUCTION": [
        "ANHYDRITE","ARGILE","BALL CLAY","CIMENT","CLINKERS",
        "FELDSPAR","KAOLIN","MARBRE","SABLE SILICEUX","BOIS BLANC","BOIS ROUGE",
    ],
    "ENGRAIS ET PRODUITS CHIMIQUES": [
        "SULFATE","SULFATE DE SOUDE","SODIUM","PVC","PVC EDGE BANDING",
    ],
    "PRODUITS PETROLIERS": ["BITUME"],
}

_KEYWORD_TO_TYPE: dict[str, str] = {}
for _cat, _keywords in TYPE_MAP.items():
    for _kw in _keywords:
        _KEYWORD_TO_TYPE[_kw.upper()] = _cat


# ---------------------------------------------------------------------------
# Core logic helpers
# ---------------------------------------------------------------------------
def gs_type_function(item: str) -> str:
    if not isinstance(item, str):
        return "MARCHANDISES DIVERS"
    item_upper = item.strip().upper()
    if item_upper in _KEYWORD_TO_TYPE:
        return _KEYWORD_TO_TYPE[item_upper]
    best_match, best_cat = "", "MARCHANDISES DIVERS"
    for kw, cat in _KEYWORD_TO_TYPE.items():
        if kw in item_upper and len(kw) > len(best_match):
            best_match, best_cat = kw, cat
    return best_cat


def gs_extract_chassis(val) -> str:
    if pd.isna(val) or not str(val).strip():
        return ""
    s = re.sub(r"\s+", "", str(val).strip().upper())
    if not (8 <= len(s) <= 17):
        return ""
    if not (any(c.isalpha() for c in s) and any(c.isdigit() for c in s)):
        return ""
    if not re.match(r"^[A-Z0-9]+$", s):
        return ""
    return s


def gs_has_valid_chassis(row) -> bool:
    raw = gs_safe_val(row, "Némuro de chassis")
    return bool(gs_extract_chassis(raw))


def gs_safe_val(row, col: str):
    if col in row.index:
        val = row[col]
        return "" if pd.isna(val) else val
    return ""


def gs_marchandise_d(row):
    return gs_safe_val(row, "Marchandise")


def gs_marchandise_h(row):
    if "Marchandise.1" in row.index:
        return gs_safe_val(row, "Marchandise.1")
    return ""


def gs_normalize_number(val, as_int=False):
    if pd.isna(val) or str(val).strip() == "":
        return ""
    try:
        num = float(str(val).replace(",", ".").replace(" ", ""))
        return int(round(num)) if as_int else num
    except (ValueError, TypeError):
        return ""


def gs_filter_nombre_colis(df: pd.DataFrame):
    if "nombre colis" not in df.columns:
        return df.copy(), 0
    mask = df["nombre colis"].apply(
        lambda x: not pd.isna(x) and str(x).strip() != ""
    )
    filtered = df[mask].copy().reset_index(drop=True)
    return filtered, len(df) - len(filtered)


def gs_filter_valid_chassis(df: pd.DataFrame):
    if "Némuro de chassis" not in df.columns:
        return pd.DataFrame(columns=df.columns), len(df)
    mask = df.apply(gs_has_valid_chassis, axis=1)
    filtered = df[mask].copy().reset_index(drop=True)
    return filtered, len(df) - len(filtered)


# ---------------------------------------------------------------------------
# Styling constants
# ---------------------------------------------------------------------------
HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT  = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
SUBHDR_FILL  = PatternFill("solid", fgColor="2E75B6")
DATA_FONT    = Font(name="Calibri", size=10)
ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALIGN_LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=True)
THIN         = Side(border_style="thin", color="B8CCE4")
BORDER       = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
ALT1_FILL    = PatternFill("solid", fgColor="DEEAF1")
ALT2_FILL    = PatternFill("solid", fgColor="FFFFFF")
DATE_FMT     = "DD/MM/YYYY"
NUM_FMT      = "#,##0.00"
INT_FMT      = "#,##0"


def _style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment, cell.border = ALIGN_CENTER, BORDER


def _style_data(ws, row, ncols, alt):
    fill = ALT1_FILL if alt else ALT2_FILL
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill, cell.font = fill, DATA_FONT
        cell.alignment, cell.border = ALIGN_LEFT, BORDER


def _auto_width(ws, mn=10, mx=40):
    for col_cells in ws.columns:
        ml = max(
            (len(str(cell.value)) for cell in col_cells if cell.value is not None),
            default=0,
        )
        ws.column_dimensions[
            get_column_letter(col_cells[0].column)
        ].width = min(max(ml + 2, mn), mx)


def _freeze(ws, row=2):
    ws.freeze_panes = ws.cell(row=row, column=1)


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------
def gs_build_navires(ws, df: pd.DataFrame, append: bool, cancel_flag: threading.Event):
    headers = [
        "N° ESCALE","NAVIRE","CONSIGNATAIRE","QUAI","DATE","EMBARQ/DEBARQ",
        "TYPES","PRODUITS","DETAIL","QUANTITE","TONNAGE","CLIENTS",
        "DATE FINITION OPERATION","FIN ENLEVEMENT","JOURS","ENTREPOSAGE",
        "SURFACE","BL / TRANSITAIRE","ADRESSE","N° CHASSIS",
    ]

    df_f, skipped = gs_filter_nombre_colis(df)

    if not append:
        for ci, h in enumerate(headers, 1):
            ws.cell(row=1, column=ci, value=h)
        _style_header(ws, 1, len(headers))
        ws.row_dimensions[1].height = 30
        start_row = 2
    else:
        start_row = ws.max_row + 1

    chassis_list = [
        gs_extract_chassis(gs_safe_val(df_f.iloc[i], "Némuro de chassis"))
        for i in range(len(df_f))
    ]

    for idx in range(len(df_f)):
        if cancel_flag.is_set():
            return None, None           # signal cancellation

        er  = start_row + idx
        row = df_f.iloc[idx]
        pv  = str(gs_safe_val(row, "PRODUITS"))

        values = [
            gs_safe_val(row, "escale_numb"),
            gs_safe_val(row, "navire_name"),
            gs_safe_val(row, "CONSIGNATAIRE"),
            "",
            gs_safe_val(row, "DATE"),
            gs_safe_val(row, "EMBARQ/DEBARQ"),
            gs_type_function(pv),
            pv,
            gs_marchandise_d(row),
            gs_normalize_number(gs_safe_val(row, "nombre colis"), True),
            gs_normalize_number(gs_safe_val(row, "Poids brute")),
            gs_safe_val(row, "Client"),
            None,
            TODAY,
            f'=IFERROR(N{er}-M{er},"")',
            "TP",
            gs_normalize_number(gs_safe_val(row, "SURF")),
            gs_safe_val(row, "BL"),
            "",
            chassis_list[idx],
        ]

        for ci, v in enumerate(values, 1):
            ws.cell(row=er, column=ci, value=v)

        _style_data(ws, er, len(headers), alt=(idx % 2 == 0))
        ws.row_dimensions[er].height = 18
        ws.cell(er,  5).number_format = DATE_FMT
        ws.cell(er, 13).number_format = DATE_FMT
        ws.cell(er, 14).number_format = DATE_FMT
        ws.cell(er, 10).number_format = INT_FMT
        ws.cell(er, 11).number_format = NUM_FMT
        ws.cell(er, 17).number_format = NUM_FMT

    if not append:
        _auto_width(ws)
        _freeze(ws, 2)

    return len(df_f), skipped


def gs_build_chassis(ws, df: pd.DataFrame, append: bool, cancel_flag: threading.Event):
    headers = [
        "NAVIRE","N° BL","Article","Marchandise","PRODUITS",
        "nombre colis","Poids brute","Client","Marchandise",
        "Némuro de chassis","MODEL","DESIGNATION",
    ]
    hints = [
        "","","","(col D source)","(Détails PRODUITS)","","","",
        "(col H source)","(extracted)","","(col D source)",
    ]

    df_f, skipped = gs_filter_valid_chassis(df)

    if not append:
        for ci, h in enumerate(headers, 1):
            ws.cell(row=1, column=ci, value=h)
        _style_header(ws, 1, len(headers))
        ws.row_dimensions[1].height = 30
        for ci, hint in enumerate(hints, 1):
            cell = ws.cell(row=2, column=ci, value=hint)
            cell.fill      = SUBHDR_FILL
            cell.font      = Font(name="Calibri", bold=True, color="FFFFFF", size=9, italic=True)
            cell.alignment = ALIGN_CENTER
            cell.border    = BORDER
        ws.row_dimensions[2].height = 14
        start_row = 3
    else:
        start_row = ws.max_row + 1

    for idx in range(len(df_f)):
        if cancel_flag.is_set():
            return None, None

        er  = start_row + idx
        row = df_f.iloc[idx]

        values = [
            gs_safe_val(row, "navire_name"),
            gs_safe_val(row, "BL"),
            gs_safe_val(row, "Article"),
            gs_marchandise_d(row),
            gs_safe_val(row, "Détails PRODUITS"),
            gs_normalize_number(gs_safe_val(row, "nombre colis"), True),
            gs_normalize_number(gs_safe_val(row, "Poids brute")),
            gs_safe_val(row, "Client"),
            gs_marchandise_h(row),
            gs_safe_val(row, "Némuro de chassis"),
            gs_safe_val(row, "Modèle"),
            gs_marchandise_d(row),
        ]

        for ci, v in enumerate(values, 1):
            ws.cell(row=er, column=ci, value=v)

        _style_data(ws, er, len(headers), alt=(idx % 2 == 0))
        ws.row_dimensions[er].height = 18
        ws.cell(er, 6).number_format = INT_FMT
        ws.cell(er, 7).number_format = NUM_FMT

    if not append:
        _auto_width(ws)
        _freeze(ws, 3)

    return len(df_f), skipped


def gs_build_rst(ws, df: pd.DataFrame, append: bool, cancel_flag: threading.Event):
    headers = [
        "N° ESCALE","NAVIRE","DATE D'ENTREE","DATE FINITION",
        "QUANTITE MANIFETE","TONNAGE MANIFETE","SURFACE MANIFETE","CLIENT",
        "Détails PRODUITS","PRODUITS","08 J","2 M 08 J","N° GROS / MRN",
        "RESTE QUANTITE","RESTE TONNAGE","RESTE SURFACE","B/L",
        "CRN / ART","DESIGNATION","LATITUDE","LONGITUDE","ETAT",
    ]

    df_f, skipped = gs_filter_nombre_colis(df)

    if not append:
        for ci, h in enumerate(headers, 1):
            ws.cell(row=1, column=ci, value=h)
        _style_header(ws, 1, len(headers))
        ws.row_dimensions[1].height = 30
        start_row = 2
    else:
        start_row = ws.max_row + 1

    for idx in range(len(df_f)):
        if cancel_flag.is_set():
            return None, None

        er  = start_row + idx
        row = df_f.iloc[idx]

        qte     = gs_normalize_number(gs_safe_val(row, "nombre colis"), True)
        tonnage = gs_normalize_number(gs_safe_val(row, "Poids brute"))
        surface = gs_normalize_number(gs_safe_val(row, "SURF"))

        values = [
            gs_safe_val(row, "escale_numb"),
            gs_safe_val(row, "navire_name"),
            gs_safe_val(row, "DATE D'ENTREE"),
            "",
            qte, tonnage, surface,
            gs_safe_val(row, "Client"),
            gs_safe_val(row, "Détails PRODUITS"),
            gs_safe_val(row, "PRODUITS"),
            f'=IFERROR(D{er}+8,"")',
            f'=IFERROR(K{er}+8,"")',
            gs_safe_val(row, "MRN"),
            qte, tonnage, surface,
            gs_safe_val(row, "BL"),
            gs_safe_val(row, "Article"),
            gs_marchandise_d(row),
            "", "",
            "N-OP",
        ]

        for ci, v in enumerate(values, 1):
            ws.cell(row=er, column=ci, value=v)

        _style_data(ws, er, len(headers), alt=(idx % 2 == 0))
        ws.row_dimensions[er].height = 18
        for c in [3, 4, 11, 12]:
            ws.cell(er, c).number_format = DATE_FMT
        for c in [5, 14]:
            ws.cell(er, c).number_format = INT_FMT
        for c in [6, 7, 15, 16]:
            ws.cell(er, c).number_format = NUM_FMT

    if not append:
        _auto_width(ws)
        _freeze(ws, 2)

    return len(df_f), skipped


# ---------------------------------------------------------------------------
# Main generator (runs in background thread)
# ---------------------------------------------------------------------------
def gs_run_generation(raw: pd.DataFrame, cancel_flag: threading.Event, result: dict):
    """
    Builds output_omar.xlsx on disk and stores result dict.
    result keys set on completion: 'stats', 'error', 'cancelled'
    """
    try:
        # Load or create workbook
        if os.path.exists(OUTPUT_FILE):
            wb = load_workbook(OUTPUT_FILE)
        else:
            wb = Workbook()
            if "Sheet" in wb.sheetnames:
                wb.remove(wb["Sheet"])

        stats = {}

        # ── NAVIRES ────────────────────────────────────────────────────────
        sn = "NAVIRES"
        app = sn in wb.sheetnames
        if not app:
            ws = wb.create_sheet(sn)
            ws.sheet_view.showGridLines = False
        else:
            ws = wb[sn]
        kept, skipped = gs_build_navires(ws, raw, app, cancel_flag)
        if cancel_flag.is_set():
            result["cancelled"] = True
            return
        stats["NAVIRES"] = {"kept": kept, "skipped": skipped, "appended": app}

        # ── N° chassis ─────────────────────────────────────────────────────
        sn = "N° chassis"
        app = sn in wb.sheetnames
        if not app:
            ws = wb.create_sheet(sn)
            ws.sheet_view.showGridLines = False
        else:
            ws = wb[sn]
        kept, skipped = gs_build_chassis(ws, raw, app, cancel_flag)
        if cancel_flag.is_set():
            result["cancelled"] = True
            return
        stats["N° chassis"] = {"kept": kept, "skipped": skipped, "appended": app}

        # ── RST ────────────────────────────────────────────────────────────
        sn = RST_SHEET_NAME
        app = sn in wb.sheetnames
        if not app:
            ws = wb.create_sheet(sn)
            ws.sheet_view.showGridLines = False
        else:
            ws = wb[sn]
        kept, skipped = gs_build_rst(ws, raw, app, cancel_flag)
        if cancel_flag.is_set():
            result["cancelled"] = True
            return
        stats[RST_SHEET_NAME] = {"kept": kept, "skipped": skipped, "appended": app}

        # Save to disk
        wb.save(OUTPUT_FILE)
        result["stats"] = stats

    except Exception as exc:
        result["error"] = str(exc)


# ---------------------------------------------------------------------------
# Streamlit page
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Streamlit page
# ---------------------------------------------------------------------------
def page_generate_sheets():
    st.title("📋 Generate Sheets")
    st.caption(
        f"Upload a source file to generate and update **`{OUTPUT_FILE}`**."
    )

    # ── File uploader ──────────────────────────────────────────────────────
    uploaded_file = st.file_uploader("📂 Upload Source Manifest File (Excel)", type=["xlsx", "xls"])
    if uploaded_file is not None:
        with open(SOURCE_FILE, "wb") as f:
            f.write(uploaded_file.getbuffer())

    # ── Session state init ─────────────────────────────────────────────────
    if "gs_running"      not in st.session_state:
        st.session_state.gs_running      = False   # is thread active?
    if "gs_cancel_flag"  not in st.session_state:
        st.session_state.gs_cancel_flag  = None
    if "gs_thread"       not in st.session_state:
        st.session_state.gs_thread       = None
    if "gs_result"       not in st.session_state:
        st.session_state.gs_result       = {}
    if "gs_done"         not in st.session_state:
        st.session_state.gs_done         = False   # completed (success/cancel)

    # ── Source file presence check ─────────────────────────────────────────
    source_exists = os.path.exists(SOURCE_FILE)
    output_exists = os.path.exists(OUTPUT_FILE)

    # Status bar
    c1, c2 = st.columns(2)
    with c1:
        if source_exists:
            st.success(f"✅ Source ready: `{SOURCE_FILE}`")
        else:
            st.error("❌ Please upload a source file above.")
    with c2:
        if output_exists:
            st.info(f"📂 Output exists: `{OUTPUT_FILE}` — will **append**")
        else:
            st.info(f"🆕 Output not found — will **create** `{OUTPUT_FILE}`")

    st.divider()

    # ── Source preview ─────────────────────────────────────────────────────
    if source_exists:
        try:
            raw = pd.read_excel(SOURCE_FILE, header=0, dtype=str)
            raw.columns = [str(c).strip() for c in raw.columns]
        except Exception as e:
            st.error(f"❌ Cannot read `{SOURCE_FILE}`: {e}")
            return

        total_rows  = len(raw)
        nc_filled   = (
            raw["nombre colis"]
            .apply(lambda x: not pd.isna(x) and str(x).strip() != "")
            .sum()
            if "nombre colis" in raw.columns else 0
        )
        chassis_ok  = (
            raw.apply(gs_has_valid_chassis, axis=1).sum()
            if "Némuro de chassis" in raw.columns else 0
        )
        bl_count    = raw["BL"].nunique() if "BL" in raw.columns else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Rows",                 total_rows)
        m2.metric("→ NAVIRES / RST rows",       nc_filled)
        m3.metric("→ N° chassis rows",          chassis_ok)
        m4.metric("Unique BL",                  bl_count)

        required = ["BL","navire_name","nombre colis","Poids brute","PRODUITS","escale_numb"]
        missing  = [c for c in required if c not in raw.columns]
        if missing:
            st.warning(f"⚠️ Missing columns: `{'`, `'.join(missing)}`")

        with st.expander("🔍 Preview source (first 10 rows)"):
            st.dataframe(raw.head(10), use_container_width=True)

    st.divider()

    # ── Poll running thread ────────────────────────────────────────────────
    if st.session_state.gs_running:
        thread: threading.Thread = st.session_state.gs_thread
        if thread and not thread.is_alive():
            # Thread finished — collect result
            st.session_state.gs_running = False
            st.session_state.gs_done    = True
            # result already stored in st.session_state.gs_result by thread

    # ── Control buttons ────────────────────────────────────────────────────
    st.subheader("⚙️ Controls")
    btn_col1, btn_col2 = st.columns([1, 1])

    # START button
    with btn_col1:
        start_disabled = (
            not source_exists                # no source file
            or st.session_state.gs_running   # already running
        )
        if st.button(
            "▶ Start Processing",
            type="primary",
            disabled=start_disabled,
            use_container_width=True,
        ):
            # Reset state
            st.session_state.gs_done        = False
            st.session_state.gs_result      = {}
            cancel_flag                     = threading.Event()
            result_dict: dict               = {}
            st.session_state.gs_cancel_flag = cancel_flag
            st.session_state.gs_result      = result_dict

            t = threading.Thread(
                target=gs_run_generation,
                args=(raw, cancel_flag, result_dict),
                daemon=True,
            )
            st.session_state.gs_thread  = t
            st.session_state.gs_running = True
            t.start()
            st.rerun()

    # STOP / CANCEL button
    with btn_col2:
        stop_disabled = not st.session_state.gs_running
        if st.button(
            "⏹ Stop / Cancel",
            type="secondary",
            disabled=stop_disabled,
            use_container_width=True,
        ):
            if st.session_state.gs_cancel_flag:
                st.session_state.gs_cancel_flag.set()   # signal thread to stop
            st.warning("⚠️ Cancellation requested — stopping after current row …")

    st.divider()

    # ── Live status while running ──────────────────────────────────────────
    if st.session_state.gs_running:
        with st.spinner("⏳ Processing … click **Stop / Cancel** to abort."):
            # auto-refresh every second while thread is alive
            import time
            time.sleep(1)
            st.rerun()

    # ── Result display ─────────────────────────────────────────────────────
    if st.session_state.gs_done:
        result = st.session_state.gs_result

        if result.get("cancelled"):
            st.warning("🚫 Processing was cancelled. Output file was **not** saved.")

        elif result.get("error"):
            st.error(f"❌ Error during processing:\n\n`{result['error']}`")

        elif result.get("stats"):
            st.success("✅ Processing complete!")

            # Summary table
            st.subheader("📊 Sheet Summary")
            rows_data = []
            for sheet, s in result["stats"].items():
                rows_data.append({
                    "Sheet":         sheet,
                    "Mode":          "Appended ➕" if s["appended"] else "Created 🆕",
                    "Rows Written":  s["kept"],
                    "Rows Skipped":  s["skipped"],
                })
            st.dataframe(
                pd.DataFrame(rows_data),
                use_container_width=True,
                hide_index=True,
            )

            # Download button
            st.divider()
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, "rb") as f:
                    file_bytes = f.read()

                st.download_button(
                    label=f"⬇️ Download  {OUTPUT_FILE}",
                    data=file_bytes,
                    file_name=OUTPUT_FILE,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    type="primary",
                )
            else:
                st.error("Output file not found on disk after processing.")

    # ── How-it-works info ─────────────────────────────────────────────────
    if not st.session_state.gs_running and not st.session_state.gs_done:
        with st.expander("ℹ️ How it works"):
            st.markdown(f"""
            | Sheet | Filter Rule |
            |-------|-------------|
            | **NAVIRES** | Rows where `nombre colis` is filled |
            | **N° chassis** | Rows where `Némuro de chassis` is a valid VIN/chassis (8–17 alphanumeric chars) |
            | **RST** (`{RST_SHEET_NAME}`) | Rows where `nombre colis` is filled |

            - Source file read from disk: **`{SOURCE_FILE}`**
            - Output written to disk: **`{OUTPUT_FILE}`**
            - If **`{OUTPUT_FILE}`** already exists, rows are **appended** to each sheet.
            - Numbers (`nombre colis`, `Poids brute`, `SURF`) are written as real numeric values.
            """)
# ---------------------------------------------------------------------------
# Hook into your existing app router
# ---------------------------------------------------------------------------
# In your main app file:
#
#   elif menu == "Generate_Sheets":
#       page_generate_sheets()