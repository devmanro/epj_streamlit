from pandas.core.interchange import dataframe
import streamlit as st
import re
import os
import unicodedata
import warnings
import pandas as pd
from pyarrow import null
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from pathlib import Path
from openpyxl.formatting.rule import FormulaRule

from openpyxl.styles import  PatternFill
from openpyxl.utils import get_column_letter

from assets.constants.constants import (
    COL_CLIENT,
    COL_QUANTITE,
    COL_TONAGE,
    COL_BL,
    COL_CHASSIS_SERIAL,
    DB_PATH, 
    COLUMNS,
    # add COL_VALUES here if you have such a column name
    COL_TYPE,
    COL_PRODUIT,
    COMMODITY_TYPES,
    GOODS__TYPES, 
    UNITS_TYPES,
    PACKAGES_TYPES,
    KEYWORD_RULES,
    UNIT_CARGO_TYPES,
    PACKAGE_CARGO_TYPES,
    COL_DESIGNATION,
    numeric_cols,
    date_cols,
    category_cols,
    text_cols,
    LIST_OF_PATHS
)


import httpx
import asyncio

BASE = "https://devmanro-my-fastapi-app.hf.space"

# ══════════════════════════════════════════════════════════════════════════════
# Wake + Poll server
# ══════════════════════════════════════════════════════════════════════════════
async def wait_for_server(set_msg=print):
    set_msg("Waking up prediction server…")

    # Fire initial wake ping
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{BASE}/health", timeout=3.0)
    except Exception:
        pass

    MAX_ATTEMPTS = 10
    for attempt in range(MAX_ATTEMPTS):
        await asyncio.sleep(3)
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"{BASE}/health", timeout=5.0)
                if res.status_code == 200:
                    json_data = res.json()
                    if json_data.get("status") == "ok":
                        print(f"✅ Server ready after ~{(attempt + 1) * 3}s")
                        set_msg("Server is ready — running predictions…")
                        return True
        except Exception:
            pass

        waited = (attempt + 1) * 3
        set_msg(f"Server is starting… ({waited}s elapsed, please wait)")
        print(f"⏳ Waiting for server... attempt {attempt + 1}/{MAX_ATTEMPTS}")

    raise Exception("Server did not respond after 30 seconds. Please try again.")



# ══════════════════════════════════════════════════════════════════════════════
# Bulk prediction
# ══════════════════════════════════════════════════════════════════════════════
async def predict_rows(rows, set_msg=print):
    """
    rows: list of dicts with 'marchandise' key
    returns: list of predictions
    """
    await wait_for_server(set_msg)

    set_msg("Sending data to prediction API…")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{BASE}/predict",
                json={"rows": [{"marchandise": r["marchandise"]} for r in rows]},
            )

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")

            json_data = response.json()
            print("RAW PREDICTION RESPONSE:", json_data)
            return json_data.get("predictions", [])

    except httpx.TimeoutException:
        raise Exception("Prediction request timed out after 1 minute.")





# ══════════════════════════════════════════════════════════════════════════════
# Updated align_data using predictions instead of find_type_and_produit
# ══════════════════════════════════════════════════════════════════════════════
def align_data(uploaded_df, mapping):
    try:
        valid_mappings_count = sum(
            1 for value in mapping.values() if value is not None
        )

        if valid_mappings_count <= 2:
            return uploaded_df, False

        # Rename columns based on the mapping
        df_mapped = uploaded_df.rename(columns=mapping)

        final_cols = [value for key, value in mapping.items() if value is not None]

        # Keep only the required columns
        df_aligned = df_mapped[final_cols].copy()

        if COL_DESIGNATION in df_aligned.columns:

            # --- 1. BYPASS: Save existing values before overwriting ---
            orig_type    = df_aligned[COL_TYPE].copy()    if COL_TYPE    in df_aligned.columns else None
            orig_produit = df_aligned[COL_PRODUIT].copy() if COL_PRODUIT in df_aligned.columns else None

            # --- 2. BUILD rows for prediction API ---
            rows = [
                {"marchandise": val if isinstance(val, str) else ""}
                for val in df_aligned[COL_DESIGNATION]
            ]

            # --- 3. CALL prediction API ---
            predictions = asyncio.run(predict_rows(rows))

            # --- 4. APPLY predictions ---
            # predictions is expected to be a list of dicts:
            # [{"cargo_type": "COIL", "produit": "UNIT"}, ...]
            df_aligned[COL_TYPE]    = [p.get("Produits", None) for p in predictions]
            df_aligned[COL_PRODUIT] = [p.get("Details", None)    for p in predictions]

            # --- 5. REINSERT: Put back original values where they were not null ---
            if orig_type is not None:
                mask = orig_type.notna() & (orig_type != '')
                df_aligned.loc[mask, COL_TYPE] = orig_type[mask]

            if orig_produit is not None:
                mask = orig_produit.notna() & (orig_produit != '')
                df_aligned.loc[mask, COL_PRODUIT] = orig_produit[mask]

        else:
            for col in [COL_TYPE, COL_PRODUIT]:
                if col not in df_aligned.columns:
                    df_aligned[col] = 'None'
                else:
                    df_aligned[col] = df_aligned[col].fillna('None')

        return df_aligned, True

    except Exception as e:
        print(f"Error during alignment: {e}")
        return uploaded_df, False


# ══════════════════════════════════════════════════════════════════════════════
# Manifest pre-alignment — runs on the RAW file BEFORE align_data()
# ══════════════════════════════════════════════════════════════════════════════

# Label written into the (mapped) product/type columns of generated rows.
GENERATED_PACKAGE_LABEL = "COLIS"

# Cells that mean "no value" in raw manifest files.
_BLANK_MANIFEST_STRINGS = frozenset({
    "", "-", "--", "—", "–", "n/a", "na", "nan", "none", "null",
})

# Max warnings kept per category in the report (the rest are counted).
_PREALIGN_WARN_CAP = 8


