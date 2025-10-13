from pydantic import BaseModel, condecimal, field_validator, Field, ValidationError, model_validator, confloat
from datetime import date
from decimal import Decimal
from typing import List


# ---------- Trees ----------
class TreeCreate(BaseModel):
    date: date
    tree_no: str
    metal_id: int

    # NEW: capture at tree stage (optional but preferred)
    gasket_weight: condecimal(max_digits=12, decimal_places=3, ge=0) | None = None  # type: ignore
    total_weight:  condecimal(max_digits=12, decimal_places=3, ge=0) | None = None  # type: ignore

    # Back-compat: allow explicit tree_weight if legacy UI still sends it
    tree_weight: condecimal(max_digits=12, decimal_places=3, ge=0) | None = None  # type: ignore

    posted_by: str

    bag_nos: List[str] = []

    @model_validator(mode="after")
    def ensure_weights(self):
        # Accept either explicit tree_weight or both gasket+total
        if self.tree_weight is not None:
            return self
        if self.gasket_weight is not None and self.total_weight is not None:
            if self.total_weight < self.gasket_weight:
                raise ValueError("total_weight must be >= gasket_weight")
            # Derive tree_weight for server-side use
            object.__setattr__(self, "tree_weight", (self.total_weight - self.gasket_weight))  # pydantic v2 pattern
            return self
        raise ValidationError(
            "Provide either tree_weight OR both gasket_weight and total_weight."
        )

class TreeOut(BaseModel):
    id: int
    date: date
    tree_no: str
    metal_id: int
    metal_name: str
    # NEW: expose captured values (may be null if created via legacy flow)
    gasket_weight: condecimal(max_digits=12, decimal_places=3) | None = None  # type: ignore
    total_weight:  condecimal(max_digits=12, decimal_places=3) | None = None  # type: ignore

    tree_weight: condecimal(max_digits=12, decimal_places=3)  # type: ignore
    est_metal_weight: condecimal(max_digits=12, decimal_places=3)  # type: ignore
    status: str

    bag_nos: List[str] = []

    class Config:
        from_attributes = True

# ---------- Waxing ----------
class PostFlaskFromTree(BaseModel):
    tree_id: int
    flask_no: str
    date: date
    gasket_weight: condecimal(max_digits=12, decimal_places=3, ge=0)  # type: ignore
    total_weight: condecimal(max_digits=12, decimal_places=3, ge=0)   # type: ignore
    posted_by: str

class WaxingCreate(BaseModel):
    date: date
    flask_no: str
    metal_id: int
    gasket_weight: float
    tree_weight: float
    posted_by: str

    @field_validator("gasket_weight", "tree_weight")
    @classmethod
    def nonneg(cls, v):
        if v < 0:
            raise ValueError("weight must be >= 0")
        return v
    
# ---------- Metal Prep ----------
class PrepCreate(BaseModel):
    flask_id: int
    prepared: bool = True
    scrap_planned: float = 0.0
    fine_24k_planned: float = 0.0
    alloy_planned: float = 0.0
    pure_planned: float = 0.0
    posted_by: str

class PrepOut(BaseModel):
    flask_id: int
    prepared: bool
    scrap_planned: float
    fine_24k_planned: float
    alloy_planned: float
    pure_planned: float

    class Config:
        from_attributes = True

# ---------- Supply ----------
class SupplyCreate(BaseModel):
    flask_id: int
    scrap_supplied: confloat(ge=0) = Field(..., description="Scrap used toward required metal")  # type: ignore
    fine_24k_supplied: confloat(ge=0) = 0.0  # type: ignore
    alloy_supplied: confloat(ge=0) = 0.0     # type: ignore
    posted_by: str

# ---------- Cutting ----------
class CuttingCreate(BaseModel):
    flask_id: int
    before_cut_A: float
    after_scrap_B: float
    after_casting_C: float
    posted_by: str

# schemas.py
class ReconciliationCreate(BaseModel):
    flask_id: int
    supplied_weight: condecimal(max_digits=12, decimal_places=3)
    before_cut_weight: condecimal(max_digits=12, decimal_places=3)
    after_cast_weight: condecimal(max_digits=12, decimal_places=3)
    after_scrap_weight: condecimal(max_digits=12, decimal_places=3)
    notes: str | None = None
    posted_by: str

class ReconciliationOut(BaseModel):
    flask_id: int
    date: date | None
    flask_no: str
    tree_no: str | None
    metal_id: int
    metal_name: str
    supplied_weight: Decimal
    before_cut_weight: Decimal
    after_cast_weight: Decimal
    after_scrap_weight: Decimal
    loss_part_i: Decimal
    loss_part_ii: Decimal
    loss_total: Decimal
