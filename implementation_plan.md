# Phase 0 & 1: Core Domain and Database Migration Plan

This plan details the foundational changes needed to migrate from Excel-based state management to a robust SQL backend using a Clean Architecture approach.

## User Review Required

> [!IMPORTANT]  
> Please review the provided code structures below. If this looks good, click **Proceed** and I will officially set this as our blueprint for Phase 0.

---

## 1. SQLAlchemy ORM Models (`infrastructure/database/models.py`)

We will define three core tables: `Vessel`, `ManifestLine` (the cargo), and `MovementEvent` (the audit log of operations).

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class EventType(str, enum.Enum):
    LANDED = "LANDED"
    RECEIVED = "RECEIVED"

class Vessel(Base):
    __tablename__ = 'vessels'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    arrival_date = Column(DateTime, default=datetime.utcnow)
    
    manifest_lines = relationship("ManifestLine", back_populates="vessel", cascade="all, delete-orphan")

class ManifestLine(Base):
    __tablename__ = 'manifest_lines'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vessel_id = Column(Integer, ForeignKey('vessels.id'), nullable=False)
    bl_code = Column(String, nullable=False, index=True)
    client = Column(String, nullable=True)
    designation = Column(String, nullable=True)
    cargo_type = Column(String, nullable=True)
    
    # Quantities
    manifested_qty = Column(Float, default=0.0)
    manifested_tonnage = Column(Float, default=0.0)
    
    landed_qty = Column(Float, default=0.0)
    received_qty = Column(Float, default=0.0)
    
    vessel = relationship("Vessel", back_populates="manifest_lines")
    movements = relationship("MovementEvent", back_populates="manifest_line", cascade="all, delete-orphan")

class MovementEvent(Base):
    __tablename__ = 'movement_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_line_id = Column(Integer, ForeignKey('manifest_lines.id'), nullable=False)
    event_type = Column(Enum(EventType), nullable=False)
    quantity = Column(Float, nullable=False)
    tonnage = Column(Float, default=0.0)
    
    operator_id = Column(String, nullable=True) # For future Auth
    shift = Column(String, nullable=True)       # MATIN, SOIR, NUIT
    timestamp = Column(DateTime, default=datetime.utcnow)
    remarks = Column(String, nullable=True)
    
    manifest_line = relationship("ManifestLine", back_populates="movements")
```

---

## 2. Data Migration Script (`scripts/migrate_manifest.py`)

This script reads the existing `manifest_source.xlsx` and populates the new SQLite database.

```python
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from infrastructure.database.models import Base, Vessel, ManifestLine

DB_URL = "sqlite:///database.sqlite"

