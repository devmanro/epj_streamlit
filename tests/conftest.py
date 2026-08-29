import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.database.models import Base, Vessel, ManifestLine

@pytest.fixture
def engine():
    _engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(_engine)
    return _engine

@pytest.fixture
def db_session(engine):
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture
def seed_data(db_session):
    vessel = Vessel(name="MSC TEST")
    db_session.add(vessel)
    db_session.commit()

    manifest_line = ManifestLine(
        vessel_id       = vessel.id,
        bl_code         = "BL123",
        manifested_qty  = 100.0,
        landed_qty      = 0.0,
        received_qty    = 0.0,
        # Real manifest fields
        article         = "ART-001",
        modele          = "TOYOTA HILUX",
        produit         = "VEHICULE",
        chassis_serial  = "CHASS-XYZ-001",
        situation       = "EN ATTENTE",
        type_           = "VEHICULE",
        cargo_type      = "RORO",
    )
    db_session.add(manifest_line)
    db_session.commit()
    return manifest_line

@pytest.fixture
def seed_vessel_with_escale(db_session):
    vessel = Vessel(
        name   = "MSC CARGO",
        escale = "ESC-2024-001",
        imo    = "IMO1234567",
    )
    db_session.add(vessel)
    db_session.commit()
    return vessel
