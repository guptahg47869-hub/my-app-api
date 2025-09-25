from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from ..db import get_db
from .. import models
from ..websockets import manager

router = APIRouter(prefix="/quenching", tags=["quenching"])

@router.post("/{flask_id}/post")
async def post_quenching(flask_id: int, payload: dict, db: Session = Depends(get_db)):
    flask = db.get(models.Flask, flask_id)
    if not flask or flask.status != models.Stage.quenching:
        raise HTTPException(400, "flask not in quenching stage")

    q = db.execute(select(models.Quenching).where(models.Quenching.flask_id == flask.id)).scalar_one_or_none()
    if not q:
        raise HTTPException(400, "quenching record missing (did casting complete?)")

    # Optional guard: ensure it's ready (time reached). Comment out if not needed.
    # if datetime.now(timezone.utc) < q.ready_at.replace(tzinfo=timezone.utc):
    #     raise HTTPException(400, "not ready yet")

    # Advance to cutting stage
    now = datetime.utcnow()
    flask.status = models.Stage.cutting
    flask.updated_at = now
    db.commit()

    await manager.broadcast({"event": "quenching_posted", "flask_id": flask.id})
    return {
        "flask_id": flask.id,
        "ready_at": q.ready_at.isoformat(),
        "moved_to": "cutting"
    }
