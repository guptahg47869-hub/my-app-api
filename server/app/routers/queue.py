# server/app/routers/queue.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone, date

from ..db import get_db
from .. import models

router = APIRouter(prefix="/queue", tags=["queue"])


# ---- 1) Trees in TRANSIT (separate endpoint) ----
@router.get("/transit", name="Transit Queue")
def transit_queue(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    tree_no: str | None = Query(None),
    metal: str | None = Query(None),  # exact metal name
    db: Session = Depends(get_db),
):
    t = models.Tree
    m = models.Metal

    q = (
        select(
            t.id.label("tree_id"),
            t.date,
            t.tree_no,
            t.tree_weight,
            t.est_metal_weight,
            m.name.label("metal_name"),
        )
        .join(m, m.id == t.metal_id)
        .where(t.status == models.TreeStatus.transit)
    )

    if date_from:
        q = q.where(t.date >= date_from)
    if date_to:
        q = q.where(t.date <= date_to)
    if tree_no:
        q = q.where(t.tree_no.ilike(f"%{tree_no}%"))
    if metal:
        q = q.where(m.name == metal)

    # sort: date DESC, metal ASC
    q = q.order_by(t.date.desc(), m.name.asc(), t.tree_no.asc())

    rows = db.execute(q).all()
    return [
        {
            "tree_id": r.tree_id,
            "date": r.date.isoformat(),
            "tree_no": r.tree_no,
            "metal_name": r.metal_name,
            "tree_weight": float(r.tree_weight),
            "est_metal_weight": float(r.est_metal_weight),
        }
        for r in rows
    ]


# ---- 2) Flasks by STAGE (unchanged path/behavior) ----
@router.get("/{stage}", name="List By Stage")
def list_by_stage(
    stage: models.Stage,
    flask_no: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List flasks by pipeline stage (waxing/supply/casting/quenching/cutting/done)."""
    f = models.Flask
    m = models.Metal

    stmt = (
        select(f)
        .join(m)
        .where(f.status == stage)
        .order_by(
            f.date.desc(),
            m.name.asc(),
            f.flask_no.asc(),
        )
    )

    if flask_no:
        stmt = stmt.where(f.flask_no.ilike(f"%{flask_no}%"))

    flasks = db.execute(stmt.order_by(f.date.desc())).scalars().all()

    result: list[dict] = []
    for fl in flasks:
        item = {
            "id": fl.id,
            "date": fl.date.isoformat(),
            "flask_no": fl.flask_no,
            "metal_id": fl.metal_id,
            "metal_name": fl.metal.name if getattr(fl, "metal", None) else None,
            "status": fl.status.value,
        }

        # metal_weight display rule:
        # - For casting and onward: show actually supplied (scrap + 24k + alloy)
        # - Otherwise: show Waxing estimated metal_weight
        supply_row = db.execute(
            select(models.Supply).where(models.Supply.flask_id == fl.id)
        ).scalar_one_or_none()

        if stage in (
            models.Stage.casting,
            models.Stage.quenching,
            models.Stage.cutting,
            models.Stage.done,
        ) and supply_row:
            total_supplied = (
                float(supply_row.scrap_supplied or 0)
                + float(getattr(supply_row, "fine_24k_supplied", 0) or 0)
                + float(getattr(supply_row, "alloy_supplied", 0) or 0)
            )
            item["metal_weight"] = round(total_supplied, 3)
        else:
            waxing_row = db.execute(
                select(models.WaxingEntry).where(models.WaxingEntry.flask_id == fl.id)
            ).scalar_one_or_none()
            if waxing_row:
                item["metal_weight"] = float(waxing_row.metal_weight)

        # include quenching details if available
        if stage == models.Stage.quenching:
            try:
                qrec = db.execute(
                    select(models.Quenching).where(models.Quenching.flask_id == fl.id)
                ).scalar_one_or_none()
                if qrec:
                    item["quenching_time_min"] = qrec.quenching_time_min
                    item["ready_at"] = qrec.ready_at.isoformat()
                    # minutes remaining
                    now = datetime.now(timezone.utc)
                    ready = qrec.ready_at
                    if ready.tzinfo is None:
                        ready = ready.replace(tzinfo=timezone.utc)
                    mins_left = int(max(0, (ready - now).total_seconds() // 60))
                    item["minutes_left"] = mins_left
            except Exception:
                # be tolerant if the relationship/table isn't present
                pass

        result.append(item)

    return result
