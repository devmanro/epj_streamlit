"""
infrastructure/database/models.py
────────────────────────────────────
ORM models for the Supabase PostgreSQL database.

Tables
------
  vessels        — one row per vessel call
  manifest_lines — one row per cargo line (FK → vessels)
"""

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime,
    Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from infrastructure.database.session import Base


# ─────────────────────────────────────────────────────────────────────────────
#  Vessel
# ─────────────────────────────────────────────────────────────────────────────

class Vessel(Base):
    __tablename__ = "vessels"

    id           = Column(BigInteger, primary_key=True, autoincrement=True)
    name         = Column(String(255),  nullable=False, index=True)
    escale       = Column(String(100),  nullable=True)
    imo          = Column(String(20),   nullable=True)
    arrival_date = Column(DateTime(timezone=True), nullable=True,
                          default=lambda: datetime.now(timezone.utc))
    created_at   = Column(DateTime(timezone=True), nullable=False,
                          default=lambda: datetime.now(timezone.utc))

    manifest_lines = relationship(
        "ManifestLine",
        back_populates="vessel",
        cascade="all, delete-orphan",
        lazy="dynamic",          # avoids loading all lines on vessel query
    )

    __table_args__ = (
        # A vessel is uniquely identified by name + escale combination
        UniqueConstraint("name", "escale", name="uq_vessel_name_escale"),
    )

    def __repr__(self):
        return f"<Vessel id={self.id} name={self.name!r} escale={self.escale!r}>"


# ─────────────────────────────────────────────────────────────────────────────
#  ManifestLine
# ─────────────────────────────────────────────────────────────────────────────

class ManifestLine(Base):
    __tablename__ = "manifest_lines"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    vessel_id  = Column(
        BigInteger,
        ForeignKey("vessels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Core cargo fields ─────────────────────────────────────────────────
    bl_code             = Column(String(100),  nullable=True,  index=True)
    article             = Column(String(255),  nullable=True)
    client              = Column(String(255),  nullable=True)
    designation         = Column(Text,         nullable=True)
    produit             = Column(String(255),  nullable=True)
    modele              = Column(String(255),  nullable=True)
    type_               = Column("type", String(100), nullable=True)
    cargo_type          = Column(String(100),  nullable=True)
    chassis_serial      = Column(String(255),  nullable=True)

    # ── Quantities / weights ──────────────────────────────────────────────
    manifested_qty      = Column(Float, nullable=True, default=0.0)
    manifested_tonnage  = Column(Float, nullable=True, default=0.0)
    reste_tp            = Column(Float, nullable=True, default=0.0)
    surface             = Column(Float, nullable=True, default=0.0)

    # ── Operational fields ────────────────────────────────────────────────
    situation           = Column(String(255),  nullable=True)
    observation         = Column(Text,         nullable=True)
    position            = Column(String(100),  nullable=True)
    transit             = Column(String(100),  nullable=True)
    cles                = Column(String(100),  nullable=True)
    daemo_breaker_type  = Column(String(255),  nullable=True)

    # ── Dates ─────────────────────────────────────────────────────────────
    manifested_date     = Column(DateTime(timezone=True), nullable=True)
    date_enlevement     = Column(DateTime(timezone=True), nullable=True)

    # ── Landing / receiving counters ──────────────────────────────────────
    landed_qty          = Column(Float,   nullable=True, default=0.0)
    received_qty        = Column(Float,   nullable=True, default=0.0)
    is_fully_delivered  = Column(Boolean, nullable=True, default=False)

    # ── Audit ─────────────────────────────────────────────────────────────
    created_at  = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at  = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )

    vessel = relationship("Vessel", back_populates="manifest_lines")

    __table_args__ = (
        # Prevent exact duplicates (same vessel + BL + chassis + article)
        UniqueConstraint(
            "vessel_id", "bl_code", "chassis_serial", "article",
            name="uq_manifest_line_identity",
        ),
        # Composite index for the most common filter pattern
        Index("ix_manifest_vessel_bl", "vessel_id", "bl_code"),
    )

    def __repr__(self):
        return (
            f"<ManifestLine id={self.id} bl={self.bl_code!r} "
            f"client={self.client!r} qty={self.manifested_qty}>"
        )
