import streamlit as st
import os
import time
import logging
import traceback
import io
import zipfile
import tempfile
from pathlib import Path
from typing import List, Tuple
import openpyxl
from openpyxl.utils import get_column_letter
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib import colors as mcolors
import numpy as np


# ==========================================================
# ===================== CORE LOGIC =========================
# ===================== (YOUR ORIGINAL FUNCTIONS) ===========
# ==========================================================


def get_excel_files(folder: str, extensions: List[str]) -> List[Path]:
    return sorted(
        f
        for f in Path(folder).iterdir()
        if f.is_file()
        and f.suffix.lower() in extensions
        and not f.name.startswith("~$")
    )


def get_true_last_col(
    sheet, start_row: int, end_row: int, start_col: int, end_col: int
) -> int:
    for col in range(end_col, start_col - 1, -1):
        for row in range(start_row, end_row + 1):
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
    for row in range(start_row, end_row + 1):
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
# ====== LINUX-COMPATIBLE IMAGE EXPORT (replaces win32) ====
# ==========================================================


def get_cell_bg_color(cell):
    """Extract background color from openpyxl cell, return hex string."""
    try:
        fill = cell.fill
        if fill and fill.fill_type not in (None, "none"):
            fg = fill.fgColor
            if fg.type == "rgb" and fg.rgb and fg.rgb != "00000000":
                hex_color = fg.rgb  # ARGB format
                # Convert ARGB to RGB
                return f"#{hex_color[2:]}"
            elif fg.type == "theme":
                return "#FFFFFF"
    except Exception:
        pass
    return "#FFFFFF"


def get_cell_font_color(cell):
    """Extract font color from openpyxl cell, return hex string."""
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


def export_range_as_image(
    sheet, rng_bounds: Tuple[int, int, int, int], output_path: str
) -> None:
    """
    Renders a range of cells from an openpyxl sheet as a PNG image.
    rng_bounds: (start_row, end_row, start_col, end_col) — 1-indexed
    """
    start_row, end_row, start_col, end_col = rng_bounds

    n_rows = end_row - start_row + 1
    n_cols = end_col - start_col + 1

    # Build cell data matrix
    cell_texts = []
    cell_bg_colors = []
    cell_font_colors = []
    cell_bold = []

    for r in range(start_row, end_row + 1):
        row_texts = []
        row_bg = []
        row_fg = []
        row_bold = []
        for c in range(start_col, end_col + 1):
            cell = sheet.cell(row=r, column=c)
            val = cell.value
            text = "" if val is None else str(val)
            row_texts.append(text)
            row_bg.append(get_cell_bg_color(cell))
            row_fg.append(get_cell_font_color(cell))
            row_bold.append(get_cell_font_bold(cell))
        cell_texts.append(row_texts)
        cell_bg_colors.append(row_bg)
        cell_font_colors.append(row_fg)
        cell_bold.append(row_bold)

    # Figure sizing
    col_width = 2.2
    row_height = 0.45
    fig_width = max(n_cols * col_width, 4)
    fig_height = max(n_rows * row_height, 1.5)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.set_xlim(0, n_cols)
    ax.set_ylim(0, n_rows)
    ax.axis("off")

    for r_idx in range(n_rows):
        for c_idx in range(n_cols):
            x = c_idx
            # Rows drawn top-to-bottom
            y = n_rows - r_idx - 1

            bg = cell_bg_colors[r_idx][c_idx]
            fg = cell_font_colors[r_idx][c_idx]
            bold = cell_bold[r_idx][c_idx]
            text = cell_texts[r_idx][c_idx]

            # Draw cell background
            rect = plt.Rectangle(
                (x, y), 1, 1, facecolor=bg, edgecolor="#CCCCCC", linewidth=0.5
            )
            ax.add_patch(rect)

            # Draw cell text
            ax.text(
                x + 0.5,
                y + 0.5,
                text,
                ha="center",
                va="center",
                fontsize=8,
                color=fg,
                fontweight="bold" if bold else "normal",
                wrap=False,
                clip_on=True,
            )

    plt.tight_layout(pad=0.1)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
