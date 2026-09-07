"""
Tests for B/L aggregation and the shared commodity ordering used by both the
Bordereaux and Débarquement documents.

Ordering contract (tools.tools.commodity_sort_priority):
    CTP, BOBINE, PIPE, POUTRELLE, CORNIERE   -> 0..4 (specified commodities)
    every other structural/goods commodity   -> 5
    UNITS + PACKAGES, UNITS, PACKAGES        -> 6..8 (always last, in order)
"""
import pandas as pd
import pytest

from assets.constants.constants import COL_BL, COL_CLIENT, COL_QUANTITE, COL_TONAGE, COL_TYPE
from tools.tools import (
    COMMODITY_SORT_ORDER,
    OTHER_COMMODITY_SORT_PRIORITY,
    _canonical_sort_group,
    aggregate_bl,
    commodity_sort_priority,
    group_sourcefile_by_client,
    matches_any_constant,
    normalize_type,
)


# ---------------------------------------------------------------------------
# aggregate_bl
# ---------------------------------------------------------------------------

def test_aggregate_bl_joins_distinct_values_with_slash():
    series = pd.Series(["BL1", "BL2", "BL3"])
    assert aggregate_bl(series) == "BL1 / BL2 / BL3"


def test_aggregate_bl_dedupes_and_keeps_first_seen_order():
    series = pd.Series(["BL2", "BL1", "BL2", "BL1"])
    assert aggregate_bl(series) == "BL2 / BL1"


def test_aggregate_bl_ignores_null_and_blank_values():
    series = pd.Series([None, "  ", "BL7", float("nan")])
    assert aggregate_bl(series) == "BL7"


def test_aggregate_bl_empty_group_returns_empty_string():
    assert aggregate_bl(pd.Series([None, " ", float("nan")])) == ""


# ---------------------------------------------------------------------------
# matches_any_constant hardening
# ---------------------------------------------------------------------------

def test_matches_any_constant_never_matches_empty_or_none():
    assert matches_any_constant("", {"BUS", "CAMIONS"}) is False
    assert matches_any_constant(None, {"BUS", "CAMIONS"}) is False


def test_matches_any_constant_is_delimiter_insensitive():
    # Underscores/hyphens are treated as spaces on both sides.
    assert matches_any_constant("DUMP TRUCK", {"DUMP_TRUCK"}) is True
    assert matches_any_constant("DUMP-TRUCK", {"DUMP_TRUCK"}) is True


def test_matches_any_constant_still_matches_partial_fragments():
    assert matches_any_constant("ENGINS", {"ENGIN"}) is True
    assert matches_any_constant("grue lourd", {"GRUE"}) is True


# ---------------------------------------------------------------------------
# normalize_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "type_value, expected",
    [
        # Structural / goods families are preserved verbatim (upper-cased).
        ("COLIS", "COLIS"),          # not collapsed to PACKAGES via "COLI"
        ("TUBE", "TUBE"),
        ("CTP", "CTP"),
        ("BOBINE", "BOBINE"),
        ("POUTRELLE", "POUTRELLE"),
        ("CORNIERE", "CORNIERE"),
        ("MDF", "MDF"),
        # Explicit combined label is canonicalised.
        ("UNITS + PACKAGES", "UNITS + PACKAGES"),
        ("UNITS+PACKAGES", "UNITS + PACKAGES"),
        # Unit / package commodities collapse into the generic buckets.
        ("CAMIONS", "UNITS"),
        ("EXCAVATEUR", "UNITS"),
        ("DUMP TRUCK", "UNITS"),
        ("WELDING MACHINE", "PACKAGES"),
        ("COLI", "PACKAGES"),
        # NaN stays null so groupby can drop it.
        (float("nan"), None),
    ],
)
def test_normalize_type(type_value, expected):
    assert normalize_type(type_value) == expected


# ---------------------------------------------------------------------------
# commodity ordering
# ---------------------------------------------------------------------------

def test_canonical_sort_group_aliases():
    assert _canonical_sort_group("TUBE") == "PIPE"
    assert _canonical_sort_group("PIPE") == "PIPE"
    assert _canonical_sort_group("COIL") == "BOBINE"
    assert _canonical_sort_group("BOB") == "BOBINE"
    assert _canonical_sort_group("BOBINE") == "BOBINE"
    assert _canonical_sort_group("UNITS+PACKAGES") == "UNITS + PACKAGES"


def test_colis_is_structural_not_package_bucket():
    # "COLIS" contains the package fragment "COLI" but is a goods commodity.
    assert _canonical_sort_group("COLIS") == "COLIS"
    assert commodity_sort_priority("COLIS") == OTHER_COMMODITY_SORT_PRIORITY
    assert commodity_sort_priority("COLIS") < commodity_sort_priority("UNITS + PACKAGES")
    assert commodity_sort_priority("COLIS") < commodity_sort_priority("UNITS")
    assert commodity_sort_priority("COLIS") < commodity_sort_priority("PACKAGES")


def test_specified_commodities_come_first_in_order():
    assert (
        commodity_sort_priority("CTP")
        < commodity_sort_priority("BOBINE")
        < commodity_sort_priority("PIPE")
        < commodity_sort_priority("POUTRELLE")
        < commodity_sort_priority("CORNIERE")
        < OTHER_COMMODITY_SORT_PRIORITY
    )
    # Explicit priorities mirror COMMODITY_SORT_ORDER.
    assert commodity_sort_priority("CTP") == COMMODITY_SORT_ORDER["CTP"] == 0
    assert commodity_sort_priority("BOBINE") == COMMODITY_SORT_ORDER["BOBINE"] == 1


