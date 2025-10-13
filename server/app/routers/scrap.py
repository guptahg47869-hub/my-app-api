# routers/scrap.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Literal

from ..db import get_db
from .. import models

router = APIRouter(prefix="/scrap", tags=["Scrap"])

@router.get("/reserves")
def get_scrap_reserves(db: Session = Depends(get_db)):
    reserves = db.query(models.ScrapReserve).all()
    return [
        {
            "id": r.id,
            "metal_id": r.metal_id,
            "metal_name": r.metal.name,  # assumes a relationship in models
            "qty_on_hand": float(r.qty_on_hand or 0),
        }
        for r in reserves
    ]

# ----- NEW -----
class ScrapAdjustIn(BaseModel):
    metal_id: int = Field(..., description="Metal id (matches ScrapReserve.metal_id)")
    action: Literal["add", "remove"] = Field(..., description="add | remove")
    amount: float = Field(..., gt=0, description="Weight to add/remove (> 0)")

@router.post("/adjust")
def adjust_scrap(req: ScrapAdjustIn, db: Session = Depends(get_db)):
    # locate (or create for 'add') the reserve row
    reserve = db.query(models.ScrapReserve).filter(models.ScrapReserve.metal_id == req.metal_id).first()

    if reserve is None:
        if req.action == "add":
            # create a new reserve row starting at 0
            reserve = models.ScrapReserve(metal_id=req.metal_id, qty_on_hand=0.0)
            db.add(reserve)
            db.flush()  # get ids
        else:
            raise HTTPException(status_code=400, detail="No reserve exists for this metal; cannot remove.")

    current = float(reserve.qty_on_hand or 0.0)
    delta = req.amount if req.action == "add" else -req.amount
    new_total = current + delta

    if new_total < 0:
        raise HTTPException(status_code=400, detail="Cannot remove more than the current reserve amount.")

    reserve.qty_on_hand = new_total
    db.commit()
    db.refresh(reserve)

    return {
        "id": reserve.id,
        "metal_id": reserve.metal_id,
        "metal_name": reserve.metal.name,
        "qty_on_hand": float(reserve.qty_on_hand or 0.0),
    }
