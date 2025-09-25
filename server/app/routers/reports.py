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
