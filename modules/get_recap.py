import os
import logging
from pathlib import Path
from typing import List, Tuple

import openpyxl
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def get_excel_files(folder: str, extensions: List[str]) -> List[Path]:
    return sorted(
        f
        for f in Path(folder).iterdir()
        if f.is_file()
        and f.suffix.lower() in extensions
        and not f.name.startswith("~$")
    )


def get_used_bounds(ws) -> Tuple[int, int, int, int]:
    min_row = ws.min_row
    max_row = ws.max_row
    min_col = ws.min_column
    max_col = ws.max_column
    return min_row, max_row, min_col, max_col


def column_has_data(ws, col: int, start_row: int, end_row: int) -> bool:
    for row in range(start_row, end_row + 1):
        val = ws.cell(row=row, column=col).value
        if val is not None and str(val).strip() != "":
            return True
    return False


def detect_horizontal_tables(ws) -> List[Tuple[int, int, int, int]]:
    """Detect horizontal table blocks by finding contiguous data columns."""
    start_row, end_row, start_col, end_col = get_used_bounds(ws)
    tables = []
    block_start = None

    for col in range(start_col, end_col + 2):
        has_data = col <= end_col and column_has_data(ws, col, start_row, end_row)
        if has_data and block_start is None:
            block_start = col
        elif not has_data and block_start is not None:
            tables.append((block_start, col - 1, start_row, end_row))
            block_start = None

    return tables


def export_range_as_image(
    ws,
    start_col: int,
    end_col: int,
    start_row: int,
    end_row: int,
    output_path: str,
) -> None:
    """Export a range of cells as a PNG image using matplotlib."""
    data = []
    for row in range(start_row, end_row + 1):
        row_data = []
        for col in range(start_col, end_col + 1):
            val = ws.cell(row=row, column=col).value
            row_data.append("" if val is None else str(val))
        data.append(row_data)

    if not data:
        return

    n_rows = len(data)
    n_cols = len(data[0]) if data else 1

    fig_w = max(6, n_cols * 1.8)
    fig_h = max(1.5, n_rows * 0.45)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")

    table = ax.table(
        cellText=data,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.4)

    # Style header row slightly different
    for col_idx in range(n_cols):
        cell = table[0, col_idx]
        cell.set_facecolor("#d0e4f7")
        cell.set_text_props(weight="bold")

    plt.tight_layout(pad=0.2)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
