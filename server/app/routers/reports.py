from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from datetime import date
from typing import Optional

from ..db import get_db
from .. import models

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/transit")
def transit_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    metal: Optional[str] = Query(None),  # exact metal name; pass 'All' or omit for everything
    db: Session = Depends(get_db),
):
    """
    Summarize Trees currently in TRANSIT:
    - group by metal name
    - sum(est_metal_weight), count(*)
    Filters:
      - date_from / date_to (inclusive)
      - metal (exact name); use 'All' or omit for all metals
    """
    t = models.Tree
    m = models.Metal

    q = (
        select(
            m.name.label("metal_name"),
            func.count(t.id).label("count"),
            func.coalesce(func.sum(t.est_metal_weight), 0).label("total_est"),
        )
        .join(m, m.id == t.metal_id)
        .where(t.status == models.TreeStatus.transit)
        .group_by(m.name)
        .order_by(m.name.asc())
    )

    if date_from:
        q = q.where(t.date >= date_from)
    if date_to:
        q = q.where(t.date <= date_to)
    if metal and metal != "All":
        q = q.where(m.name == metal)

    rows = db.execute(q).all()

    data = [
        {
            "metal_name": r.metal_name,
            "count": int(r.count or 0),
            "total_est_metal_weight": float(r.total_est or 0.0),
        }
        for r in rows
    ]
    overall_total = round(sum(d["total_est_metal_weight"] for d in data), 3)

    return {
        "filters": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "metal": metal or "All",
        },
        "rows": data,
        "overall_total": overall_total,
    }

@router.get("/transit/trees")
def transit_trees(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    metal: str = Query(...),  # exact metal name required for drill-down
    db: Session = Depends(get_db),
):
    t = models.Tree
    m = models.Metal
    q = (
        select(
            t.id.label("tree_id"),
            t.date, t.tree_no, t.tree_weight, t.est_metal_weight,
            m.name.label("metal_name"),
        )
        .join(m, m.id == t.metal_id)
        .where(t.status == models.TreeStatus.transit, m.name == metal)
        .order_by(t.date.desc(), t.tree_no.asc())
    )
    if date_from:
        q = q.where(t.date >= date_from)
    if date_to:
        q = q.where(t.date <= date_to)

    rows = db.execute(q).all()
    return [{
        "tree_id": r.tree_id,
        "date": r.date.isoformat(),
        "tree_no": r.tree_no,
        "metal_name": r.metal_name,
        "tree_weight": float(r.tree_weight) if r.tree_weight is not None else None,
        "est_metal_weight": float(r.est_metal_weight) if r.est_metal_weight is not None else None,
    } for r in rows]

@router.get("/scrap_loss")
def scrap_loss(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    metal: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    c = models.Cutting
    f = models.Flask
    m = models.Metal

    q = (
        select(
            c.id,
            f.date,
            f.flask_no,
            m.name.label("metal_name"),
            c.before_cut_A, c.after_casting_C, c.after_scrap_B, c.loss,
        )
        .join(f, f.id == c.flask_id)
        .join(m, m.id == f.metal_id)
        .where(f.status == models.Stage.done)                      # <-- only confirmed (Recon -> Done)
        .order_by(f.date.desc(), m.name.asc(), f.flask_no.asc())
    )
    if date_from:
        q = q.where(f.date >= date_from)
    if date_to:
        q = q.where(f.date <= date_to)
    if metal and metal != "All":
        q = q.where(m.name == metal)

    rows = db.execute(q).all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "date": r.date.isoformat() if r.date else None,
            "flask_no": r.flask_no,
            "metal_name": r.metal_name,
            "before_cut_A": float(r.before_cut_A) if r.before_cut_A is not None else 0.0,
            "after_casting_C": float(r.after_casting_C) if r.after_casting_C is not None else 0.0,
            "after_scrap_B": float(r.after_scrap_B) if r.after_scrap_B is not None else 0.0,
            "loss": float(r.loss) if r.loss is not None else 0.0,
        })
    return out
