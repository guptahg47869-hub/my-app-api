from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app import models

router = APIRouter(prefix="/scrap", tags=["Scrap"])

@router.get("/reserves")
def get_scrap_reserves(db: Session = Depends(get_db)):
    reserves = db.query(models.ScrapReserve).all()
    return [
        {
            "id": r.id,
            "metal_id": r.metal_id,
            "metal_name": r.metal.name,  # assumes you have a relationship in models
            "qty_on_hand": r.qty_on_hand,
        }
        for r in reserves
    ]
