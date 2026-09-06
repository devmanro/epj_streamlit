import pytest

from tools.tools import (
    _compute_commodity_and_received_lines,
    computecommodity_and_received_lines,
)


def _call(raw_commodity, rec_str="05"):
    return computecommodity_and_received_lines(raw_commodity, rec_str)


@pytest.mark.parametrize(
    "raw_commodity, expected_commodity",
    [
        # Big bags / bulk bagged raw materials
        ("BIG BAG", "BIG BAGS"),
        ("BAG", "BIG BAGS"),
        ("BIG BAGS", "BIG BAGS"),
        ("CALCINED", "BIG BAGS"),
        ("ANTHRACITE COAL", "BIG BAGS"),
        ("COAL", "BIG BAGS"),
        # Wood / panel products (crate-style lines)
        ("MDF", "MDF"),
        ("CTP", "CTP"),
        ("PLYWOOD", "PLYWOOD"),
        ("FFP", "FFP"),
        ("MDF + PLYWOOD", "MDF + PLYWOOD"),
        ("FILM FACED", "FILM FACED"),
        ("FILM", "FILM"),
        # Steel products
        ("PIPE", "TUBES"),
        ("TUBE", "TUBES"),
        ("STEEL PIPE", "TUBES"),
        ("BEAMS", "Bundles of BEAMS"),
        ("STEEL H-BEAM", "Bundles of BEAMS"),
        ("METAL SHEET", "Bundles of METAL SHEET"),
        ("TOLE", "Bundles of METAL SHEET"),
        ("FORMWORK", "Bundles of formwork"),
        ("STEEL MOULDS", "Bundles of formwork"),
        ("FIL M", "FIL MACHINE"),
        ("FIL MACHINE", "FIL MACHINE"),
        ("STEEL WIRE", "FIL MACHINE"),
        ("COIL", "COILS"),
        ("BOBINE", "COILS"),
        ("BOB", "COILS"),
        # General-cargo product families
        ("COLIS", "COLIS"),
        ("POUTRELLE", "POUTRELLES"),
        ("POUTRELLE FORTE EPESSEUR", "POUTRELLES"),
        ("CORNIERE", "CORNIERES"),
        ("CORNIERE 12 M", "CORNIERES"),
        # Lumber
        ("WHITE WOOD", "BUNDLES"),
        ("BEECH WOOD", "BUNDLES"),
        ("RED WOOD", "BUNDLES"),
        # Unit cargo
        ("BUS", "Unit"),
        ("MINI BUS", "Unit"),
        ("CAMION POMPE A BETON", "Unit"),
        ("REMORQUES", "Unit"),
        ("EXCAVATEUR", "Unit"),
        ("DUMP TRUCK", "Unit"),
        # Package cargo
        ("WELDING MACHINE", "package"),
        ("SPARE PARTS", "package"),
        # Unknown / empty
        ("RANDOM UNKNOWN", "RANDOM UNKNOWN"),
        ("", "General Cargo"),
        (None, "General Cargo"),
    ],
)
def test_commodity_mapping(raw_commodity, expected_commodity):
    commodity, received_lines, total_rec_str = _call(raw_commodity)

    assert commodity == expected_commodity
    assert isinstance(received_lines, list)
    assert received_lines
    assert total_rec_str.startswith("05")


def test_signature_and_return_structure_preserved():
    result = _call("MDF", "03")
    assert len(result) == 3
    assert result[0] == "MDF"
    assert result[1][0] == "Crates of MDF Found Dismembered on board"
    assert result[2] == "03  Crates of MDF"


def test_big_bags_received_lines():
    _, received_lines, total = _call("BIG BAG", "05")
    assert received_lines == [
        "BIG BAGS FOUND TORN ON BOARD",
        "BIG BAGS FOUND BROKEN ON BOARD",
        "EMPTY BAG ON BOARD",
    ]
    assert total == "05  Big Bags"


def test_tubes_received_lines_preserve_period():
    _, received_lines, total = _call("PIPE", "05")
    assert received_lines == ["TUBES.", "TUBES Damaged on board"]
    assert total == "05  TUBES"


def test_unit_received_lines():
    _, received_lines, total = _call("BUS", "05")
    assert received_lines == ["Unit", "Unit Damaged on board"]
    assert total == "05  Units"


def test_unknown_received_lines():
    _, received_lines, total = _call("RANDOM UNKNOWN", "05")
    assert received_lines == ["Packaging damaged on board"]
    assert total == "05  RANDOM UNKNOWN"


def test_empty_cell_does_not_match_unit_or_package():
    # Regression: Python treats '' as a substring of every constant, which
    # used to misclassify empty cells as "Units + Package".
    commodity, _, total = _call("", "05")
    assert commodity == "General Cargo"
    assert total == "05  General Cargo"
