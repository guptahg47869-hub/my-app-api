# app/services/auto_quenching.py
import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from .. import models
from ..websockets import manager   # you already broadcast on manual post

CUTOVER_DELAY = timedelta(minutes=1)       # "1 minute after DONE"
POLL_INTERVAL = 30                         # how often to look for ready flasks

async def _advance_ready_flasks_once() -> int:
    """Promote any flasks that have been ready >= CUTOVER_DELAY."""
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - CUTOVER_DELAY
    advanced = 0

    with SessionLocal() as db:                         # new session per sweep
        # Find flasks in quenching whose ready_at is past cutoff
        q = (
            select(models.Flask.id)
            .join(models.Quenching, models.Quenching.flask_id == models.Flask.id)
            .where(models.Flask.status == models.Stage.quenching)
            .where(models.Quenching.ready_at <= cutoff)
        )
        flask_ids = list(db.execute(q).scalars())

        for fid in flask_ids:
            # Double-check & advance atomically in this transaction
            f: models.Flask | None = db.get(models.Flask, fid)
            if not f or f.status != models.Stage.quenching:
                continue
            f.status = models.Stage.cutting
            f.updated_at = now_utc
            db.commit()
            advanced += 1
            # let any connected UIs know
            try:
                await manager.broadcast({"event": "quenching_auto_posted", "flask_id": f.id})
            except Exception:
                pass
    return advanced


async def auto_quenching_loop():
    """Background loop started on app startup."""
    # small delay so startup finishes cleanly
    await asyncio.sleep(2)
    while True:
        try:
            await _advance_ready_flasks_once()
        except Exception:
            # keep the loop alive even if something goes wrong
            import logging; logging.exception('auto_quenching_loop iteration failed')
        await asyncio.sleep(POLL_INTERVAL)
