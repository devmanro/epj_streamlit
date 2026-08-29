import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.services import CargoService, CargoDomainError
from infrastructure.database.models import ManifestLine, MovementEvent, Vessel

# ── Existing tests (unchanged logic) ─────────────────────────────────────────

def test_land_cargo_success(db_session, seed_data):
    service = CargoService(db_session)
    event = service.land_cargo("BL123", qty=50.0, tonnage=10.0, shift="MATIN", operator_id="user1")

    # Needs explicit commit as service no longer commits
    db_session.commit()

    assert event.quantity == 50.0
    assert event.event_type.value == "LANDED"
    assert seed_data.landed_qty == 50.0

def test_nonexistent_bl(db_session):
    service = CargoService(db_session)
    with pytest.raises(CargoDomainError, match="B/L BAD_BL not found"):
        service.land_cargo("BAD_BL", qty=10.0, tonnage=0.0, shift="MATIN", operator_id="user1")

def test_zero_or_negative_quantity(db_session, seed_data):
    service = CargoService(db_session)
    with pytest.raises(CargoDomainError, match="Quantity must be greater than zero"):
        service.land_cargo("BL123", qty=-5.0, tonnage=0.0, shift="MATIN", operator_id="user1")

def test_land_cargo_exceeds_manifest(db_session, seed_data):
    service = CargoService(db_session)
    with pytest.raises(CargoDomainError, match="Cannot land 150.0"):
        service.land_cargo("BL123", qty=150.0, tonnage=20.0, shift="MATIN", operator_id="test_user")

def test_receive_cargo_exceeds_landed(db_session, seed_data):
    service = CargoService(db_session)
    service.land_cargo("BL123", qty=50.0, tonnage=10.0, shift="MATIN", operator_id="test_user")
    db_session.commit()

    with pytest.raises(CargoDomainError, match="Cannot receive 60.0"):
        service.receive_cargo("BL123", qty=60.0, tonnage=10.0, shift="MATIN", operator_id="test_user")

def test_end_to_end_cycle(db_session, seed_data):
    service = CargoService(db_session)

    # 1. Land 40
    ev1 = service.land_cargo("BL123", qty=40.0, tonnage=5.0, shift="MATIN", operator_id="user1")
    db_session.commit()

    # 2. Receive 30
    ev2 = service.receive_cargo("BL123", qty=30.0, tonnage=3.0, shift="SOIR", operator_id="user2")
    db_session.commit()

    assert seed_data.landed_qty == 40.0
    assert seed_data.received_qty == 30.0

    # 3. Check Audit Logs
    events = db_session.query(MovementEvent).order_by(MovementEvent.id).all()
    assert len(events) == 2
    assert events[0].event_type.value == "LANDED"
    assert events[1].event_type.value == "RECEIVED"

# ── New tests for real manifest fields ───────────────────────────────────────

def test_seed_data_has_real_fields(db_session, seed_data):
    """Verify that the new manifest fields are stored and retrieved correctly."""
    line = db_session.query(ManifestLine).filter_by(bl_code="BL123").first()
    assert line.modele == "TOYOTA HILUX"
    assert line.produit == "VEHICULE"
    assert line.chassis_serial == "CHASS-XYZ-001"
    assert line.situation == "EN ATTENTE"
    # assert line.type == "VEHICULE"
    assert line.cargo_type == "RORO"

def test_vessel_has_escale_and_imo(db_session, seed_vessel_with_escale):
    """Verify that Vessel stores escale and IMO correctly."""
    v = db_session.query(Vessel).filter_by(name="MSC CARGO").first()
    assert v.escale == "ESC-2024-001"
    assert v.imo == "IMO1234567"

def test_land_cargo_with_full_manifest_data(db_session, seed_data):
    """Landing cargo should work correctly regardless of new optional fields."""
    service = CargoService(db_session)
    event = service.land_cargo("BL123", qty=80.0, tonnage=15.0, shift="NUIT", operator_id="op-42")
    db_session.commit()
    assert event.quantity == 80.0
    assert seed_data.landed_qty == 80.0
    # remaining should be correct
    assert seed_data.manifested_qty - seed_data.landed_qty == 20.0
