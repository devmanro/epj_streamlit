"""Tests for tools.tools.expand_manifest_packages (pre-alignment step).

Raw manifests group rows in blocks: a header row carries the CLIENT name
(and usually the global 'nombre colis' / 'Poids brute'), followed by
continuation sub-rows with an empty CLIENT — one physical entity per row.
"""
import pandas as pd

from assets.constants.constants import (
    COL_BL,
    COL_CHASSIS_SERIAL,
    COL_CLIENT,
    COL_PRODUIT,
    COL_QUANTITE,
    COL_TONAGE,
    COL_TYPE,
)
from tools.tools import (
    GENERATED_PACKAGE_LABEL,
    expand_manifest_packages,
    group_sourcefile_by_client,
)


SRC_CLIENT = "Client"
SRC_QTY = "nombre colis"
SRC_W = "Poids brute"
SRC_CH = "Némuro de chassis"
SRC_BL = "BL"
SRC_TYPE = "type"
SRC_PROD = "PRODUITS"


def _mapping(with_product_type=True):
    mapping = {
        SRC_CLIENT: COL_CLIENT,
        SRC_QTY: COL_QUANTITE,
        SRC_W: COL_TONAGE,
        SRC_CH: COL_CHASSIS_SERIAL,
        SRC_BL: COL_BL,
    }
    if with_product_type:
        mapping[SRC_TYPE] = COL_TYPE
        mapping[SRC_PROD] = COL_PRODUIT
    return mapping


def _row(client=None, bl=None, qty=None, w=None, chassis=None,
         type_=None, produit=None):
    return {
        SRC_CLIENT: client,
        SRC_BL: bl,
        SRC_QTY: qty,
        SRC_W: w,
        SRC_CH: chassis,
        SRC_TYPE: type_,
        SRC_PROD: produit,
    }


# ── Package expansion ────────────────────────────────────────────────────

def test_global_exceeds_chassis_adds_colis_row():
    df = pd.DataFrame([_row("CLI A", "B1", 3, 36000, "CH-001", "excavator", "lourd")])
    out, report = expand_manifest_packages(df, _mapping())

    assert report["rows_added"] == 1
    assert len(out) == 2
    # Header keeps only its own unit.
    assert out.loc[0, SRC_QTY] == 1
    assert out.loc[0, SRC_W] == 36000
    # Generated row: global - chassis, labelled COLIS, client attached.
    gen = out.loc[1]
    assert gen[SRC_QTY] == 2
    assert gen[SRC_W] == 0
    assert gen[SRC_TYPE] == GENERATED_PACKAGE_LABEL == "COLIS"
    assert gen[SRC_PROD] == GENERATED_PACKAGE_LABEL
    assert gen[SRC_CLIENT] == "CLI A"
    assert gen[SRC_BL] == "B1"
    assert pd.isna(gen[SRC_CH])
    # Block total still equals the global quantity.
    assert out[SRC_QTY].sum() == 3


def test_continuation_rows_attached_and_aligned():
    # Global header + 5 chassis sub-rows carrying single weights, no qty.
    rows = [_row("AIB OMAR", "B6", 6, 98040, "CH-0", "engins", "engins")]
    for i, w in enumerate([13840, 13840, 13840, 13840, 28840], start=1):
        rows.append(_row(None, None, None, w, f"CH-{i}", "engins", "engins"))
    df = pd.DataFrame(rows)
    out, report = expand_manifest_packages(df, _mapping())

    assert report["rows_added"] == 0
    assert report["client_cells_filled"] == 5
    assert report["bl_cells_filled"] == 5
    assert (out[SRC_CLIENT] == "AIB OMAR").all()
    assert (out[SRC_BL] == "B6").all()
    # Single-entity alignment: header + each chassis row count 1.
    assert out[SRC_QTY].tolist() == [1, 1, 1, 1, 1, 1]
    # Header keeps its own single weight: global - sub-rows.
    assert out.loc[0, SRC_W] == 13840
    assert out[SRC_W].sum() == 98040


def test_global_header_without_own_chassis():
    rows = [
        _row("CLI A", "B1", 10, 5000, None, "engins", "engins"),
        _row(None, None, None, 1000, "CH-1", "engins", "engins"),
        _row(None, None, None, 1000, "CH-2", "engins", "engins"),
    ]
    out, report = expand_manifest_packages(pd.DataFrame(rows), _mapping())

    # 10 - 2 chassis = 8 packages on a generated row; header stripped to 0.
    assert report["rows_added"] == 1
    assert out.loc[0, SRC_QTY] == 0
    assert out.loc[1, SRC_QTY] == 1
    assert out.loc[2, SRC_QTY] == 1
    assert out.loc[3, SRC_QTY] == 8
    assert out.loc[3, SRC_CLIENT] == "CLI A"
    assert out[SRC_QTY].sum() == 10


def test_distributed_block_left_untouched():
    # Already itemized layout (unit row + COLIS row, client repeated).
    rows = [
        _row("EURL AID", "B1", 1, 36, "CH-1", "excavator", "lourd"),
        _row("EURL AID", "B1", 2, 0, None, "colis", "colis"),
    ]
    df = pd.DataFrame(rows)
    out, report = expand_manifest_packages(df, _mapping())

    assert report["rows_added"] == 0
    assert report["warnings"] == []
    pd.testing.assert_frame_equal(out.reset_index(drop=True), df)


