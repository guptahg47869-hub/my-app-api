from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import date as dtdate
import re

from ..db import get_db
from .. import models, schemas
from ..formulas import est_metal_weight  # your existing helper

router = APIRouter(prefix="/trees", tags=["trees"])

# @router.get('/next_number')
# def get_next_tree_number(date: dtdate, db: Session = Depends(get_db)):
#     """
#     Return the next tree number for the given date in the format TREE-0001.
#     Resets per date; continues the series if there are already trees that day.
#     """
#     rows = db.query(models.Tree).filter(models.Tree.date == date).all()
#     max_seq = 0
#     for t in rows:
#         s = (t.tree_no or '').strip()
#         m = re.search(r'(\d+)$', s)  # take trailing digits
#         if m:
#             try:
#                 n = int(m.group(1))
#                 if n > max_seq:
#                     max_seq = n
#             except Exception:
#                 pass
#     next_seq = max_seq + 1
#     next_tree_no = f'TREE-{next_seq:04d}'
#     return {'tree_no': next_tree_no}

@router.get('/next_number')
def get_next_tree_number(db: Session = Depends(get_db)):
    """Return the next global tree number like TREE-000001 (no daily reset)."""
    rows = db.query(models.Tree.tree_no).all()
    max_seq = 0
    for (s,) in rows:
        if not s:
            continue
        m = re.search(r'(\d+)$', s.strip())
        if m:
            n = int(m.group(1))
            if n > max_seq:
                max_seq = n
    next_seq = max_seq + 1
    return {'tree_no': f'TREE-{next_seq:06d}'}


@router.post("", response_model=schemas.TreeOut)
def create_tree(payload: schemas.TreeCreate, db: Session = Depends(get_db)):
    """
    Create a Tree (enters 'transit').

    Accepts either:
      - tree_weight (legacy client), OR
      - gasket_weight + total_weight (new flow) → derives tree_weight = total - gasket

    Computes est_metal_weight using your existing formula helper.
    """
    # Validate metal
    metal = db.get(models.Metal, payload.metal_id)
    if not metal:
        raise HTTPException(status_code=400, detail="invalid metal_id")

    exists = db.execute(
        select(models.Tree).where(models.Tree.tree_no == payload.tree_no)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="A tree with this Tree No already exists")

    # At this point payload.tree_weight is guaranteed by schema:
    # - either provided explicitly, or
    # - derived from gasket/total inside TreeCreate model_validator
    tree_wt = float(payload.tree_weight)

    # Estimate metal using your formula
    est = est_metal_weight(tree_wt, metal.name)

    tree = models.Tree(
        date=payload.date,
        tree_no=payload.tree_no.strip(),
        metal_id=payload.metal_id,
        gasket_weight=payload.gasket_weight,   # may be None (legacy)
        total_weight=payload.total_weight,     # may be None (legacy)
        tree_weight=tree_wt,
        est_metal_weight=est,
        status=models.TreeStatus.transit,
        posted_by=payload.posted_by,
    )

    db.add(tree)
    db.flush()  # get tree.id

    # --- upsert/attach bags ---
    bag_nos = [b.strip().upper() for b in (payload.bag_nos or []) if b and b.strip()]
    if bag_nos:
        existing = db.query(models.Bag).filter(models.Bag.bag_no.in_(bag_nos)).all()
        existing_by_no = {b.bag_no: b for b in existing}
        to_attach = []
        for bno in bag_nos:
            bag = existing_by_no.get(bno)
            if not bag:
                bag = models.Bag(bag_no=bno)
                db.add(bag)
                db.flush()  # get bag.id
            to_attach.append(bag)
        tree.bags = list({*tree.bags, *to_attach})  # merge unique

    db.commit()
    db.refresh(tree)

    return schemas.TreeOut(
        id=tree.id,
        date=tree.date,
        tree_no=tree.tree_no,
        metal_id=tree.metal_id,
        metal_name=metal.name,
        gasket_weight=tree.gasket_weight,
        total_weight=tree.total_weight,
        tree_weight=tree.tree_weight,
        est_metal_weight=tree.est_metal_weight,
        status=tree.status.value,
        bag_nos=[b.bag_no for b in tree.bags],  # NEW
    )
