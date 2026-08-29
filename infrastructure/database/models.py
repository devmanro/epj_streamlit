from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, synonym
from datetime import datetime, timezone
import enum

Base = declarative_base()

class EventType(str, enum.Enum):
    LANDED = "LANDED"
    RECEIVED = "RECEIVED"

class Vessel(Base):
    __tablename__ = 'vessels'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    escale = Column(String, nullable=True)          # ESCALE — call/stopover reference
    imo = Column(String, nullable=True)             # IMO_NAVIRE
    arrival_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    manifest_lines = relationship("ManifestLine", back_populates="vessel", cascade="all, delete-orphan")

class ManifestLine(Base):
    __tablename__ = 'manifest_lines'

    id = Column(Integer, primary_key=True, autoincrement=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id'), nullable=False)

    # Core identification
    bl_code = Column(String, nullable=False, index=True)  # B/L
    article = Column(String, nullable=True)               # ARTICLE
    client = Column(String, nullable=True)                # CLIENT
    designation = Column(String, nullable=True)           # DESIGNATION

    # Classification
    produit = Column(String, nullable=True)               # PRODUIT
    modele = Column(String, nullable=True)                # MODELE
    type_ = Column(String, String, nullable=True)         # TYPE (conditionnement)
    cargo_type = Column(String, nullable=True)            # CARGO_TYPE (manifest category)
    chassis_serial = Column(String, nullable=True)        # CHASSIS/SERIAL

    

    # Quantities
    manifested_qty = Column(Float, default=0.0)           # QUANTITE
    manifested_tonnage = Column(Float, default=0.0)       # TONAGE
    landed_qty = Column(Float, default=0.0)
    received_qty = Column(Float, default=0.0)
    reste_tp = Column(Float, default=0.0)                 # RESTE T/P
    surface = Column(Float, default=0.0)                  # SURFACE

    # Operational fields
    situation = Column(String, nullable=True)             # SITUATION
    observation = Column(String, nullable=True)           # OBSERVATION
    position = Column(String, nullable=True)              # POSITION
    transit = Column(String, nullable=True)               # TRANSIT
    cles = Column(String, nullable=True)                  # CLES
    daemo_breaker_type = Column(String, nullable=True)    # DAEMO BREAKER (DRB) TOP BOX TYPE

    # Dates
    manifested_date = Column(DateTime, nullable=True)     # DATE
    date_enlevement = Column(DateTime, nullable=True)     # DATE ENLEV

    # Optimistic Locking
    version = Column(Integer, default=1, nullable=False)

    vessel = relationship("Vessel", back_populates="manifest_lines")
    movements = relationship("MovementEvent", back_populates="manifest_line", cascade="all, delete-orphan")

    # Removed UniqueConstraint('vessel_id', 'bl_code') to allow multiple chassis/items per B/L

    __mapper_args__ = {
        "version_id_col": version
    }

class MovementEvent(Base):
    __tablename__ = 'movement_events'

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_line_id = Column(Integer, ForeignKey('manifest_lines.id'), nullable=False)
    event_type = Column(Enum(EventType), nullable=False)
    quantity = Column(Float, nullable=False)
    tonnage = Column(Float, default=0.0)

    operator_id = Column(String, nullable=True)
    shift = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    remarks = Column(String, nullable=True)

    manifest_line = relationship("ManifestLine", back_populates="movements")