def _is_blank_manifest_cell(value) -> bool:
    """True for empty cells and placeholder strings ('-', 'N/A', ...)."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return False
    return str(value).strip().lower() in _BLANK_MANIFEST_STRINGS


def _parse_manifest_number(value):
    """
    Parse a raw quantity/weight cell.

    Returns (number, explicit): explicit is False when the cell is blank or
    unparseable (number is then 0.0). Accepts ints, floats, French decimals
    ('17,650'), thousand separators ('1,234.56') and stray spaces.
    """
    if _is_blank_manifest_cell(value):
        return 0.0, False
    if isinstance(value, bool):
        return 0.0, False
    if isinstance(value, (int, float)):
        return float(value), True
    text = str(value).strip().replace(" ", "").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text and "." in text:
        text = text.replace(",", "")
    try:
        return float(text), True
    except ValueError:
        return 0.0, False


def _clean_manifest_number(value, decimals=3):
    """Return an int when whole, else a rounded float (for cell rewrites)."""
    number = float(value)
    if number.is_integer():
        return int(number)
    return round(number, decimals)


def expand_manifest_packages(df, mapping):
    """
    Pre-alignment normalizer for RAW manifest files. Call it right after
    loading the xlsx/json and BEFORE ``align_data(df_raw, final_mp)``::

        df_raw, pre_report = expand_manifest_packages(df_raw, final_mp)
        molded_df, success = align_data(df_raw, final_mp)

    Raw manifests group rows in *blocks*: a header row carries the CLIENT
    name (and usually the global 'nombre colis' / 'Poids brute'), followed
    by continuation sub-rows with an empty CLIENT — one physical entity per
    row (single chassis / single weight, sometimes a single quantity).
    Forward-filled files (CLIENT repeated on every row of the same B/L)
    are supported too.

    Per block this function:
      1. drops fully-empty rows (filtering);
      2. forward-fills CLIENT and B/L onto continuation rows — a blank
         CLIENT would otherwise make the row silently dropped by the
         CLIENT grouping in group_sourcefile_by_client (pandas drops NaN
         group keys), losing its quantity;
      3. aligns 'nombre colis' / 'Poids brute' so the block sums to the
         global header values (chassis sub-rows without quantity get 1,
         the header keeps only its own unit / own single weight);
      4. appends a synthetic COLIS row with
         (global nombre colis − number of chassis) when the global quantity
         exceeds the chassis count, with product/type = COLIS;
      5. validates that quantity-carrying rows without chassis have a
         product/type classification (CLIENT may legitimately be blank on
         sub-rows, product/type may not).

    ``mapping`` is the same {source_column: canonical_column} dict passed to
    align_data — it locates the raw CLIENT / QUANTITE / TONAGE / CHASSIS /
    B/L / TYPE / PRODUIT columns. Blocks are left untouched when CLIENT or
    QUANTITE is not mapped.

    Returns (fixed_df, report). The input DataFrame is never mutated.
    report = {
        "ok", "note", "blocks", "rows_added", "rows_dropped_empty",
        "client_cells_filled", "bl_cells_filled", "qty_cells_rewritten",
        "weight_cells_rewritten", "added_rows": [{client, bl, qty}],
        "warnings": [str, ...],
    }
    """
    report = {
        "ok": True,
        "note": "",
        "blocks": 0,
        "rows_added": 0,
        "rows_dropped_empty": 0,
        "client_cells_filled": 0,
        "bl_cells_filled": 0,
        "qty_cells_rewritten": 0,
        "weight_cells_rewritten": 0,
        "added_rows": [],
        "warnings": [],
    }

    if df is None or getattr(df, "empty", True):
        report.update(ok=False, note="empty input — nothing to do")
        return df, report
    if not mapping:
        report.update(ok=False, note="no column mapping — cannot locate CLIENT/QUANTITE columns")
        return df.copy(), report

    # mapping is {source_column: canonical_column} → reverse it.
    reverse = {}
    for src, canon in mapping.items():
        if canon and canon not in reverse:
            reverse[canon] = src

    def _resolve(canon):
        src = reverse.get(canon)
        return src if src in df.columns else None

    src_client = _resolve(COL_CLIENT)
    src_qty = _resolve(COL_QUANTITE)
    if src_client is None or src_qty is None:
        report.update(
            ok=False,
            note="CLIENT and/or QUANTITE not mapped — manifest left untouched",
        )
        return df.copy(), report

    src_weight = _resolve(COL_TONAGE)
    src_chassis = _resolve(COL_CHASSIS_SERIAL)
    src_bl = _resolve(COL_BL)
    src_type = _resolve(COL_TYPE)
    src_produit = _resolve(COL_PRODUIT)

    work = df.copy().reset_index(drop=True)

    # ── 1. Filtering: drop fully-empty rows ──────────────────────────────
    def _row_is_empty(row):
        for value in row:
            if not _is_blank_manifest_cell(value):
                return False
        return True

    empty_mask = work.apply(_row_is_empty, axis=1)
    report["rows_dropped_empty"] = int(empty_mask.sum())
    work = work.loc[~empty_mask].reset_index(drop=True)
    if work.empty:
        report["note"] = "all rows empty"
        return work, report

    # ── Cell helpers ─────────────────────────────────────────────────────
    def _warn(message, _counter=[0]):
        # Cap stored warnings; count the overflow in a trailing summary.
        if _counter[0] < _PREALIGN_WARN_CAP:
            report["warnings"].append(message)
        _counter[0] += 1

    def _cell_blank(col, i):
        if col is None:
            return True
        return _is_blank_manifest_cell(work.at[i, col])

    def _cell_text(col, i):
        if col is None:
            return ""
        value = work.at[i, col]
        return "" if _is_blank_manifest_cell(value) else str(value).strip()

    def _cell_num(col, i, warn_label=None):
        if col is None:
            return 0.0, False
        value = work.at[i, col]
        number, explicit = _parse_manifest_number(value)
        if warn_label and not explicit and not _is_blank_manifest_cell(value):
            _warn(f"Row {i + 1}: {warn_label} value '{value}' is not a number — treated as 0")
        return number, explicit

    def _has_chassis(i):
        return src_chassis is not None and not _is_blank_chassis(work.at[i, src_chassis])

    def _rewrite_qty(i, value):
        current, explicit = _cell_num(src_qty, i)
        new_value = _clean_manifest_number(value)
        current_clean = _clean_manifest_number(current) if explicit else None
        if (not explicit) or (current_clean != new_value):
            work.at[i, src_qty] = new_value
            report["qty_cells_rewritten"] += 1

    def _rewrite_weight(i, value):
        current, explicit = _cell_num(src_weight, i)
        new_value = _clean_manifest_number(value)
        current_clean = _clean_manifest_number(current) if explicit else None
        if (not explicit) or (current_clean != new_value):
            work.at[i, src_weight] = new_value
            report["weight_cells_rewritten"] += 1

    # ── 2. Block scan ────────────────────────────────────────────────────
    # A new block starts on a filled CLIENT, unless it repeats the current
    # block's client *and* B/L (forward-filled layout → same shipment).
    # Blank-CLIENT rows continue the current block. Leading rows before the
    # first CLIENT header are orphans (kept as-is, warned about).
    blocks = []  # list of (header_idx, end_idx)
    cur_h, cur_client, cur_bl = None, "", ""
    orphans = 0
    for i in range(len(work)):
        client_text = _cell_text(src_client, i)
        if not client_text:
            if cur_h is None:
                orphans += 1
            continue
        bl_text = _cell_text(src_bl, i)
        same_block = (
            cur_h is not None
            and client_text == cur_client
            and (not bl_text or not cur_bl or bl_text == cur_bl)
        )
        if same_block:
            continue
        if cur_h is not None:
            blocks.append((cur_h, i - 1))
        cur_h, cur_client, cur_bl = i, client_text, bl_text
    if cur_h is not None:
        blocks.append((cur_h, len(work) - 1))
    if orphans:
        _warn(
            f"{orphans} leading row(s) before the first CLIENT header were left "
            "untouched (no client to attach them to)"
        )

    if src_type is None and src_produit is None:
        _warn(
            "TYPE and PRODUIT columns are not mapped — generated COLIS rows "
            "and untyped quantities may not survive grouping; map them if possible"
        )

    generated = {}  # header_idx -> generated row dict

    # ── 3-5. Per-block alignment / expansion / validation ────────────────
    for (h, e) in blocks:
        report["blocks"] += 1
        header_client = _cell_text(src_client, h)
        header_bl = _cell_text(src_bl, h)
        idx = list(range(h, e + 1))
        sub_idx = idx[1:]

        # Normalize number-like strings in place ("36 000" → 36000,
        # "17,5" → 17.5) so downstream to_numeric() never zeroes them.
        for _col, _kind in ((src_qty, "qty"), (src_weight, "weight")):
            if _col is None:
                continue
            for i in idx:
                raw = work.at[i, _col]
                if isinstance(raw, str) and not _is_blank_manifest_cell(raw):
                    number, explicit = _parse_manifest_number(raw)
                    if explicit:
                        cleaned = _clean_manifest_number(number)
                        if raw.strip() != str(cleaned):
                            work.at[i, _col] = cleaned
                            report[f"{_kind}_cells_rewritten"] += 1

        gq, gq_exp = _cell_num(src_qty, h, warn_label=f"'{src_qty}' (client {header_client})")
        gw, gw_exp = (
            _cell_num(src_weight, h, warn_label=f"'{src_weight}' (client {header_client})")
            if src_weight else (0.0, False)
        )

        sub_qty = [_cell_num(src_qty, i) for i in sub_idx]
        has_sub_qty = any(exp for _, exp in sub_qty)
        sq = sum(v for v, _ in sub_qty)

        if src_weight:
            sub_w = [_cell_num(src_weight, i) for i in sub_idx]
            has_sub_w = any(exp for _, exp in sub_w)
            sw = sum(v for v, _ in sub_w)
        else:
            has_sub_w, sw = False, 0.0

        has_ch = [_has_chassis(i) for i in idx]
        chassis_count = sum(has_ch)
        header_units = 1 if has_ch[0] else 0

        # Is the header quantity the GLOBAL block total, or the header row's
        # own quantity? Global when it is the only quantity around, or when
        # sub-row quantities + header units add up to it exactly.
        if not has_sub_qty:
            header_is_global = bool(gq_exp and gq > 0)
        else:
            header_is_global = bool(
                gq_exp and gq > 0 and abs((sq + header_units) - gq) < 1e-6
            )

        if header_is_global:
            # Quantity already itemized on package-like sub-rows (kept as-is).
            pkg_sub_qty = sum(
                v for i, (v, exp) in zip(sub_idx, sub_qty)
                if exp and not _has_chassis(i)
            )
            itemized = (chassis_count > 0) or (pkg_sub_qty > 0)
            if itemized:
                # Header quantity is the block TOTAL → strip it down to the
                # header row's own units so nothing is counted twice.
                _rewrite_qty(h, float(header_units))
                # Chassis sub-rows without quantity are single entities → 1.
                # Explicit sub-row quantities are never overwritten.
                for i in sub_idx:
                    if _has_chassis(i):
                        _, exp = _cell_num(src_qty, i)
                        if not exp:
                            _rewrite_qty(i, 1.0)
                # ── Expansion: missing packages become an explicit row ──
                additional = gq - chassis_count - pkg_sub_qty
                if additional > 1e-6:
                    row = {c: None for c in work.columns}
                    row[src_client] = header_client
                    if src_bl and header_bl:
                        row[src_bl] = header_bl
                    row[src_qty] = _clean_manifest_number(additional)
                    if src_weight:
                        row[src_weight] = 0
                    if src_type:
                        row[src_type] = GENERATED_PACKAGE_LABEL
                    if src_produit:
                        row[src_produit] = GENERATED_PACKAGE_LABEL
                    generated[h] = row
                    report["rows_added"] += 1
                    report["added_rows"].append({
                        "client": header_client,
                        "bl": header_bl,
                        "qty": _clean_manifest_number(additional),
                    })
                # Header keeps only its own single weight.
                if src_weight and has_sub_w and gw_exp and gw > 0 and sw <= gw + 1e-6:
                    _rewrite_weight(h, max(0.0, gw - sw))
            # else: pure bulk block (no chassis, nothing itemized) — the
            # header quantity IS the record; keep it untouched.
        elif has_sub_qty:
            # Distributed layout (e.g. unit row + COLIS row): everything is
            # already itemized — reconcile only, never rewrite/add.
            existing_pkg = 0.0
            if not has_ch[0] and gq_exp:
                existing_pkg += gq
            for i, (v, exp) in zip(sub_idx, sub_qty):
                if exp and not _has_chassis(i):
                    existing_pkg += v
            total = (gq if gq_exp else 0.0) + sq
            gap = total - chassis_count - existing_pkg
            if abs(gap) > 1e-6:
                _warn(
                    f"Client '{header_client}' (B/L {header_bl or '—'}): quantities don't "
                    f"reconcile (total {total:g}, chassis {chassis_count}, unpackaged "
                    f"{existing_pkg:g}) — left untouched, please review"
                )
        # else: no quantities anywhere in the block — nothing to align.

        # ── CLIENT / B-L forward-fill onto continuation rows ─────────────
        for i in sub_idx:
            if _cell_blank(src_client, i):
                work.at[i, src_client] = header_client
                report["client_cells_filled"] += 1
            if src_bl and header_bl and _cell_blank(src_bl, i):
                work.at[i, src_bl] = header_bl
                report["bl_cells_filled"] += 1

        # ── Validation: product/type must exist on qty-carrying rows ─────
        # (CLIENT may legitimately repeat or be blank on sub-rows; a
        # quantity without chassis and without product/type cannot be
        # classified downstream.)
        if src_type is not None or src_produit is not None:
            for i in idx:
                if _has_chassis(i):
                    continue
                v, exp = _cell_num(src_qty, i)
                if not exp or v <= 0:
                    continue
                if _cell_blank(src_type, i) and _cell_blank(src_produit, i):
                    _warn(
                        f"Row {i + 1} (client '{header_client}', qty {v:g}) has no "
                        "product/type — it may not survive grouping"
                    )

    # ── Rebuild: emit blocks in order, generated rows at the end of theirs ─
    pieces = []
    pos = 0
    for (h, e) in blocks:
        if pos < h:
            pieces.append(work.iloc[pos:h])  # orphans / gaps, untouched
        pieces.append(work.iloc[h:e + 1])
        if h in generated:
            pieces.append(pd.DataFrame([generated[h]], columns=work.columns))
        pos = e + 1
    if pos < len(work):
        pieces.append(work.iloc[pos:])
    if pieces:
        with warnings.catch_warnings():
            # Generated rows are sparse (None outside the mapped columns);
            # the all-NA concat behaviour change in pandas 3 is irrelevant here.
            warnings.simplefilter("ignore", FutureWarning)
            out = pd.concat(pieces, ignore_index=True)
    else:
        out = work

    report["note"] = (
        f"{report['blocks']} client block(s), "
        f"{report['rows_added']} COLIS row(s) generated, "
        f"{report['client_cells_filled']} continuation row(s) attached to their client"
    )
    return out, report

def get_manual_color(product_name):
    """Maps product names to specific hex colors as requested."""
    name = str(product_name).upper()
    
    # Group products by color
    color_groups = {
        "92D050": ["CTP", "PLYWOOD", "MDF", "FFP", "MDF + PLYWOOD"],                      # Greenish
        "538DD5": ["BIG BAG", "BAG", "PIPE", "CORNIERE", "CORNIERS"],                      # Blue
        "C65911": ["TUBE", "FORMWORK", "POUTRELLE"],                                       # Brown/Orange
        "948A54": ["BOB", "BOBINE", "COIL", "METAL SHEET", "STEEL BEAMS"],                 # Tan/Gold
        "DDD9C4": ["BEAMS", "FIL", "FIL M"],                                              # Grey/Beige
        "FFDC6B": ["COLI", "COLIS", "UNIT", "BUS", "MINI BUS", "CAMIONS", "CAMION POMPE A BETON", "REMORQUES", "EXCAVATEUR", "BULLDOZER", "CHARGEUR", "COMPACTEUR", "FINISSEUR", "CAMION GRUE", "CHARIOT ELEVATEUR", "NIVELEUSE"], # GOLD
    }

    
    # Find which group the product belongs to
    for color, products in color_groups.items():
        if name in products:
            return color
    
    # Returns None (White) if not found or for 'Others'
    return None


def apply_summary_conditional_formatting(ws, summary_rows, start_col, clients):
    red_fill = PatternFill(start_color="FFFF0000", end_color="FFFF0000", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid")

    total_row = summary_rows[0]      # total decharger
    manifest_row = summary_rows[1]   # total quantite manifest
    reste_row = summary_rows[2]      # reste

    first_client_col = get_column_letter(start_col + 2)
    last_client_col = get_column_letter(start_col + 1 + len(clients))

    total_range = f"{first_client_col}{total_row}:{last_client_col}{total_row}"
    manifest_range = f"{first_client_col}{manifest_row}:{last_client_col}{manifest_row}"
    reste_range = f"{first_client_col}{reste_row}:{last_client_col}{reste_row}"

    # total decharger row
    ws.conditional_formatting.add(
        total_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}>{first_client_col}{manifest_row}"],
            fill=red_fill,
            stopIfTrue=True
        )
    )
    ws.conditional_formatting.add(
        total_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}={first_client_col}{manifest_row}"],
            fill=yellow_fill
        )
    )

    # total quantite manifest row
    ws.conditional_formatting.add(
        manifest_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}>{first_client_col}{manifest_row}"],
            fill=red_fill,
            stopIfTrue=True
        )
    )
    ws.conditional_formatting.add(
        manifest_range,
        FormulaRule(
            formula=[f"={first_client_col}{total_row}={first_client_col}{manifest_row}"],
            fill=yellow_fill
        )
    )

    # reste row
    ws.conditional_formatting.add(
        reste_range,
        FormulaRule(
            formula=[f"={first_client_col}{reste_row}<0"],
            fill=red_fill,
            stopIfTrue=True
        )
    )
    ws.conditional_formatting.add(
        reste_range,
        FormulaRule(
            formula=[f"={first_client_col}{reste_row}=0"],
            fill=yellow_fill
        )
    )


# @st.cache_resource
def ensure_directories():
    """Creates folders if they don't exist. Cached to run only once."""
    for p in LIST_OF_PATHS:
        Path(p).mkdir(parents=True, exist_ok=True)

 # Helper function to get display name without extension
