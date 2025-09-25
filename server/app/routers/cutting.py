from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from ..db import get_db
from .. import models, schemas
from ..websockets import manager

router = APIRouter(prefix="/cutting", tags=["cutting"])

@router.post("")
async def post_cutting(payload: schemas.CuttingCreate, db: Session = Depends(get_db)):
    """
    Expected payload:
    {
      "flask_id": 1,
      "before_cut_A": 100.0,
      "after_scrap_B": 5.0,
      "after_casting_C": 92.0,
      "posted_by": "cutter1"
    }
    """
    flask_id = payload.flask_id
    if flask_id is None:
        raise HTTPException(422, "flask_id required")

    flask = db.get(models.Flask, flask_id)
    if not flask or flask.status != models.Stage.cutting:
        raise HTTPException(400, "flask not in cutting stage")

    A = float(payload.before_cut_A)
    B = float(payload.after_scrap_B)
    C = float(payload.after_casting_C)    
    posted_by = payload.posted_by

    if A < 0 or B < 0 or C < 0:
        raise HTTPException(400, "weights must be >= 0")

    loss = round(A - (B + C), 3)

    # Scrap credit back to reserves (transactionally)
    reserve = db.execute(select(models.ScrapReserve).where(models.ScrapReserve.metal_id == flask.metal_id)).scalar_one_or_none()
    if not reserve:
        raise HTTPException(400, "scrap reserve missing for this metal")

    now = datetime.utcnow()

    try:
        # upsert Cutting
        existing = db.execute(select(models.Cutting).where(models.Cutting.flask_id == flask.id)).scalar_one_or_none()
        if existing:
            existing.before_cut_A = A
            existing.after_scrap_B = B
            existing.after_casting_C = C
            existing.loss = loss
            existing.posted_at = now
            existing.posted_by = posted_by
        else:
            db.add(models.Cutting(
                flask_id=flask.id,
                before_cut_A=A,
                after_scrap_B=B,
                after_casting_C=C,
                loss=loss,
                posted_by=posted_by
            ))

        # increment reserve and log movement
        reserve.qty_on_hand = float(reserve.qty_on_hand) + B
        db.add(models.ScrapMovement(
            metal_id=flask.metal_id,
            flask_id=flask.id,
            delta=B,
            source="cutting.add",
            created_by=posted_by
        ))

        # advance state
        flask.status = models.Stage.done
        flask.updated_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise

    await manager.broadcast({"event": "cutting_posted", "flask_id": flask.id})
    return {
        "flask_id": flask.id,
        "loss": loss,
        "scrap_returned": B,
        "status": "done"
    }
