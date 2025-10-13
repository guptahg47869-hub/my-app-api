# server/app/routers/queue.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone, date

from ..db import get_db
from .. import models

router = APIRouter(prefix="/queue", tags=["queue"])

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
            # NEW: include gasket/total
            t.gasket_weight,
            t.total_weight,
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

    q = q.order_by(t.date.desc(), m.name.asc(), t.tree_no.asc())
    rows = db.execute(q).all()

    return [
        {
            "tree_id": r.tree_id,
            "date": r.date.isoformat(),
            "tree_no": r.tree_no,
            "metal_name": r.metal_name,
            # NEW: surface to UI for autofill (may be None)
            "gasket_weight": float(r.gasket_weight) if r.gasket_weight is not None else None,
            "total_weight":  float(r.total_weight)  if r.total_weight  is not None else None,
            # existing
            "tree_weight": float(r.tree_weight),
            "est_metal_weight": float(r.est_metal_weight),
        }
        for r in rows
    ]

@router.get("/metal_prep")
def metal_prep_queue(
    db: Session = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    metal: str | None = None,
    q: str | None = Query(None, description="search by flask_no OR tree_no"),
):
    f = models.Flask
    m = models.Metal
    w = models.WaxingEntry
    t = models.Tree

    stmt = (
        select(
            f.id.label("flask_id"),                      # ⬅ ensure this key exists
            f.date,
            f.flask_no,
            t.tree_no.label("tree_no"),                  # ⬅ include tree_no
            m.name.label("metal_name"),
            w.metal_weight.label("required_metal_weight"),
        )
        .join(m, m.id == f.metal_id)
        .join(w, w.flask_id == f.id)
        .outerjoin(t, t.id == f.tree_id)                # ⬅ join to Tree
        .where(f.status == models.Stage.metal_prep)
        .order_by(f.date.desc(), m.name.asc(), f.flask_no.asc())
    )

    if date_from:
        stmt = stmt.where(f.date >= date_from)
    if date_to:
        stmt = stmt.where(f.date <= date_to)
    if metal:
        stmt = stmt.where(m.name == metal)
    if q:                                               # ⬅ search by flask OR tree
        like = f"%{q}%"
        stmt = stmt.where((f.flask_no.ilike(like)) | (t.tree_no.ilike(like)))

    rows = db.execute(stmt).all()
    return [{
        "flask_id": r.flask_id,                         # ⬅ returned to UI
        "date": r.date.isoformat() if r.date else None,
        "flask_no": r.flask_no,
        "tree_no": r.tree_no,                           # ⬅ returned to UI
        "metal_name": r.metal_name,
        "required_metal_weight": float(r.required_metal_weight or 0.0),
    } for r in rows]

@router.get("/reconciliation")
def reconciliation_queue(
    db: Session = Depends(get_db),
    date_from: date | None = None,
    date_to: date | None = None,
    metal: str | None = None,
    q: str | None = Query(None, description="search by flask_no OR tree_no"),
):
    f = models.Flask
    m = models.Metal
    t = models.Tree
    r = models.Reconciliation

    stmt = (
        select(
            f.id.label("flask_id"),
            f.date,
            f.flask_no,
            t.tree_no.label("tree_no"),
            m.name.label("metal_name"),
            r.supplied_weight,
            r.before_cut_weight,
            r.after_cast_weight,
            r.after_scrap_weight,
            r.loss_total,
        )
        .join(m, m.id == f.metal_id)
        .outerjoin(t, t.id == f.tree_id)
        .join(r, r.flask_id == f.id)
        .where(f.status == models.Stage.reconciliation)
        .order_by(f.date.desc(), m.name.asc(), f.flask_no.asc())
    )

    if date_from:
        stmt = stmt.where(f.date >= date_from)
    if date_to:
        stmt = stmt.where(f.date <= date_to)
    if metal:
        stmt = stmt.where(m.name == metal)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((f.flask_no.ilike(like)) | (t.tree_no.ilike(like)))

    rows = db.execute(stmt).all()
    return [
        {
            "flask_id": r.flask_id,
            "date": r.date.isoformat() if r.date else None,
            "flask_no": r.flask_no,
            "tree_no": r.tree_no,
            "metal_name": r.metal_name,
            "supplied_weight": float(r.supplied_weight or 0.0),
            "before_cut_weight": float(r.before_cut_weight or 0.0),
            "after_cast_weight": float(r.after_cast_weight or 0.0),
            "after_scrap_weight": float(r.after_scrap_weight or 0.0),
            "loss_total": float(r.loss_total or 0.0),
        }
        for r in rows
    ]


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

        supply_row = db.execute(
            select(models.Supply).where(models.Supply.flask_id == fl.id)
        ).scalar_one_or_none()

        # add Tree No for display / search
        tno = db.execute(
            select(models.Tree.tree_no).where(models.Tree.id == fl.tree_id)
        ).scalar_one_or_none()
        item["tree_no"] = tno


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

        if stage == models.Stage.quenching:
            try:
                qrec = db.execute(
                    select(models.Quenching).where(models.Quenching.flask_id == fl.id)
                ).scalar_one_or_none()
                if qrec:
                    item["quenching_time_min"] = qrec.quenching_time_min
                    item["ready_at"] = qrec.ready_at.isoformat()
                    from datetime import timezone as _tz, datetime as _dt
                    now = _dt.now(_tz.utc)
                    ready = qrec.ready_at
                    if ready.tzinfo is None:
                        ready = ready.replace(tzinfo=_tz.utc)
                    mins_left = int(max(0, (ready - now).total_seconds() // 60))
                    item["minutes_left"] = mins_left
            except Exception:
                pass

        result.append(item)

    return result