# ============================================================
def get_display_name(filename: str) -> str:
    """Remove file extension for display"""
    from pathlib import Path
    return Path(filename).stem

def clean_dataframe_types(datasource , only_cols=None):
    """
    Loops through columns and applies appropriate types and handles None/NaN.
    """
    # 1. Define Column Groups
    # numeric_cols = ["QUANTITE", "TONAGE", "RESTE T/P", "SURFACE"]
    # text_cols = ["NAVIRE", "B/L", "DESIGNATION", "CLIENT","DATE" ]
    # category_cols = ["TYPE", "SITUATION", "CLES"]

    cols_to_process = only_cols if only_cols is not None else datasource.columns
    for col in cols_to_process:
        if col not in datasource.columns:
            continue
        # --- Handle Text Columns (The "FLOAT" Error Fix) ---
        if col in text_cols:
            # Force to string first, then clean up the 'nan' strings
            datasource[col] = datasource[col].astype(str).replace(['nan', 'None', 'NaN', 'null'], '')
            datasource[col] = datasource[col].str.replace(r'\.0$', '', regex=True) # Removes .0 from IDs
            
        # --- Handle Numeric Columns ---
        elif col in numeric_cols:
            datasource[col] = pd.to_numeric(datasource[col], errors='coerce').fillna(0.0)
            if col == "QUANTITE":
                datasource[col] = datasource[col].astype(int)

        # --- Handle Date Columns ---
        elif col in date_cols:
            # Convert to datetime; errors='coerce' turns bad dates into NaT (Accepted by DateColumn)
            datasource[col] = pd.to_datetime(datasource[col], errors='coerce')

        # --- Handle Category Columns ---
        elif col in category_cols:
            default_val = "En attente" if col == "SITUATION" else "N/A" 
            datasource[col] = datasource[col].astype(str).replace(['nan', 'None', 'NaN'], default_val)

    return datasource


