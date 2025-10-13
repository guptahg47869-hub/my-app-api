# server/app/routers/flask_search.py
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models

router = APIRouter(prefix="/search", tags=["flask_search"])


def _stage_order_value(stage: str) -> int:
    order = {
        "transit": 0,
        "metal_prep": 1,
        "supply": 2,
        "casting": 3,
        "quenching": 4,
        "cutting": 5,
        "reconciliation": 6,
        "done": 7,
    }
    return order.get(stage, 99)


def _bag_model_and_col(models_module):
    Bag = getattr(models_module, "Bag", None) or getattr(models_module, "BagNo", None)
    if Bag is None:
        return None, None
    if hasattr(Bag, "bag_no"):
        return Bag, Bag.bag_no
    if hasattr(Bag, "number"):
        return Bag, Bag.number
    if hasattr(Bag, "name"):
        return Bag, Bag.name
    return Bag, None


@router.get("/flasks")
def search_flasks(
    db: Session = Depends(get_db),
    stage: Optional[str] = Query(
        "active",
        description="active (=not done), or one of: transit, metal_prep, supply, casting, quenching, cutting, reconciliation, done; use 'all' to disable stage filter",
    ),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    metal: Optional[str] = None,
    q: Optional[str] = Query(None, description="search by flask_no / tree_no / bag number"),
) -> List[Dict[str, Any]]:
    F, T, M, W = models.Flask, models.Tree, models.Metal, models.WaxingEntry

    # -------------------- FLASKS --------------------
    f_rows: List[Any] = []
    if stage != "transit":  # <- transit is trees-only; skip querying flasks
        f_stmt = (
            select(
                F.id.label("flask_id"),
                F.tree_id,
                F.date,
                F.flask_no,
                F.status.label("stage"),
                M.name.label("metal_name"),
                T.tree_no.label("tree_no"),
                W.metal_weight.label("metal_weight"),
            )
            .join(M, M.id == F.metal_id)
            .outerjoin(T, T.id == F.tree_id)
            .join(W, W.flask_id == F.id)
        )

        if stage and stage not in ("all", ""):
            if stage == "active":
                f_stmt = f_stmt.where(F.status != models.Stage.done)
            else:
                # only real flask stages should be coerced to enum
                try:
                    stage_enum = models.Stage(stage)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Unknown stage '{stage}'")
                f_stmt = f_stmt.where(F.status == stage_enum)

        if date_from:
            f_stmt = f_stmt.where(F.date >= date_from)
        if date_to:
            f_stmt = f_stmt.where(F.date <= date_to)
        if metal:
            f_stmt = f_stmt.where(M.name == metal)

        f_rows = db.execute(f_stmt).all()

    # -------------------- TREES without a flask (TRANSIT) --------------------
    t_rows: List[Any] = []
    if stage in (None, "", "all", "active", "transit"):
        sub = select(F.id).where(F.tree_id == T.id, F.status != models.Stage.done).exists()
        t_stmt = (
            select(
                T.id.label("tree_id"),
                T.date,
                T.tree_no,
                M.name.label("metal_name"),
                T.est_metal_weight.label("metal_weight"),
            )
            .join(M, M.id == T.metal_id)
            .where(T.status == models.TreeStatus.transit)
            .where(~sub)
        )
        if date_from:
            t_stmt = t_stmt.where(T.date >= date_from)
        if date_to:
            t_stmt = t_stmt.where(T.date <= date_to)
        if metal:
            t_stmt = t_stmt.where(M.name == metal)

        t_rows = db.execute(t_stmt).all()

    # -------------------- BAG NUMBERS --------------------
    FlaskBags = getattr(models, "flask_bags", None)
    TreeBags = getattr(models, "tree_bags", None)
    Bag, BAG_COL = _bag_model_and_col(models)

    bag_by_flask = defaultdict(list)
    bag_by_tree = defaultdict(list)

    if Bag is not None and BAG_COL is not None:
        flask_ids = [r.flask_id for r in f_rows]
        if FlaskBags is not None and flask_ids:
            fb_stmt = (
                select(FlaskBags.c.flask_id, BAG_COL)
                .select_from(FlaskBags.join(Bag, Bag.id == FlaskBags.c.bag_id))
                .where(FlaskBags.c.flask_id.in_(flask_ids))
                .order_by(BAG_COL.asc())
            )
            for fid, bag_text in db.execute(fb_stmt):
                if bag_text:
                    bag_by_flask[fid].append(str(bag_text))

        tree_ids = set()
        tree_ids.update([r.tree_id for r in f_rows if getattr(r, "tree_id", None) is not None])
        tree_ids.update([getattr(r, "tree_id", None) for r in t_rows if getattr(r, "tree_id", None) is not None])
        tree_ids.update([getattr(r, "tree_id", None) for r in t_rows])

        if TreeBags is not None and tree_ids:
            tb_stmt = (
                select(TreeBags.c.tree_id, BAG_COL)
                .select_from(TreeBags.join(Bag, Bag.id == TreeBags.c.bag_id))
                .where(TreeBags.c.tree_id.in_(list(tree_ids)))
                .order_by(BAG_COL.asc())
            )
            for tid, bag_text in db.execute(tb_stmt):
                if bag_text:
                    bag_by_tree[tid].append(str(bag_text))

    # -------------------- Build unified results --------------------
    results: List[Dict[str, Any]] = []

    for r in f_rows:
        seen, bags = set(), []
        for btxt in bag_by_flask.get(r.flask_id, []):
            if btxt not in seen:
                seen.add(btxt); bags.append(btxt)
        if getattr(r, "tree_id", None) is not None:
            for btxt in bag_by_tree.get(r.tree_id, []):
                if btxt not in seen:
                    seen.add(btxt); bags.append(btxt)

        results.append(
            {
                "id": r.flask_id,
                "kind": "flask",
                "stage": r.stage.value if hasattr(r.stage, "value") else str(r.stage),
                "date": r.date.isoformat() if r.date else None,
                "metal_name": r.metal_name,
                "flask_no": r.flask_no,
                "tree_no": r.tree_no,
                "metal_weight": float(r.metal_weight or 0.0),
                "bag_nos": bags,
                "bag_nos_text": ", ".join(bags),
            }
        )

    for r in t_rows:
        bags = bag_by_tree.get(r.tree_id, [])
        results.append(
            {
                "id": f"tree-{r.tree_id}",
                "kind": "tree",
                "stage": "transit",
                "date": r.date.isoformat() if r.date else None,
                "metal_name": r.metal_name,
                "flask_no": None,
                "tree_no": r.tree_no,
                "metal_weight": float(r.metal_weight or 0.0),
                "bag_nos": bags,
                "bag_nos_text": ", ".join(bags),
            }
        )

    if q:
        s = q.strip().lower()
        def _hit(row: Dict[str, Any]) -> bool:
            return any([
                (row.get("flask_no") or "").lower().find(s) >= 0,
                (row.get("tree_no") or "").lower().find(s) >= 0,
                any((b.lower().find(s) >= 0) for b in row.get("bag_nos") or []),
            ])
        results = [r for r in results if _hit(r)]

    results.sort(
        key=lambda r: (
            _stage_order_value(str(r.get("stage"))),
            r.get("date") or "",
            (r.get("metal_name") or "").lower(),
            str(r.get("flask_no") or ""),
        )
    )
    return results


@router.get("/flasks/export")
def export_flasks_csv(
    db: Session = Depends(get_db),
    stage: Optional[str] = "active",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    metal: Optional[str] = None,
    q: Optional[str] = None,
):
    rows = search_flasks(db=db, stage=stage, date_from=date_from, date_to=date_to, metal=metal, q=q)
    import csv
    from io import StringIO
    from fastapi.responses import StreamingResponse

    buf = StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=["date", "stage", "metal_name", "flask_no", "tree_no", "metal_weight", "bag_nos_text"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in rows:
        writer.writerow(
            {
                "date": r.get("date") or "",
                "stage": r.get("stage") or "",
                "metal_name": r.get("metal_name") or "",
                "flask_no": r.get("flask_no") or "",
                "tree_no": r.get("tree_no") or "",
                "metal_weight": r.get("metal_weight") if r.get("metal_weight") is not None else "",
                "bag_nos_text": ", ".join(r.get("bag_nos") or []),
            }
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="flask_search.csv"'},
    )
