import streamlit as st
import os
import time
import logging
import traceback
import io
import zipfile
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles.borders import Border
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib import colors as mcolors
import numpy as np
import re


# ==========================================================
# ===================== CORE LOGIC =========================
# ==========================================================


def get_excel_files(folder: str, extensions: List[str]) -> List[Path]:
    return sorted(
        f
        for f in Path(folder).iterdir()
        if f.is_file()
        and f.suffix.lower() in extensions
        and not f.name.startswith("~$")
    )


def is_row_hidden(sheet, row: int) -> bool:
    """Check if a row is hidden in the sheet."""
    try:
        rd = sheet.row_dimensions.get(row)
        if rd and rd.hidden:
            return True
    except Exception:
        pass
    return False


def is_col_hidden(sheet, col: int) -> bool:
    """Check if a column is hidden in the sheet."""
    try:
        col_letter = get_column_letter(col)
        cd = sheet.column_dimensions.get(col_letter)
        if cd and cd.hidden:
            return True
    except Exception:
        pass
    return False


def get_visible_rows(sheet, start_row: int, end_row: int) -> List[int]:
    """Return list of visible row indices in the range."""
    return [r for r in range(start_row, end_row + 1) if not is_row_hidden(sheet, r)]


def get_visible_cols(sheet, start_col: int, end_col: int) -> List[int]:
    """Return list of visible column indices in the range."""
    return [c for c in range(start_col, end_col + 1) if not is_col_hidden(sheet, c)]


def get_true_last_col(
    sheet, start_row: int, end_row: int, start_col: int, end_col: int
) -> int:
    for col in range(end_col, start_col - 1, -1):
        if is_col_hidden(sheet, col):
            continue
        for row in range(start_row, end_row + 1):
            if is_row_hidden(sheet, row):
                continue
            val = sheet.cell(row=row, column=col).value
            if val is not None and str(val).strip() != "":
                return col
    return start_col


def get_used_bounds(sheet) -> Tuple[int, int, int, int]:
    start_row = sheet.min_row
    start_col = sheet.min_column
    end_row = sheet.max_row
    end_col = sheet.max_column
    true_end_col = get_true_last_col(sheet, start_row, end_row, start_col, end_col)
    return start_row, end_row, start_col, true_end_col


def column_has_data(sheet, col: int, start_row: int, end_row: int) -> bool:
    if is_col_hidden(sheet, col):
        return False
    for row in range(start_row, end_row + 1):
        if is_row_hidden(sheet, row):
            continue
        val = sheet.cell(row=row, column=col).value
        if val is not None and str(val).strip() != "":
            return True
    return False


def detect_horizontal_tables(sheet) -> List[Tuple[int, int, int, int]]:
    start_row, end_row, start_col, end_col = get_used_bounds(sheet)
    tables = []
    block_start = None

    for col in range(start_col, end_col + 2):
        has_data = col <= end_col and column_has_data(sheet, col, start_row, end_row)
        if has_data and block_start is None:
            block_start = col
        elif not has_data and block_start is not None:
            tables.append((block_start, col - 1, start_row, end_row))
            block_start = None
    return tables


# ==========================================================
# ====== TOTAL/J LANDMARK + BORDERS DETECTION ==============
# ==========================================================


def cell_has_any_border(cell) -> bool:
    try:
        b = cell.border
        sides = [b.left, b.right, b.top, b.bottom]
        return any(
            s is not None and s.border_style is not None and s.border_style != "none"
            for s in sides
        )
    except Exception:
        return False


def find_totalj_col(
    sheet, start_row: int, end_row: int, start_col: int, end_col: int
) -> Optional[int]:
    pattern = re.compile(r"total\s*/\s*j", re.IGNORECASE)
    for col in range(end_col, start_col - 1, -1):
        if is_col_hidden(sheet, col):
            continue
        for row in range(start_row, end_row + 1):
            if is_row_hidden(sheet, row):
                continue
            val = sheet.cell(row=row, column=col).value
            if val is not None and pattern.search(str(val).strip()):
                return col
    return None


def find_last_bordered_table(
    sheet, start_row: int, end_row: int, start_col: int, end_col: int
) -> Optional[Tuple[int, int, int, int]]:
    totalj_col = find_totalj_col(sheet, start_row, end_row, start_col, end_col)
    if totalj_col is None:
        return None

    block_end = totalj_col
    block_start = totalj_col

    for col in range(totalj_col - 1, start_col - 1, -1):
        if is_col_hidden(sheet, col):
            continue
        col_bordered = any(
            cell_has_any_border(sheet.cell(row=r, column=col))
            for r in range(start_row, end_row + 1)
            if not is_row_hidden(sheet, r)
        )
        if col_bordered:
            block_start = col
        else:
            break

    return (block_start, block_end, start_row, end_row)