def getDB():
    # 1. Check if the database file exists
    dir_name = os.path.dirname(DB_PATH)
    if not os.path.exists(dir_name):
        st.info(f"Database file creation at: {DB_PATH}")
        os.makedirs(dir_name)

    # 2. Create empty Excel file if it doesn't exist
    if not os.path.exists(DB_PATH):
        # Create a basic dataframe with columns
        df_new = pd.DataFrame(columns=COLUMNS)
        df_new.to_excel(DB_PATH, index=False)
        st.info(f"Created new database at: {DB_PATH}")

    # 2. Load the Master Data
    try:
        # We read from the single constant path now
        df = pd.read_excel(DB_PATH)
        return df
    except Exception as e:
        st.error(f"Error reading database: {e}")
        return null


def create_mapping_ui(uploaded_df, required_columns=COLUMNS):
    st.write("### Map Imported Columns to Database Columns")
    mapping = {}

    # Create a dropdown for every required column
    for req_col in required_columns:
        mapping[req_col] = st.selectbox(
            f"Select the source for: **{req_col}**",
            options=[None] + list(uploaded_df.columns),
            key=f"map_{req_col}"
        )
    return mapping


def find_type_and_produit(designation):
    """
    Return (CARGO_TYPE, PRODUIT_CATEGORY) by matching keywords against the designation.
    Rules are checked in order — first match wins for cargo_type.
    PRODUIT scans the full designation against UNIT and PACKAGE sets.
    """
    if not isinstance(designation, str):
        return pd.Series([None, None])

    designation_upper = designation.upper()

    # Step 1: Find cargo_type from KEYWORD_RULES (first match wins)
    cargo_type = None
    for keywords, ctype in KEYWORD_RULES:
        for keyword in keywords:
            if keyword.upper() in designation_upper:
                cargo_type = ctype
                break
        if cargo_type is not None:
            break

    # Step 2: Check designation directly against BOTH category sets
    is_unit = any(
        constant.upper() in designation_upper
        for constant in UNIT_CARGO_TYPES
    )
    is_package = any(
        constant.upper() in designation_upper
        for constant in PACKAGE_CARGO_TYPES
    )

    # Step 3: Also check cargo_type itself against category sets
    if cargo_type is not None:
        if not is_unit:
            unit_matched, _ = matches_any_constant(cargo_type, UNIT_CARGO_TYPES)
            is_unit = unit_matched
        if not is_package:
            pkg_matched, _ = matches_any_constant(cargo_type, PACKAGE_CARGO_TYPES)
            is_package = pkg_matched

    # Step 4: Determine PRODUIT
    if is_package and is_unit:
        produit = "UNIT + PACKAGE"
    elif is_package:
        produit = "PACKAGE"
    elif is_unit:
        produit = "UNIT"
    else:
        produit = cargo_type  # Unknown → flag for manual review

    return pd.Series([cargo_type, produit])



@st.dialog("Map Your Columns", width="large")
def show_mapping_dialog(uploaded_df):
    st.write("Match your file columns to the database headings:")
    # st.info(list(uploaded_df.columns))
    st.session_state.trigger_mapping = False
    mapping = {}
    uploaded_cols = list(uploaded_df.columns)
    COLS_PER_ROW = 4

    for i in range(0, len(COLUMNS), COLS_PER_ROW):
        row_cols = st.columns(COLS_PER_ROW)
        batch = COLUMNS[i: i + COLS_PER_ROW]

        for j, req_col in enumerate(batch):
            with row_cols[j]:
                with st.container(border=True):
                    st.markdown(f"**{req_col}**")

                    # --- AUTO-MATCH LOGIC ---
                    # Find first uploaded col that contains the required name (e.g., 'date' in 'date_manifeste')
                    default_index = 0  # Default to None
                    for idx, col in enumerate(uploaded_cols):
                        if req_col.lower() in col.lower():
                            default_index = idx + 1 # +1 because [None] is at index 0
                            break
                    # ------------------------

                    selected_source_column = st.selectbox(
                        f"Source for {req_col}:",
                        options=[None] + uploaded_cols,
                        index=default_index,
                        key=f"map_{req_col}",
                        label_visibility="collapsed"
                    )
                    
                    if selected_source_column:
                        mapping[selected_source_column] = req_col
        
        st.session_state.final_mapping = mapping

    if st.button("Confirm and Import", type="primary", width='stretch'):
        # 1. Clear the trigger immediately so it doesn't re-open
        st.session_state.final_mapping = mapping
        # st.session_state.mapping_shown = True
        st.session_state.uploaded_file = None
        # Print to the terminal window

        # 2. Force a rerun to close the dialog and update the main app
        st.rerun()


# ---------------------------------------------------------------------------
# Commodity / received-lines helpers.
# ---------------------------------------------------------------------------

