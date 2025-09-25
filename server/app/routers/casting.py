from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import select
from ..db import get_db
from .. import models, formulas
from ..websockets import manager

router = APIRouter(prefix="/casting", tags=["casting"])

@router.post("/{flask_id}/complete")
async def complete_casting(flask_id: int, payload: dict, db: Session = Depends(get_db)):
    flask = db.get(models.Flask, flask_id)
    if not flask or flask.status != models.Stage.casting:
        raise HTTPException(400, "flask not in casting stage")

    # lookup metal
    metal = flask.metal
    casting_temp = formulas.casting_temp_for(metal.name)
    oven_temp = formulas.oven_temp_for(metal.name)

    existing = db.execute(select(models.Casting).where(models.Casting.flask_id == flask.id)).scalar_one_or_none()
    now = datetime.utcnow()
    if existing:
        existing.casting_temp = casting_temp
        existing.oven_temp = oven_temp
        existing.completed_at = now
        existing.posted_by = payload.get("posted_by", "system")
    else:
        db.add(models.Casting(
            flask_id=flask.id,
            casting_temp=casting_temp,
            oven_temp=oven_temp,
            completed_at=now,
            posted_by=payload.get("posted_by", "system")
        ))

    q_minutes = formulas.quenching_minutes_for(metal.name)
    ready_at_dt = formulas.ready_at(now, q_minutes)

    existing_q = db.execute(
        select(models.Quenching).where(models.Quenching.flask_id == flask.id)
    ).scalar_one_or_none()

    if existing_q:
        existing_q.quenching_time_min = q_minutes
        existing_q.ready_at = ready_at_dt
        existing_q.posted_by = payload.get("posted_by", "system")
    else:
        db.add(models.Quenching(
            flask_id=flask.id,
            quenching_time_min=q_minutes,
            ready_at=ready_at_dt,
            posted_by=payload.get("posted_by", "system")
        ))
        
    flask.status = models.Stage.quenching
    flask.updated_at = now
    db.commit()

    await manager.broadcast({"event": "casting_complete", "flask_id": flask.id})
    return {
        "flask_id": flask.id,
        "casting_temp": float(casting_temp),
        "oven_temp": float(oven_temp),
        "completed_at": now.isoformat()
    }