def test_generic_buckets_always_last_in_exact_sequence():
    assert (
        commodity_sort_priority("UNITS + PACKAGES")
        < commodity_sort_priority("UNITS")
        < commodity_sort_priority("PACKAGES")
    )
    # ...and after every other structural commodity.
    for structural in ("CTP", "BOBINE", "TUBE", "POUTRELLE", "CORNIERE", "COLIS", "MDF"):
        assert commodity_sort_priority(structural) < commodity_sort_priority("UNITS + PACKAGES")


def test_unit_and_package_cargo_fall_into_generic_buckets():
    assert commodity_sort_priority("CAMIONS") == COMMODITY_SORT_ORDER["UNITS"]
    assert commodity_sort_priority("DUMP TRUCK") == COMMODITY_SORT_ORDER["UNITS"]
    assert commodity_sort_priority("WELDING MACHINE") == COMMODITY_SORT_ORDER["PACKAGES"]


# ---------------------------------------------------------------------------
# group_sourcefile_by_client (end-to-end on a real Excel file)
# ---------------------------------------------------------------------------

def _write_source(tmp_path, rows):
    df = pd.DataFrame(rows, columns=[COL_CLIENT, COL_TYPE, COL_QUANTITE, COL_TONAGE, COL_BL])
    filepath = tmp_path / "manifest.xlsx"
    df.to_excel(filepath, index=False)
    return str(filepath)


def test_grouping_aggregates_bl_and_sums_quantities(tmp_path):
    filepath = _write_source(tmp_path, [
        ("ACME", "CTP", 2, 4.5, "25030TJD0701-17"),
        ("ACME", "CTP", 3, 5.5, "25030TJD0101/01"),
        ("ACME", "CTP", 1, 1.0, "25030TJD0701-17"),   # duplicate B/L ignored
        ("ACME", "TUBE", 4, 2.0, "25030TJD9999-01"),
    ])

    grouped = group_sourcefile_by_client(filepath, bl_aggregated=True)

    ctp_row = grouped[grouped[COL_TYPE] == "CTP"].iloc[0]
    assert ctp_row[COL_BL] == "TJD0701-17 / TJD0101/01"   # shortened + aggregated
    assert ctp_row[COL_QUANTITE] == 6
    assert ctp_row[COL_TONAGE] == pytest.approx(11.0)

    tube_row = grouped[grouped[COL_TYPE] == "TUBE"].iloc[0]
    assert tube_row[COL_BL] == "TJD9999-01"


def test_grouping_without_bl_aggregation_keeps_first_bl(tmp_path):
    filepath = _write_source(tmp_path, [
        ("ACME", "CTP", 2, 4.5, "25030TJD0701-17"),
        ("ACME", "CTP", 3, 5.5, "25030TJD0101/01"),
    ])

    grouped = group_sourcefile_by_client(filepath, bl_aggregated=False)

    ctp_row = grouped[grouped[COL_TYPE] == "CTP"].iloc[0]
    assert ctp_row[COL_BL] == "TJD0701-17"


def test_grouped_output_follows_shared_commodity_order(tmp_path):
    filepath = _write_source(tmp_path, [
        ("ACME", "UNITS", 1, 1.0, "BL-U"),
        ("ACME", "PACKAGES", 1, 1.0, "BL-P"),
        ("ACME", "CORNIERE", 1, 1.0, "BL-C"),
        ("ACME", "POUTRELLE", 1, 1.0, "BL-PL"),
        ("ACME", "TUBE", 1, 1.0, "BL-T"),
        ("ACME", "BOBINE", 1, 1.0, "BL-B"),
        ("ACME", "CTP", 1, 1.0, "BL-CTP"),
        ("ACME", "UNITS + PACKAGES", 1, 1.0, "BL-UP"),
        ("ACME", "COLIS", 1, 1.0, "BL-CO"),
        ("ACME", "MDF", 1, 1.0, "BL-M"),
    ])

    grouped = group_sourcefile_by_client(filepath, bl_aggregated=True)
    out_types = list(grouped[COL_TYPE])

    # Exact chain for the specified commodities and the trailing buckets.
    assert out_types[:5] == ["CTP", "BOBINE", "TUBE", "POUTRELLE", "CORNIERE"]
    assert out_types[-3:] == ["UNITS + PACKAGES", "UNITS", "PACKAGES"]

    # COLIS stays its own structural commodity (not folded into PACKAGES),
    # i.e. it sorts before the generic buckets.
    assert "COLIS" in out_types
    assert out_types.index("COLIS") < out_types.index("UNITS + PACKAGES")

    # Priorities are non-decreasing across the whole output.
    priorities = [commodity_sort_priority(t) for t in out_types]
    assert priorities == sorted(priorities)


def test_equal_priority_groups_are_sorted_by_client(tmp_path):
    filepath = _write_source(tmp_path, [
        ("ZETA", "CORNIERE", 1, 1.0, "BL-Z"),
        ("ALPHA", "CORNIERE", 1, 1.0, "BL-A"),
    ])

    grouped = group_sourcefile_by_client(filepath, bl_aggregated=True)

    assert list(grouped[COL_CLIENT]) == ["ALPHA", "ZETA"]