def _normalize_commodity_text(value):
    """Normalize a commodity cell value for deterministic matching."""
    if value is None:
        return ""
    # Strip accents / diacritics (e.g. unité -> unite)
    text = str(value)
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


def _normalize_match_text(value):
    """
    Normalize text for delimiter-insensitive matching. Underscores and hyphens
    are treated as spaces so e.g. 'DUMP_TRUCK' matches 'DUMP TRUCK'.
    """
    if value is None:
        return ""
    text = _normalize_commodity_text(value)
    text = re.sub(r"[-_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Placeholders that appear in CHASSIS/SERIAL but are not real serials.
_CHASSIS_PLACEHOLDERS = {"", "-", "--", "—", "–", "N/A", "NA", "NONE", "NULL", "NAN", ".", "/"}

# Structural / break-bulk families — never bucketed as UNITS/PACKAGES.
_STRUCTURAL_TYPE_LABELS = {
    "CTP", "BOBINE", "PIPE", "POUTRELLE", "CORNIERE",
    "MDF", "PLYWOOD", "FFP", "MDF + PLYWOOD",
    "BEAMS", "STEEL BEAMS", "METAL SHEET",
    "FORMWORK", "FIL M", "BRIDGE COMP", "BIG BAG",
    "COIL", "TUBE", "WHITE WOOD", "BEECH WOOD", "RED WOOD",
}

# French / English equipment names commonly found in source files (singular+plural stems).
_UNIT_EQUIPMENT_STEMS = {
    "CAMION", "BULLDOZER", "EXCAVATEUR", "EXCAVATOR", "CHARGEUR", "LOADER",
    "REMORQUE", "TRAILER", "FINISSEUR", "COMPACTEUR", "NIVELEUSE", "GRADER",
    "GRUE", "CRANE", "CHARIOT", "FORKLIFT", "BUS", "MINIBUS", "TRACTEUR",
    "PELLE", "ROLLER", "MIXER", "BENNE", "ENGIN", "LOURD", "NIVEL",
}


def _is_blank_chassis(value) -> bool:
    """True when a chassis/serial cell is empty or a non-serial placeholder (e.g. '-')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    if pd.isna(value):
        return True
    text = str(value).strip().upper()
    return text in _CHASSIS_PLACEHOLDERS


def _count_real_chassis(series) -> int:
    """Count non-empty, non-placeholder chassis/serial values."""
    if series is None:
        return 0
    count = 0
    for val in series:
        if not _is_blank_chassis(val):
            count += 1
    return count


def _is_package_type(text):
    """
    Check if text denotes a package/colis in French or English, singular or plural.
    e.g. COLIS, COLI, PACKAGE, PACKAGES, PKG, PKGS, CAISSE, CAISSES, CARTON, CARTONS, BOX, BOXES.
    """
    matched, norm = matches_any_constant(text, PACKAGE_CARGO_TYPES)
    if not norm:
        return False
    if matched:
        return True
    words = norm.split()
    package_keywords = {
        "COLIS", "COLI", "PACKAGE", "PACKAGES", "PKG", "PKGS",
        "CAISSE", "CAISSES", "CARTON", "CARTONS", "BOX", "BOXES",
        "SPARE_PARTS", "SPARE PART", "SPARE PARTS",
    }
    for w in words:
        if w in package_keywords:
            return True
    return False


def _is_unit_type(text):
    """
    Check if text denotes a unit/unite in French or English, singular or plural,
    or matches unit machinery/vehicles.
    e.g. UNIT, UNITS, UNITE, UNITES, CAMIONS, EXCAVATEURS, BULLDOZERS, …
    """
    matched, norm = matches_any_constant(text, UNIT_CARGO_TYPES)
    if not norm:
        return False
    if matched:
        return True

    words = norm.split()
    unit_keywords = {"UNIT", "UNITS", "UNITE", "UNITES"}
    for w in words:
        if w in unit_keywords:
            return True

    # French/English equipment stems (EXCAVATEURS, CHARGEURS, REMORQUES, FINISSEUR, …)
    compact = norm.replace(" ", "")
    for stem in _UNIT_EQUIPMENT_STEMS:
        if compact.startswith(stem) or stem in words or stem in compact:
            return True

    # COMMODITY_TYPES equipment entries that are not structural goods
    for commodity in COMMODITY_TYPES:
        c_norm = _normalize_match_text(commodity)
        if not c_norm or c_norm in _STRUCTURAL_TYPE_LABELS:
            continue
        if c_norm in norm or norm in c_norm:
            return True

    return False


def _is_unit_or_package_bucket(type_value) -> bool:
    """True when a (possibly already-normalized) TYPE belongs to the unit/package family."""
    if type_value is None or (isinstance(type_value, float) and pd.isna(type_value)):
        return False
    text = _normalize_commodity_text(type_value)
    if not text:
        return False
    if text in {"UNITS", "PACKAGES", "UNITS + PACKAGES", "UNITS + PACKAGE"}:
        return True
    if text in _STRUCTURAL_TYPE_LABELS:
        return False
    return _is_unit_type(text) or _is_package_type(text)


def _decide_client_unit_package_label(has_unit: bool, has_pkg: bool, quantite: int, chassis_count: int) -> str:
    """
    Decide UNITS / PACKAGES / UNITS + PACKAGES for one client from their
    unit/package rows only (structural commodities are handled separately).

    Combined only when the client has both unit-type and package-type cargo.
    Chassis count alone does not invent packages (source files often list
    chassis on qty=0 rows and the quantity on a separate row).
    """
    if has_unit and has_pkg:
        return "UNITS + PACKAGES"
    if has_unit or chassis_count > 0:
        return "UNITS"
    if has_pkg:
        return "PACKAGES"
    return "UNITS"


def _is_unit_package_combined(value):
    """Return True when a value explicitly denotes a combined unit+package group."""
    text = _normalize_commodity_text(value)
    if not text:
        return False
    text = re.sub(r"\s*\+\s*", " + ", text)
    text = re.sub(r"\s+", " ", text).strip()
    has_unit = ("UNIT" in text or "UNITE" in text)
    has_pkg = ("PACKAGE" in text or "COLI" in text or "CAISSE" in text or "PKG" in text)
    return bool(has_unit and has_pkg)


def _matches_keyword(text, keyword):
    """Case-insensitive substring / regex-word match after normalizing both sides."""
    if not text:
        return False
    kw = _normalize_commodity_text(keyword)
    if not kw:
        return False
    # Exact or word boundary match
    pattern = r"\b" + re.escape(kw) + r"(S|ES)?\b"
    return bool(re.search(pattern, text)) or kw in text


def _classify_commodity(raw_commodity):
    """
    Return (family, source) where family is the normalized commodity type and
    source is 'family' (direct GOODS__TYPES/COMMODITY_TYPES match) or 'rule'
    (KEYWORD_RULES match). More specific labels are tried first.
    """
    text = _normalize_commodity_text(raw_commodity)
    if not text:
        return None, None

    # Direct known structural families.
    known_families = [
        "BIG BAG",
        "PLYWOOD",
        "PIPE",
        "TUBE",
        "BEAMS",
        "METAL SHEET",
        "STEEL BEAMS",
        "FORMWORK",
        "FIL M",
        "COIL",
        "BOBINE",
        "BOB",
        "POUTRELLE",
        "CORNIERE",
        "CTP",
        "MDF",
        "FFP",
        "MDF + PLYWOOD",
        "WHITE WOOD",
        "BEECH WOOD",
        "RED WOOD",
    ]
    # Sort by normalized length so compound entries are checked first
    known_families.sort(key=lambda family: len(_normalize_commodity_text(family)), reverse=True)

    for family in known_families:
        if _matches_keyword(text, family):
            return family.upper(), "family"

    # Canonical KEYWORD_RULES fallback.
    keyword_rules = [
        (keyword, cargo_type)
        for keywords, cargo_type in KEYWORD_RULES
        for keyword in keywords
    ]
    keyword_rules.sort(
        key=lambda item: len(_normalize_commodity_text(item[0])),
        reverse=True,
    )
    for keyword, cargo_type in keyword_rules:
        if _matches_keyword(text, keyword):
            return cargo_type, "rule"

    return None, None


def _big_bags_received_template(rec_str):
    commodity = "BIG BAGS"
    received_lines = [
        "BIG BAGS FOUND TORN ON BOARD",
        "BIG BAGS FOUND BROKEN ON BOARD",
        "EMPTY BAG ON BOARD",
    ]
    total_rec_str = f"{rec_str}  Big Bags"
    return commodity, received_lines, total_rec_str


def _crates_received_template(display_name, rec_str):
    commodity = display_name or "CRATES"
    received_lines = [
        f"Crates of {commodity} Found Dismembered on board",
        f"Crates of {commodity} wet on board (Packing and/or Contents)",
        f"Crates of {commodity} moldy on board (Packing and/or Contents)",
    ]
    total_rec_str = f"{rec_str}  Crates of {commodity}"
    return commodity, received_lines, total_rec_str


def _bundles_received_template(display_name, rec_str, bundle_label=None):
    label = bundle_label or display_name
    commodity = f"Bundles of {label}"
    received_lines = [
        f"{commodity}.",
        f"{commodity} Found Dismembered on board",
    ]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _lumber_received_template(display_name, rec_str):
    """Wood/lumber (white/beech/red wood) uses the bundle + wet/mouldy wording."""
    commodity = "BUNDLES"
    received_lines = [
        f"Bundles of {display_name} Found Dismembered on board",
        f"Bundles of {display_name} wet on board (Packing and/or Contents)",
        f"Bundles of {display_name} moldy on board (Packing and/or Contents)",
    ]
    total_rec_str = f"{rec_str}  Bundles of {display_name}"
    return commodity, received_lines, total_rec_str


def _coils_received_template(rec_str):
    commodity = "COILS"
    received_lines = [
        "Coils Found Rusty on board",
        "Coils Packaging damaged on board",
    ]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _simple_received_template(rec_str, commodity):
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _unit_received_template(rec_str):
    commodity = "Unit"
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  Units"
    return commodity, received_lines, total_rec_str


def _package_received_template(rec_str):
    commodity = "package"
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _unit_package_received_template(rec_str):
    commodity = "Units + Package"
    received_lines = [commodity, f"{commodity} Damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _general_cargo_received_template(rec_str, display_name):
    commodity = display_name or "General Cargo"
    received_lines = ["Packaging damaged on board"]
    total_rec_str = f"{rec_str}  {commodity}"
    return commodity, received_lines, total_rec_str


def _compute_commodity_and_received_lines(raw_commodity: str, rec_str: str):
    """
    Given the raw commodity string from Excel and the received quantity string (rec_str),
    compute:
      - normalized commodity name
      - list of 'received' description lines
      - total_rec_str string to be displayed under 'Total Received'
    """
    raw_text = _normalize_commodity_text(raw_commodity)
    display_name = raw_text or "General Cargo"

    family, _ = _classify_commodity(raw_commodity)

    # ----------------------------------------------------------------
    # 1. Specific product families / KEYWORD_RULE canonical groups
    # ----------------------------------------------------------------
    if family == "BIG BAG":
        return _big_bags_received_template(rec_str)

    if family in {"MDF", "CTP", "FFP", "MDF + PLYWOOD", "PLYWOOD"}:
        return _crates_received_template(display_name, rec_str)

    if family in {"PIPE", "TUBE"}:
        commodity = "TUBES"
        received_lines = ["TUBES.", "TUBES Damaged on board"]
        total_rec_str = f"{rec_str}  {commodity}"
        return commodity, received_lines, total_rec_str

    if family == "POUTRELLE":
        return _simple_received_template(rec_str, commodity="POUTRELLES")

    if family == "CORNIERE":
        return _simple_received_template(rec_str, commodity="CORNIERES")

    if family in {"STEEL BEAMS", "BEAMS"}:
        return _bundles_received_template(display_name, rec_str, bundle_label="BEAMS")

    if family == "METAL SHEET":
        return _bundles_received_template(display_name, rec_str, bundle_label="METAL SHEET")
 
    if family in {"FIL M", "FILM", "FIL MACHINE"}:
        commodity = "FIL MACHINE"
        received_lines = ["RLX FOUND DISMEMBERED ON BOARD"]
        total_rec_str = f"{rec_str}  {commodity}"
        return commodity, received_lines, total_rec_str

    if family in {"COILS", "BOBINES", "BOB"}:
        return _coils_received_template(rec_str)

    if family in {"WHITE WOOD", "BEECH WOOD", "RED WOOD"}:
        return _lumber_received_template(display_name, rec_str)

    # if family == "FORMWORK":
    #     return _bundles_received_template(display_name, rec_str, bundle_label="formwork")


    # if family == "BRIDGE COMP":
    #     return _bundles_received_template(display_name, rec_str)

    # ----------------------------------------------------------------
    # 2. Unit / package buckets (multilingual + singular/plural)
    # ----------------------------------------------------------------
    # if _is_unit_package_combined(raw_text):
    #     return _unit_package_received_template(rec_str)

    unit_hit = _is_unit_type(raw_text) or _is_unit_type(family or "")
    package_hit = _is_package_type(raw_text) or _is_package_type(family or "")

    # if raw_text:
    #     unit_hit = unit_hit or matches_any_constant(raw_text, UNIT_CARGO_TYPES)
    #     package_hit = package_hit or matches_any_constant(raw_text, PACKAGE_CARGO_TYPES)

    # if family:
    #     unit_hit = unit_hit or matches_any_constant(family, UNIT_CARGO_TYPES)
    #     package_hit = package_hit or matches_any_constant(family, PACKAGE_CARGO_TYPES)  

    # if family in COMMODITY_TYPES and family not in GOODS__TYPES:
    #     unit_hit = True

    if unit_hit and package_hit:
        return _unit_package_received_template(rec_str)
    if package_hit:
        return _package_received_template(rec_str)
    if unit_hit:
        return _unit_received_template(rec_str)

    # ----------------------------------------------------------------
    # 3. General cargo fallback
    # ----------------------------------------------------------------
    return _general_cargo_received_template(rec_str, display_name)


def computecommodity_and_received_lines(raw_commodity: str, rec_str: str):
    """
    Public compatibility wrapper for the non-underscore function name.
    Retains the original signature and return tuple.
    """
    return _compute_commodity_and_received_lines(raw_commodity, rec_str)


def _fill_entry_table(
    doc,
    table,
    client: str,
    commodity: str,
    manifest_qty_str: str,
    tonnage_str: str,
    received_lines,
    total_rec_str: str,
):
    """
    Fill the 5-row table in the DOCX document for a single cargo entry.
    Handles:
      - Receiver / Commodity
      - Manifested Quantity / Tonnage
      - Dynamic 'Received:' lines
      - Total Received line
      - Final note and separator
    """
    # Row 0: Receiver / Commodity
    row0 = table.rows[0].cells
    row0[0].width = Cm(9)
    p0 = row0[0].paragraphs[0]
    p0.add_run("Receiver : ").bold = True
    p0.add_run(client)
    p0.alignment = WD_ALIGN_PARAGRAPH.LEFT

    row0[1].width = Cm(9)
    p1 = row0[1].paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_c = p1.add_run("Commodity : ")
    run_c1 = p1.add_run(commodity)
    run_c.bold = True
    run_c.font.name = "Agency FB"
    run_c1.font.name = "Agency FB"

    # Row 1: Manifested Quantity / Tonnage
    row1 = table.rows[1].cells
    row1[0].width = Cm(12)
    p2 = row1[0].paragraphs[0]
    p2.add_run("Manifested Quantity : ").bold = True
    p2.add_run(f"{manifest_qty_str} {commodity}")
    p2.alignment = WD_ALIGN_PARAGRAPH.LEFT

    row1[1].width = Cm(5)
    p3 = row1[1].paragraphs[0]
    p3.add_run("Tonnage : ").bold = True
    p3.add_run(f"{tonnage_str} Mt")
    p3.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # --- DYNAMIC RECEIVED AREA (Row 2) ---
    row2 = table.rows[2].cells
    row2[0].width = Cm(30)

    row2_cell = table.rows[2].cells[0]

    # Clear default paragraph and add the formatted lines
    row2_cell.paragraphs[0].clear()
    for i, line in enumerate(received_lines):
        if i == 0:
            p = row2_cell.paragraphs[0]
        else:
            p = row2_cell.add_paragraph()

        run_label = p.add_run("Received:    ")
        run_label.bold = True
        p.add_run(line)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Row 3: Total Received
    row3 = table.rows[3].cells
    row3[0].width = Cm(12)
    p4 = row3[0].paragraphs[0]
    p4.add_run("Total Received: ").bold = True
    p4.add_run(f" {total_rec_str}")
    p4.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Row 4: Final line
    row4 = table.rows[4].cells
    row4[0].width = Cm(25)
    p5 = row4[0].paragraphs[0]
    full = p5.add_run("The Quantity Will Be confirmed after delivery Cargo.")
    full.bold = True

    # Border Line
    p_sep = doc.add_paragraph()
    p_sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sep = p_sep.add_run("=*"*29)
    run_sep.bold = True


def _shorten_bl_code(bl: str) -> str:
    """
    Shorten B/L codes like '25030TJD0701-17' or '25030TJD0101/01'
    Rule: Find 3 consecutive letters, then take those 3 letters and everything after them.
    Examples:
        '25030TJD0701-17' -> 'TJD0701-17'
        '25030TJD0101/01' -> 'TJD0101/01'
    """
    if bl is None:
        return ""
    s = str(bl).strip()

    # Find 3 consecutive letters
    m = re.search(r"([A-Za-z]{3})(.*)$", s)
    if m:
        # Return the 3 letters + everything after them
        return m.group(1) + m.group(2)

    return s


def matches_any_constant(type_str, constants_set):
    """
    Check if type_str contains any constant from constants_set (or vice versa).
    Handles partial matches like "ENGINS" matching "ENGIN" or "grue lourd" matching "GRUE".
    Empty/None values never match.
    """
    type_str_upper = _normalize_match_text(type_str)
    if not type_str_upper:
        return False, ""

    for constant in constants_set:  
        constant_upper = _normalize_match_text(constant)
        if not constant_upper:
            continue
        if constant_upper in type_str_upper:
            return True, type_str_upper
        if type_str_upper in constant_upper:
            return True, type_str_upper
    return False, type_str_upper


def normalize_type(type_value, has_chassis=False, quantite=0, chassis_count=0):
    """
    Normalize TYPE value to standard categories.
    Recognizes French and English, singular and plural.
    Groups units and packages into 'UNITS + PACKAGES' or 'UNITS' or 'PACKAGES'
    using keywords or chassis and quantity comparisons.

    When called without chassis context (defaults), unit/package rows become
    UNITS or PACKAGES only. Combined UNITS + PACKAGES is decided later at
    client level in group_sourcefile_by_client.
    """
    if pd.isna(type_value):
        return None

    type_str = _normalize_commodity_text(type_value)
    if not type_str:
        return type_str

    # Already-normalized buckets
    if type_str in {"UNITS + PACKAGES", "UNITS + PACKAGE"}:
        return "UNITS + PACKAGES"
    if type_str == "UNITS":
        return "UNITS"
    if type_str == "PACKAGES":
        return "PACKAGES"

    # Structural/goods families first (BOBINE/COIL, PIPE/TUBE, POUTRELLE, CORNIERE, CTP, MDF, etc.)
    if _matches_keyword(type_str, "CTP"):
        return "CTP"
    if _matches_keyword(type_str, "BOBINE") or _matches_keyword(type_str, "BOB") or _matches_keyword(type_str, "COIL"):
        return "BOBINE"
    if _matches_keyword(type_str, "PIPE") or _matches_keyword(type_str, "TUBE"):
        return "PIPE"
    if _matches_keyword(type_str, "POUTRELLE"):
        return "POUTRELLE"
    if _matches_keyword(type_str, "CORNIERE") or _matches_keyword(type_str, "CORNIER"):
        return "CORNIERE"
    if _matches_keyword(type_str, "COFFRAGE") or _matches_keyword(type_str, "FORMWORK"):
        return "FORMWORK"

    structural_families = [
        "MDF + PLYWOOD", "MDF", "PLYWOOD", "FFP",
        "BEAMS", "STEEL BEAMS", "METAL SHEET",
        "FORMWORK", "FIL M", "BRIDGE COMP", "BIG BAG",
    ]
    structural_families.sort(
        key=lambda family: len(_normalize_commodity_text(family)),
        reverse=True,
    )
    for family in structural_families:
        if _matches_keyword(type_str, family):
            return family.upper()

    # Units and Packages classification
    is_unit = _is_unit_type(type_str)
    is_pkg = _is_package_type(type_str)

    if is_unit or is_pkg:
        # Optional chassis/quantity context (legacy / single-row callers)
        if has_chassis:
            if quantite > chassis_count:
                return "UNITS + PACKAGES"
            if is_unit or chassis_count > 0:
                return "UNITS"
            if is_pkg:
                return "PACKAGES"
        if is_unit and is_pkg:
            return "UNITS + PACKAGES"
        if is_unit:
            return "UNITS"
        if is_pkg:
            return "PACKAGES"

    return type_str


def first_non_null(series):
    return next((x for x in series if pd.notna(x)), None)


# Helper function for B/L aggregation
def aggregate_bl(series):
    """
    Collect every distinct, non-empty B/L value in the group and join them
    into a single aggregated string (e.g. 'BL1 / BL2 / BL3').
    """
    bl_values = []
    for x in series:
        if pd.notna(x):
            s = str(x).strip()
            if s:
                # In case a cell already contains ' / ', split and preserve distinct items
                parts = [p.strip() for p in s.split('/') if p.strip()]
                bl_values.extend(parts)
    if not bl_values:
        return ""
    unique_bls = list(dict.fromkeys(bl_values))
    return " / ".join(unique_bls)


# Specified order, plus the generic buckets that must be last.
COMMODITY_SORT_ORDER = {
    "CTP": 0,
    "BOBINE": 1,
    "PIPE": 2,
    "POUTRELLE": 3,
    "CORNIERE": 4,
    "UNITS + PACKAGES": 6,
    "UNITS": 7,
    "PACKAGES": 8,
}
# Priority for every structural / general commodity outside the explicit list.
OTHER_COMMODITY_SORT_PRIORITY = 5


def _canonical_sort_group(type_value):
    """
    Reduce a TYPE value to the canonical commodity group used for ordering.
    Supports English & French, singular & plural.
    Aliases such as TUBE/PIPE or BOB/COIL/BOBINE are collapsed so related
    structural commodities order together.
    """
    if type_value is None:
        return "OTHER"

    text = _normalize_commodity_text(type_value)
    if not text:
        return "OTHER"

   

    # Specified structural commodities and their aliases (FR + EN, sing + plur)
    if _matches_keyword(text, "CTP"):
        return "CTP"
    if _matches_keyword(text, "BOBINE") or _matches_keyword(text, "BOB") or _matches_keyword(text, "COIL"):
        return "BOBINE"
    if _matches_keyword(text, "PIPE") or _matches_keyword(text, "TUBE"):
        return "PIPE"
    if _matches_keyword(text, "POUTRELLE"):
        return "POUTRELLE"
    if _matches_keyword(text, "CORNIERE") or _matches_keyword(text, "CORNIER"):
        return "CORNIERE"

    structural_families = [
        "MDF + PLYWOOD",
        "MDF",
        "PLYWOOD",
        "FFP",
        "BEAMS",
        "STEEL BEAMS",
        "METAL SHEET",
        "FORMWORK",
        "FIL M",
        "BRIDGE COMP",
        "BIG BAG",
    ]
    structural_families.sort(
        key=lambda family: len(_normalize_commodity_text(family)),
        reverse=True,
    )
    for family in structural_families:
        if _matches_keyword(text, family):
            return family.upper()

    # Generic unit / package buckets
    family, _ = _classify_commodity(text)
    is_unit = _is_unit_type(text) or _is_unit_type(family or "")
    is_package = _is_package_type(text) or _is_package_type(family or "")

    if text in {"UNITS + PACKAGES", "UNITS + PACKAGE"} or (is_unit and is_package):
        return "UNITS + PACKAGES"
    if is_unit:
        return "UNITS"
    if is_package:
        return "PACKAGES"

    return text


def commodity_sort_priority(type_value):
    """
    Return the sort priority for a TYPE value used by both Bordereaux and
    Débarquement. Lower numbers are rendered first.
    """
    group = _canonical_sort_group(type_value)
    if group in COMMODITY_SORT_ORDER:
        return COMMODITY_SORT_ORDER[group]
    return OTHER_COMMODITY_SORT_PRIORITY


def _apply_commodity_sort(commodity_type):
    return commodity_sort_priority(commodity_type)


def group_sourcefile_by_client(
    input_excel: str,
    sheet_name: int | str = 0,
    skip_units_packages: bool = False,
    bl_aggregated: bool = False,
) -> pd.DataFrame:
    df = pd.read_excel(input_excel, sheet_name=sheet_name, engine="openpyxl")

    # ── Continuation rows: forward-fill CLIENT / B-L ──────────────────────
    # Manifest blocks leave CLIENT blank on sub-rows ("same as above"). A blank
    # CLIENT would make the final groupby([CLIENT, TYPE]) silently drop the row
    # (pandas drops NaN group keys by default), losing its quantity. Only blank
    # cells are filled — existing values are never overwritten.
    for _ffill_col in (COL_CLIENT, COL_BL):
        if _ffill_col in df.columns:
            df[_ffill_col] = df[_ffill_col].mask(
                df[_ffill_col].apply(_is_blank_manifest_cell)
            ).ffill()

    # Skip rows whose commodity type is in UNITS_TYPES or PACKAGES_TYPES
    if skip_units_packages and COL_TYPE in df.columns:
        skip_types = UNITS_TYPES | PACKAGES_TYPES
        df = df[
            ~df[COL_TYPE]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(skip_types)
        ].reset_index(drop=True)

    # Ensure numeric
    for col in [COL_QUANTITE, COL_TONAGE]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Short B/L into the same column
    if COL_BL in df.columns:
        df[COL_BL] = df[COL_BL].apply(_shorten_bl_code)

    # ── Fill missing TYPE from PRODUIT before normalization ──────────────
    if COL_TYPE in df.columns and COL_PRODUIT in df.columns:
        missing_type_mask = df[COL_TYPE].isna() | (df[COL_TYPE].astype(str).str.strip() == '')
        df.loc[missing_type_mask, COL_TYPE] = df.loc[missing_type_mask, COL_PRODUIT]
        has_chassis_col = COL_CHASSIS_SERIAL in df.columns

        # PASS 1 ─ keyword-only normalize (no chassis context)
        # e.g. BULLDOZER/CAMION/EXCAVATEURS → UNITS, COLIS → PACKAGES
        df["_norm_type"] = df[COL_TYPE].apply(lambda v: normalize_type(v))

        # PASS 2 ─ for each CLIENT, merge ALL unit/package rows into one label:
        # UNITS / PACKAGES / UNITS + PACKAGES. Structural rows keep Pass-1 type.
        def _apply_client_buckets(client_df: pd.DataFrame) -> pd.Series:
            
            # Check TYPE column for unit/package
            type_mask = client_df["_norm_type"].apply(_is_unit_or_package_bucket)
            
            # Also check PRODUIT column as fallback for rows where TYPE was empty
            produit_mask = pd.Series(False, index=client_df.index)
            if COL_PRODUIT in client_df.columns:
                produit_mask = client_df[COL_PRODUIT].apply(
                    lambda v: _is_unit_or_package_bucket(normalize_type(v)) 
                            if pd.notna(v) and str(v).strip() != '' 
                            else False
                )
            
            unit_pkg_mask = type_mask | produit_mask  # ← combine both
            labels = client_df["_norm_type"].copy()

            if not unit_pkg_mask.any():
                return labels

            subset = client_df.loc[unit_pkg_mask]
            quantite = int(subset[COL_QUANTITE].sum()) if COL_QUANTITE in subset.columns else 0
            chassis_count = (
                _count_real_chassis(subset[COL_CHASSIS_SERIAL]) if has_chassis_col else 0
            )

            has_unit = False
            has_pkg = False
            for idx, row in subset.iterrows():
                t_norm = _normalize_commodity_text(row["_norm_type"])
                p_norm = _normalize_commodity_text(row.get(COL_PRODUIT, "")) if COL_PRODUIT in subset.columns else ""
                
                # Check TYPE
                if _is_unit_type(t_norm) or t_norm in {"UNITS", "UNITS + PACKAGES"}:
                    has_unit = True
                if _is_package_type(t_norm) or t_norm in {"PACKAGES", "UNITS + PACKAGES"}:
                    has_pkg = True
                
                # Check PRODUIT as fallback
                if _is_unit_type(p_norm):
                    has_unit = True
                if _is_package_type(p_norm):
                    has_pkg = True
                
                # Chassis = unit
                if has_chassis_col and not _is_blank_chassis(row.get(COL_CHASSIS_SERIAL)):
                    has_unit = True

            final_label = _decide_client_unit_package_label(
                has_unit=has_unit,
                has_pkg=has_pkg,
                quantite=quantite,
                chassis_count=chassis_count,
            )
            labels.loc[unit_pkg_mask] = final_label
            return labels

        # Per-client bucketing via an explicit loop (not groupby.apply):
        # with a single client group, groupby.apply returns a wide DataFrame
        # instead of a Series and the assignment below crashes.
        _bucket_parts = [
            _apply_client_buckets(group_df)
            for _, group_df in df.groupby(COL_CLIENT, dropna=False, group_keys=False)
        ]
        if _bucket_parts:
            df[COL_TYPE] = pd.concat(_bucket_parts)
        else:
            df[COL_TYPE] = df["_norm_type"]
        df = df.drop(columns=["_norm_type"])

    # ── Aggregation ───────────────────────────────────────────────────────
    agg_dict = {
        COL_QUANTITE: "sum",
        COL_TONAGE: "sum",
        COL_BL: aggregate_bl,
    }

    skip_cols = [COL_CLIENT, COL_QUANTITE, COL_TONAGE, COL_BL, COL_PRODUIT, COL_TYPE]

    if not bl_aggregated:
        skip_cols.remove(COL_BL)
        agg_dict.pop(COL_BL, None)

    for col in COLUMNS:
        if col in skip_cols:
            continue
        if col in df.columns:
            agg_dict[col] = first_non_null

    grouped = df.groupby([COL_CLIENT, COL_TYPE], as_index=False).agg(agg_dict)

    grouped["sort_priority"] = grouped[COL_TYPE].apply(_apply_commodity_sort)

    sorted_grouped = grouped.sort_values(
        by=["sort_priority", COL_CLIENT],
        ascending=[True, True],
        na_position="last",
    ).reset_index(drop=True)

    sorted_grouped = sorted_grouped.drop(columns=["sort_priority"])

    return sorted_grouped