def test_pure_bulk_block_untouched():
    df = pd.DataFrame([_row("CHINA ROAD", "B1", 339, 1399, None, "COLIS", "COLIS")])
    out, report = expand_manifest_packages(df, _mapping())

    assert report["rows_added"] == 0
    assert out.loc[0, SRC_QTY] == 339
    assert report["warnings"] == []


def test_french_number_strings_normalized():
    df = pd.DataFrame([_row("CLI A", "B1", "3", "36 000", "CH-1", "engins", "engins")])
    out, report = expand_manifest_packages(df, _mapping())

    assert out.loc[0, SRC_W] == 36000
    assert report["rows_added"] == 1
    assert out.loc[1, SRC_QTY] == 2


# ── Filtering / validation ───────────────────────────────────────────────

def test_empty_rows_dropped_and_orphans_warned():
    rows = [
        _row(),  # fully empty → dropped
        _row(None, None, 5, 100, None, "colis", "colis"),  # orphan → kept + warned
        _row("CLI A", "B1", 2, 50, "CH-1", "engins", "engins"),
    ]
    out, report = expand_manifest_packages(pd.DataFrame(rows), _mapping())

    assert report["rows_dropped_empty"] == 1
    assert len(out) == 3  # orphan + header + generated COLIS row
    assert any("leading row" in w for w in report["warnings"])


def test_missing_product_type_warns():
    df = pd.DataFrame([_row("CLI A", "B1", 10, 500, None, None, None)])
    _, report = expand_manifest_packages(df, _mapping())

    assert any("product/type" in w for w in report["warnings"])


def test_unmapped_type_produit_warns_once():
    df = pd.DataFrame([_row("CLI A", "B1", 3, 100, "CH-1")])
    _, report = expand_manifest_packages(df, _mapping(with_product_type=False))

    assert any("not mapped" in w for w in report["warnings"])


def test_unmapped_client_or_qty_returns_untouched():
    df = pd.DataFrame([_row("CLI A", "B1", 3, 100, "CH-1")])
    out, report = expand_manifest_packages(df, {SRC_QTY: COL_QUANTITE})

    assert report["ok"] is False
    pd.testing.assert_frame_equal(out, df)


# ── Downstream grouping (the original "output = 4" bug) ──────────────────

def test_groupby_keeps_blank_client_rows_single_client(tmp_path):
    # The 7-row DENNOUNI case: 4 ENGINS rows + 3 COLIS rows with blank CLIENT.
    rows = []
    for ch in ["CH-1", "CH-2", "CH-3", "CH-4"]:
        rows.append({COL_CLIENT: "SARL E.T.P. DENNOUNI", COL_TYPE: "ENGINS",
                     COL_PRODUIT: "ENGINS", COL_QUANTITE: 1, COL_TONAGE: 10,
                     COL_BL: "B1", COL_CHASSIS_SERIAL: ch})
    for q in [1, 2, 3]:
        rows.append({COL_CLIENT: None, COL_TYPE: None, COL_PRODUIT: "COLIS",
                     COL_QUANTITE: q, COL_TONAGE: 1, COL_BL: "B1",
                     COL_CHASSIS_SERIAL: None})
    path = tmp_path / "case.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)

    grouped = group_sourcefile_by_client(str(path))

    assert len(grouped) == 1
    assert grouped.loc[0, COL_CLIENT] == "SARL E.T.P. DENNOUNI"
    assert grouped.loc[0, COL_TYPE] == "UNITS + PACKAGES"
    assert grouped.loc[0, COL_QUANTITE] == 10


def test_end_to_end_raw_denouni_blocks(tmp_path):
    # Raw manifest style: 4 header rows, global qty + 1 chassis each.
    raw = pd.DataFrame([
        _row("SARL E.T.P. DENNOUNI", "LYG223", 2, 34.5, "CH-A", "excavator", "engins"),
        _row("SARL E.T.P. DENNOUNI", "LYG224", 3, 25.8, "CH-B", "finisseur", "engins"),
        _row("SARL E.T.P. DENNOUNI", "LYG228", 4, 38.5, "CH-C", "bulldozer", "engins"),
        _row("SARL E.T.P. DENNOUNI", "LYG234", 1, 17.6, "CH-D", "chargeur", "engins"),
    ])
    mapping = _mapping()
    expanded, report = expand_manifest_packages(raw, mapping)
    assert report["rows_added"] == 3  # (2-1) + (3-1) + (4-1) + (1-1)

    # Simulate align_data's rename step (no API call) then group.
    final_cols = [v for v in mapping.values() if v is not None]
    aligned = expanded.rename(columns=mapping)[final_cols]
    path = tmp_path / "aligned.xlsx"
    aligned.to_excel(path, index=False)
    grouped = group_sourcefile_by_client(str(path))

    total = grouped.loc[grouped[COL_CLIENT] == "SARL E.T.P. DENNOUNI", COL_QUANTITE].sum()
    assert total == 10
    label = grouped.loc[grouped[COL_CLIENT] == "SARL E.T.P. DENNOUNI", COL_TYPE].iloc[0]
    assert label == "UNITS + PACKAGES"
