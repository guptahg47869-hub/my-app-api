from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import TIMESTAMP, String, Enum, Date, DateTime, ForeignKey, UniqueConstraint, Numeric
from sqlalchemy import Table, Column, Integer, func

from datetime import datetime, date
import enum
from .db import Base
from sqlalchemy.sql import func

# models.py
class Stage(str, enum.Enum):
    waxing = "waxing"
    metal_prep = "metal_prep"   # NEW
    supply = "supply"
    casting = "casting"
    quenching = "quenching"
    cutting = "cutting"
    reconciliation = "reconciliation"
    done = "done"

class TreeStatus(str, enum.Enum):
    transit = "transit"
    consumed = "consumed"

class Tree(Base):
    __tablename__ = "trees"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)  # type: ignore
    tree_no: Mapped[str] = mapped_column(String(32), nullable=False)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"), nullable=False)

    # NEW: capture at tree stage
    gasket_weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    total_weight:  Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)

    # Derived/stored
    tree_weight: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    est_metal_weight: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)

    status: Mapped[TreeStatus] = mapped_column(Enum(TreeStatus), default=TreeStatus.transit, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    posted_by: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (UniqueConstraint('tree_no', name='uq_tree_no'),)
    bags = relationship("Bag", secondary="tree_bags", back_populates="trees")


class Metal(Base):
    __tablename__ = "metals"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    scrap_reserves = relationship("ScrapReserve", back_populates="metal")

class Flask(Base):
    __tablename__ = "flasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date)  # type: ignore
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
    bags = relationship("Bag", secondary="flask_bags", back_populates="flasks")

class Bag(Base):
    __tablename__ = "bags"
    id = Column(Integer, primary_key=True)
    bag_no = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # backrefs populated below
    trees = relationship("Tree", secondary="tree_bags", back_populates="bags")
    flasks = relationship("Flask", secondary="flask_bags", back_populates="bags")

# association: trees<->bags (many-to-many)
tree_bags = Table(
    "tree_bags",
    Base.metadata,
    Column("tree_id", ForeignKey("trees.id", ondelete="CASCADE"), primary_key=True),
    Column("bag_id", ForeignKey("bags.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("tree_id", "bag_id", name="uq_tree_bag"),
)

# association: flasks<->bags (many-to-many)
flask_bags = Table(
    "flask_bags",
    Base.metadata,
    Column("flask_id", ForeignKey("flasks.id", ondelete="CASCADE"), primary_key=True),
    Column("bag_id", ForeignKey("bags.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("flask_id", "bag_id", name="uq_flask_bag"),
)


class WaxingEntry(Base):
    __tablename__ = "waxing_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    gasket_weight: Mapped[float] = mapped_column(Numeric(12, 3))
    tree_weight: Mapped[float] = mapped_column(Numeric(12, 3))
    metal_weight: Mapped[float] = mapped_column(Numeric(12, 3))
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask", back_populates="waxingentry")

# models.py
class MetalPrep(Base):
    __tablename__ = "metal_prep"
    id: Mapped[int] = mapped_column(primary_key=True)

    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    prepared: Mapped[bool] = mapped_column(default=False)           # prepared vs. not prepared

    # planned values saved at prep time (for gold use fine+alloy; for Pt/Ag use pure)
    scrap_planned: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    fine_24k_planned: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    alloy_planned: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    pure_planned: Mapped[float] = mapped_column(Numeric(12, 3), default=0)

    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask")


class Supply(Base):
    __tablename__ = "metal_supply"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    required_metal_weight: Mapped[float] = mapped_column(Numeric(12, 3))
    scrap_supplied: Mapped[float] = mapped_column(Numeric(12, 3))
    fine_24k_supplied: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    alloy_supplied: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    fresh_supplied: Mapped[float] = mapped_column(Numeric(12, 3), default=0)
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))
    flask = relationship("Flask")

class Casting(Base):
    __tablename__ = "casting"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)
    casting_temp: Mapped[float] = mapped_column(Numeric(8, 2))
    oven_temp: Mapped[float] = mapped_column(Numeric(8, 2))
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
    before_cut_A: Mapped[float] = mapped_column(Numeric(12, 3))
    after_scrap_B: Mapped[float] = mapped_column(Numeric(12, 3))
    after_casting_C: Mapped[float] = mapped_column(Numeric(12, 3))
    loss: Mapped[float] = mapped_column(Numeric(12, 3))
    posted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    posted_by: Mapped[str] = mapped_column(String(64))

    flask = relationship("Flask", back_populates="cutting_rel")

class ScrapReserve(Base):
    __tablename__ = "scrap_reserves"
    id: Mapped[int] = mapped_column(primary_key=True)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"), unique=True)
    qty_on_hand: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    metal = relationship("Metal", back_populates="scrap_reserves")

class ScrapMovement(Base):
    __tablename__ = "scrap_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    metal_id: Mapped[int] = mapped_column(ForeignKey("metals.id"))
    flask_id: Mapped[int | None]
    delta: Mapped[float] = mapped_column(Numeric(12, 3))
    source: Mapped[str] = mapped_column(String(32))  # supply.consume / cutting.add
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(64))

class Reconciliation(Base):
    __tablename__ = "reconciliation"
    id: Mapped[int] = mapped_column(primary_key=True)
    flask_id: Mapped[int] = mapped_column(ForeignKey("flasks.id"), unique=True)

    # values captured at Cutting (can be edited at Recon)
    supplied_weight: Mapped[Decimal]     = mapped_column(Numeric(12,3), nullable=False)
    before_cut_weight: Mapped[Decimal]   = mapped_column(Numeric(12,3), nullable=False)
    after_cast_weight: Mapped[Decimal]   = mapped_column(Numeric(12,3), nullable=False)
    after_scrap_weight: Mapped[Decimal]  = mapped_column(Numeric(12,3), nullable=False)

    # derived preview saved for convenience (optional)
    loss_part_i: Mapped[Decimal]         = mapped_column(Numeric(12,3), nullable=False)   # supplied - before_cut
    loss_part_ii: Mapped[Decimal]        = mapped_column(Numeric(12,3), nullable=False)   # before_cut - (after_cast+after_scrap)
    loss_total: Mapped[Decimal]          = mapped_column(Numeric(12,3), nullable=False)   # supplied - after_cast - after_scrap

    notes: Mapped[str | None]            = mapped_column(String(256))
    posted_by: Mapped[str]               = mapped_column(String(64))
    created_at: Mapped[datetime]         = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime]         = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    flask = relationship("Flask")
