from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import date as dtdate

from ..db import get_db
from .. import models, schemas
from ..formulas import est_metal_weight  # your helper

router = APIRouter(prefix="/trees", tags=["trees"])


@router.post("", response_model=schemas.TreeOut)
def create_tree(payload: schemas.TreeCreate, db: Session = Depends(get_db)):
    """
    Create a Tree for planning (enters 'transit').
    - Unique key: (date, tree_no)
    - est_metal_weight is computed from tree_weight and metal via your formula
    """
    # validate metal
    metal = db.get(models.Metal, payload.metal_id)
    if not metal:
        raise HTTPException(status_code=400, detail="invalid metal_id")

    # enforce unique (date, tree_no)
    exists = db.execute(
        select(models.Tree).where(and_(
            models.Tree.date == payload.date,
            models.Tree.tree_no == payload.tree_no
        ))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="A tree with this Date and Tree No already exists")

    # estimate using your helper (no gasket at this step)
    est = est_metal_weight(float(payload.tree_weight), metal.name)

    tree = models.Tree(
        date=payload.date,
        tree_no=payload.tree_no.strip(),
        metal_id=payload.metal_id,
        tree_weight=payload.tree_weight,
        est_metal_weight=est,
        status=models.TreeStatus.transit,
        posted_by=payload.posted_by,
    )
    db.add(tree)
    db.commit()
    db.refresh(tree)

    # response_model=TreeOut will serialize these cleanly
    return schemas.TreeOut(
        id=tree.id,
        date=tree.date,
        tree_no=tree.tree_no,
        metal_id=tree.metal_id,
        metal_name=metal.name,
        tree_weight=tree.tree_weight,
        est_metal_weight=tree.est_metal_weight,
        status=tree.status.value,
    )
