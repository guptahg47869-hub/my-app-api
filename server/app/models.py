from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import TIMESTAMP, String, Enum, Date, DateTime, ForeignKey, UniqueConstraint, Numeric
from datetime import datetime, date
import enum
from .db import Base
from sqlalchemy.sql import func


class Stage(str, enum.Enum):
    waxing = "waxing"
    supply = "supply"
    casting = "casting"
    quenching = "quenching"
    cutting = "cutting"
    done = "done"

class TreeStatus(str, enum.Enum):
    transit = "transit"
    consumed = "consumed"

class Tree(Base):
    __tablename__ = "trees"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False) # type: ignore
    tree_no: Mapped[str] = mapped_column(String(32), nullable=False)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"), nullable=False)

    tree_weight: Mapped[Decimal] = mapped_column(Numeric(12,3), nullable=False)
    est_metal_weight: Mapped[Decimal] = mapped_column(Numeric(12,3), nullable=False)

    status: Mapped[TreeStatus] = mapped_column(Enum(TreeStatus), default=TreeStatus.transit, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    posted_by: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("date", "tree_no", name="uq_date_tree_no"),
    )

class Metal(Base):
    __tablename__ = "metals"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    scrap_reserves = relationship("ScrapReserve", back_populates="metal")

class Flask(Base):
    __tablename__ = "flasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date) # type: ignore
    flask_no: Mapped[str] = mapped_column(String(32))
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"))
    status: Mapped[Stage] = mapped_column(Enum(Stage), default=Stage.waxing)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tree_id: Mapped[Optional[int]] = mapped_column(ForeignKey("trees.id"), nullable=True)
    
    metal = relationship("Metal")
    __table_args__ = (UniqueConstraint("date", "flask_no", name="uq_date_flask"),)
    waxingentry = relationship("WaxingEntry", uselist=False, back_populates="flask")
    casting = relationship("Casting", uselist=False, back_populates="flask")
    quenching_rel = relationship("Quenching", uselist=False, back_populates="flask")
    cutting_rel = relationship("Cutting", uselist=False, back_populates="flask")

class WaxingEntry(Base):
    __tablename__ = "waxing_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    gasket_weight: Mapped[float] = mapped_column(Numeric(12,3))
    tree_weight: Mapped[float] = mapped_column(Numeric(12,3))
    metal_weight: Mapped[float] = mapped_column(Numeric(12,3))
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask", back_populates="waxingentry")  

class Supply(Base):
    __tablename__ = "metal_supply"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    required_metal_weight: Mapped[float] = mapped_column(Numeric(12,3))
    scrap_supplied: Mapped[float] = mapped_column(Numeric(12,3))
    fresh_supplied: Mapped[float] = mapped_column(Numeric(12,3))
    fine_24k_supplied: Mapped[float] = mapped_column(Numeric(12,3), default=0)
    alloy_supplied: Mapped[float] = mapped_column(Numeric(12,3), default=0)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))
    flask = relationship("Flask")

class Casting(Base):
    __tablename__ = "casting"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    casting_temp: Mapped[float] = mapped_column(Numeric(8,2))
    oven_temp: Mapped[float] = mapped_column(Numeric(8,2))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask", back_populates="casting")

class Quenching(Base):
    __tablename__ = "quenching"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    quenching_time_min: Mapped[int] = mapped_column()
    ready_at: Mapped[datetime] = mapped_column(DateTime)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask", back_populates="quenching_rel")

class Cutting(Base):
    __tablename__ = "cutting"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    before_cut_A: Mapped[float] = mapped_column(Numeric(12,3))
    after_scrap_B: Mapped[float] = mapped_column(Numeric(12,3))
    after_casting_C: Mapped[float] = mapped_column(Numeric(12,3))
    loss: Mapped[float] = mapped_column(Numeric(12,3))
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask", back_populates="cutting_rel")

class ScrapReserve(Base):
    __tablename__ = "scrap_reserves"
    id: Mapped[int] = mapped_column(primary_key=True)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"), unique=True)
    qty_on_hand: Mapped[float] = mapped_column(Numeric(14,3), default=0)
    metal = relationship("Metal", back_populates="scrap_reserves")

class ScrapMovement(Base):
    __tablename__ = "scrap_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"))
    flask_id: Mapped[int | None]
    delta: Mapped[float] = mapped_column(Numeric(12,3))
    source: Mapped[str] = mapped_column(String(32))  # supply.consume / cutting.add
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(64))
