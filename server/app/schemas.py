from pydantic import BaseModel, condecimal, field_validator
from datetime import date
from pydantic import BaseModel, Field, confloat

class TreeCreate(BaseModel):
    date: date
    tree_no: str
    metal_id: int
    tree_weight: condecimal(max_digits=12, decimal_places=3, ge=0) # type: ignore
    posted_by: str

class TreeOut(BaseModel):
    id: int
    date: date
    tree_no: str
    metal_id: int
    metal_name: str
    tree_weight: condecimal(max_digits=12, decimal_places=3) # type: ignore
    est_metal_weight: condecimal(max_digits=12, decimal_places=3) # type: ignore
    status: str

    class Config:
        from_attributes = True

class PostFlaskFromTree(BaseModel):
    tree_id: int
    flask_no: str
    date: date
    gasket_weight: condecimal(max_digits=12, decimal_places=3, ge=0) # type: ignore
    total_weight: condecimal(max_digits=12, decimal_places=3, ge=0) # type: ignore
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

# class SupplyCreate(BaseModel):
#     flask_id: int
#     scrap_supplied: float
#     posted_by: str

# schemas.py

class SupplyCreate(BaseModel):
    flask_id: int
    scrap_supplied: confloat(ge=0) = Field(..., description="Scrap used toward required metal") # type: ignore
    fine_24k_supplied: confloat(ge=0) = 0.0 # type: ignore
    alloy_supplied: confloat(ge=0) = 0.0 # type: ignore
    posted_by: str


class CuttingCreate(BaseModel):
    flask_id: int
    before_cut_A: float
    after_scrap_B: float
    after_casting_C: float
    posted_by: str