def run_migration(excel_path: str):
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        df = pd.read_excel(excel_path)
        
        # 1. Extract Unique Vessels
        navire_col = 'NAVIRE' if 'NAVIRE' in df.columns else df.columns[0]
        unique_vessels = df[navire_col].dropna().unique()
        
        vessel_map = {}
        for v_name in unique_vessels:
            vessel = Vessel(name=str(v_name).strip())
            session.add(vessel)
            session.flush() # Get the ID
            vessel_map[v_name] = vessel.id
            
        # 2. Populate Manifest Lines
        for _, row in df.iterrows():
            v_name = row.get(navire_col)
            if pd.isna(v_name): continue
            
            manifest_line = ManifestLine(
                vessel_id=vessel_map[v_name],
                bl_code=str(row.get('B/L', 'UNKNOWN')).strip(),
                client=str(row.get('CLIENT', '')).strip(),
                designation=str(row.get('DESIGNATION', '')).strip(),
                cargo_type=str(row.get('TYPE', '')).strip(),
                manifested_qty=float(row.get('QUANTITE', 0.0) or 0.0),
                manifested_tonnage=float(row.get('TONAGE', 0.0) or 0.0),
                landed_qty=0.0,
                received_qty=0.0
            )
            session.add(manifest_line)
            
        session.commit()
        print("Migration successful!")
    except Exception as e:
        session.rollback()
        print(f"Migration failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    run_migration("manifest_source.xlsx")
```

---

## 3. Cargo Service (`core/cargo_tracking/cargo_service.py`)

This handles business rules, enforcing that you cannot remove more cargo than what exists.

```python
from sqlalchemy.orm import Session
from infrastructure.database.models import ManifestLine, MovementEvent, EventType

class CargoDomainError(Exception):
    pass

class CargoService:
    def __init__(self, session: Session):
        self.session = session
        
    def land_cargo(self, bl_code: str, qty: float, tonnage: float, shift: str, operator_id: str) -> MovementEvent:
        if qty <= 0:
            raise CargoDomainError("Quantity must be greater than zero.")
            
        line = self.session.query(ManifestLine).filter_by(bl_code=bl_code).first()
        if not line:
            raise CargoDomainError(f"B/L {bl_code} not found in manifest.")
            
        # Business Rule: Cannot land more than manifested
        remaining_to_land = line.manifested_qty - line.landed_qty
        if qty > remaining_to_land:
            raise CargoDomainError(f"Cannot land {qty}. Only {remaining_to_land} remaining.")
            
        # Update Aggregate
        line.landed_qty += qty
        
        # Create Event
        event = MovementEvent(
            manifest_line_id=line.id,
            event_type=EventType.LANDED,
            quantity=qty,
            tonnage=tonnage,
            shift=shift,
            operator_id=operator_id,
            remarks=f"Landed {qty} units."
        )
        self.session.add(event)
        self.session.commit()
        
        return event

    def receive_cargo(self, bl_code: str, qty: float, tonnage: float, shift: str, operator_id: str) -> MovementEvent:
        if qty <= 0:
            raise CargoDomainError("Quantity must be greater than zero.")
            
        line = self.session.query(ManifestLine).filter_by(bl_code=bl_code).first()
        if not line:
            raise CargoDomainError(f"B/L {bl_code} not found.")
            
        # Business Rule: Cannot receive (remove from port) more than what has been landed
        available_on_port = line.landed_qty - line.received_qty
        if qty > available_on_port:
            raise CargoDomainError(f"Cannot receive {qty}. Only {available_on_port} landed and available on port.")
            
        line.received_qty += qty
        
        event = MovementEvent(
            manifest_line_id=line.id,
            event_type=EventType.RECEIVED,
            quantity=qty,
            tonnage=tonnage,
            shift=shift,
            operator_id=operator_id,
            remarks=f"Received {qty} units."
        )
        self.session.add(event)
        self.session.commit()
        
        return event
```

---

## 4. `st.session_state` Architecture

In the new architecture, Streamlit should **not** hold business data (like DataFrames of logs) in `session_state`. It should only hold **UI View State**.

*   **DON'T DO THIS**: `st.session_state.pending_ops_df = pd.DataFrame(...)`
*   **DO THIS**: 
    1. Streamlit forms capture user input.
    2. Streamlit calls `CargoService.land_cargo()`.
    3. The service updates the database.
    4. Streamlit queries the database (via a read repository) to refresh the view.

**What stays in `session_state`?**
*   `st.session_state.current_user`: The logged-in operator ID.
*   `st.session_state.selected_vessel_id`: The ID of the vessel currently selected in a dropdown.
*   `st.session_state.active_tab`: Which tab the user is looking at.

```python
# Example UI file: ui/pages/tracking.py
import streamlit as st
from infrastructure.database.session import get_session
from core.cargo_tracking.cargo_service import CargoService, CargoDomainError

def render_tracking():
    st.title("Cargo Tracking")
    
    # Only keep UI selection state
    if "selected_bl" not in st.session_state:
        st.session_state.selected_bl = None
        
    db_session = get_session()
    service = CargoService(db_session)
    
    with st.form("landing_form"):
        bl = st.text_input("B/L Code")
        qty = st.number_input("Quantity", min_value=1.0)
        submitted = st.form_submit_button("Land Cargo")
        
        if submitted:
            try:
                service.land_cargo(bl, qty, tonnage=0.0, shift="MATIN", operator_id="admin")
                st.success(f"Successfully landed {qty} for {bl}!")
            except CargoDomainError as e:
                st.error(str(e))
```

---

## 5. Pytest Fixtures (`tests/conftest.py` & `tests/test_cargo_service.py`)

Testing the `CargoService` with an in-memory SQLite database ensures business rules work perfectly without touching the file system.

**`tests/conftest.py`**
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from infrastructure.database.models import Base, Vessel, ManifestLine

@pytest.fixture
def db_session():
    # Use an in-memory SQLite database for fast, isolated tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()

@pytest.fixture
def seed_data(db_session):
    # Setup test vessel and manifest
    vessel = Vessel(name="MSC TEST")
    db_session.add(vessel)
    db_session.commit()
    
    manifest_line = ManifestLine(
        vessel_id=vessel.id,
        bl_code="BL123",
        manifested_qty=100.0,
        landed_qty=0.0,
        received_qty=0.0
    )
    db_session.add(manifest_line)
    db_session.commit()
    
    return manifest_line
```

**`tests/test_cargo_service.py`**
```python
import pytest
from core.cargo_tracking.cargo_service import CargoService, CargoDomainError

def test_land_cargo_success(db_session, seed_data):
    service = CargoService(db_session)
    
    # Act
    event = service.land_cargo("BL123", qty=50.0, tonnage=10.0, shift="MATIN", operator_id="test_user")
    
    # Assert
    assert event.quantity == 50.0
    assert seed_data.landed_qty == 50.0

def test_land_cargo_exceeds_manifest(db_session, seed_data):
    service = CargoService(db_session)
    
    # Attempt to land 150 when only 100 manifested
    with pytest.raises(CargoDomainError, match="Cannot land 150.0"):
        service.land_cargo("BL123", qty=150.0, tonnage=20.0, shift="MATIN", operator_id="test_user")

def test_receive_cargo_exceeds_landed(db_session, seed_data):
    service = CargoService(db_session)
    
    # Land 50 first
    service.land_cargo("BL123", qty=50.0, tonnage=10.0, shift="MATIN", operator_id="test_user")
    
    # Attempt to receive 60 (only 50 landed on port)
    with pytest.raises(CargoDomainError, match="Cannot receive 60.0. Only 50.0 landed"):
        service.receive_cargo("BL123", qty=60.0, tonnage=10.0, shift="MATIN", operator_id="test_user")
```
