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
            
        # Row-level locking to prevent concurrent overwrite
        line = self.session.query(ManifestLine).filter_by(bl_code=bl_code).with_for_update().first()
        if not line:
            raise CargoDomainError(f"B/L {bl_code} not found in manifest.")
            
        remaining_to_land = line.manifested_qty - line.landed_qty
        if qty > remaining_to_land:
            raise CargoDomainError(f"Cannot land {qty}. Only {remaining_to_land} remaining.")
            
        line.landed_qty += qty
        
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
        return event

    def receive_cargo(self, bl_code: str, qty: float, tonnage: float, shift: str, operator_id: str) -> MovementEvent:
        if qty <= 0:
            raise CargoDomainError("Quantity must be greater than zero.")
            
        # Row-level locking
        line = self.session.query(ManifestLine).filter_by(bl_code=bl_code).with_for_update().first()
        if not line:
            raise CargoDomainError(f"B/L {bl_code} not found.")
            
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
        return event