def get_last_table_bounds(
    sheet, col_limit: int
) -> Optional[Tuple[int, int, int, int]]:
    start_row, end_row, start_col, end_col = get_used_bounds(sheet)
    tables = detect_horizontal_tables(sheet)

    if not tables:
        return None

    last_start_col, last_end_col, t_start_row, t_end_row = tables[-1]

    bordered = find_last_bordered_table(
        sheet, t_start_row, t_end_row, last_start_col, last_end_col
    )

    if bordered:
        b_start_col, b_end_col, b_start_row, b_end_row = bordered
        # Get only visible columns in the bordered block
        vis_cols = get_visible_cols(sheet, b_start_col, b_end_col)
        if col_limit < len(vis_cols):
            # Take only last col_limit visible columns
            vis_cols = vis_cols[-col_limit:]
        return (vis_cols[0], vis_cols[-1], b_start_row, b_end_row)
    else:
        vis_cols = get_visible_cols(sheet, last_start_col, last_end_col)
        if col_limit < len(vis_cols):
            vis_cols = vis_cols[-col_limit:]
        return (vis_cols[0], vis_cols[-1], t_start_row, t_end_row)


# ==========================================================
# ====== LINUX-COMPATIBLE IMAGE EXPORT =====================
# ==========================================================


def get_cell_bg_color(cell):
    try:
        fill = cell.fill
        if fill and fill.fill_type not in (None, "none"):
            fg = fill.fgColor
            if fg.type == "rgb" and fg.rgb and fg.rgb != "00000000":
                return f"#{fg.rgb[2:]}"
            elif fg.type == "theme":
                return "#FFFFFF"
    except Exception:
        pass
    return "#FFFFFF"


def get_cell_font_color(cell):
    try:
        font = cell.font
        if font and font.color:
            fc = font.color
            if fc.type == "rgb" and fc.rgb and fc.rgb != "00000000":
                return f"#{fc.rgb[2:]}"
    except Exception:
        pass
    return "#000000"


def get_cell_font_bold(cell):
    try:
        return cell.font.bold if cell.font else False
    except Exception:
        return False


def get_border_edges(cell) -> dict:
    edges = {"left": False, "right": False, "top": False, "bottom": False}
    try:
        b = cell.border
        for side in edges:
            s = getattr(b, side, None)
            if s and s.border_style and s.border_style != "none":
                edges[side] = True
    except Exception:
        pass
    return edges

from playwright.sync_api import sync_playwright
from html import escape


def build_html_table(sheet, start_row, end_row, start_col, end_col):
    merged_ranges = sheet.merged_cells.ranges

    # Map merged cells
    merge_map = {}
    for merge in merged_ranges:
        min_row, min_col, max_row, max_col = merge.bounds
        if min_row >= start_row and max_row <= end_row:
            merge_map[(min_row, min_col)] = (max_row, max_col)

    html = """
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        body { font-family: Calibri, Arial; }
        table { border-collapse: collapse; }
        td {
            border: 1px solid black;
            padding: 4px;
            font-size: 13px;
            vertical-align: middle;
            text-align: center;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
    </style>
    </head>
    <body>
    <table>
    """

    skip_cells = set()

    for r in range(start_row, end_row + 1):
        if sheet.row_dimensions.get(r) and sheet.row_dimensions[r].hidden:
            continue

        html += "<tr>"

        for c in range(start_col, end_col + 1):
            if sheet.column_dimensions.get(sheet.cell(row=1, column=c).column_letter) and \
               sheet.column_dimensions[sheet.cell(row=1, column=c).column_letter].hidden:
                continue

            if (r, c) in skip_cells:
                continue

            cell = sheet.cell(row=r, column=c)
            value = "" if cell.value is None else escape(str(cell.value))

            style = ""

            # Background color
            fill = cell.fill
            if fill and fill.fill_type and fill.fgColor.type == "rgb":
                style += f"background-color:#{fill.fgColor.rgb[2:]};"

            # Font bold
            if cell.font and cell.font.bold:
                style += "font-weight:bold;"

            # Font color
            if cell.font and cell.font.color and cell.font.color.type == "rgb":
                style += f"color:#{cell.font.color.rgb[2:]};"

            rowspan = 1
            colspan = 1

            if (r, c) in merge_map:
                max_row, max_col = merge_map[(r, c)]
                rowspan = max_row - r + 1
                colspan = max_col - c + 1

                for rr in range(r, max_row + 1):
                    for cc in range(c, max_col + 1):
                        if (rr, cc) != (r, c):
                            skip_cells.add((rr, cc))

            html += f'<td rowspan="{rowspan}" colspan="{colspan}" style="{style}">{value}</td>'

        html += "</tr>"

    html += """
    </table>
    </body>
    </html>
    """

    return html