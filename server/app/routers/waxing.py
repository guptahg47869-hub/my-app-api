# server/app/routers/waxing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date as dtdate

from ..db import get_db
from .. import models, schemas
from ..formulas import est_metal_weight  # your helper

router = APIRouter(prefix="/waxing", tags=["waxing"])

@router.post("/post_to_prep")
def post_flask_from_tree(payload: schemas.PostFlaskFromTree, db: Session = Depends(get_db)):
    """
    From a Tree in transit, create a Flask and WaxingEntry, and move flask to METAL_PREP.

    Input:
      - tree_id (must be in transit)
      - date, flask_no (unique per date)
      - gasket_weight, total_weight  => tree_weight = total - gasket
    Output:
      - flask_id, tree_id, metal_weight (final), tree_weight, status
    """
    # 1) Load and validate the tree
    tree = db.get(models.Tree, payload.tree_id)
    if not tree or tree.status != models.TreeStatus.transit:
        raise HTTPException(status_code=400, detail="tree not in transit")

    # 2) Metal for formula
    metal = db.get(models.Metal, tree.metal_id)
    if not metal:
        raise HTTPException(status_code=400, detail="invalid metal on tree")


    # before inserting the new flask …
    dupe = db.execute(
        select(models.Flask.id)
        .where(
            models.Flask.date == payload.date,
            models.Flask.flask_no == payload.flask_no,
        )
    ).first()

    if dupe:
        raise HTTPException(
            status_code=409,
            detail=f'Flask #{payload.flask_no} is already used on {payload.date:%m-%d-%Y}',
        )

    # # 3) Prevent creating a new flask if this flask_no is already in rotation
    # active_dup = db.execute(
    #     select(models.Flask.id, models.Flask.date, models.Flask.status)
    #     .where(
    #         models.Flask.flask_no == payload.flask_no.strip(),
    #         models.Flask.status != models.Stage.done,
    #     )
    # ).first()

    # if active_dup:
    #     rid, rdate, rstatus = active_dup
    #     raise HTTPException(
    #         status_code=409,
    #         detail=f"Flask No '{payload.flask_no}' is already active (status={rstatus}, date={rdate}). "
    #             "Finish the other flask before reusing this number.",
    #     )

    # 4) Create the flask in METAL_PREP
    flask = models.Flask(
        date=payload.date,
        flask_no=payload.flask_no.strip(),
        metal_id=tree.metal_id,
        status=models.Stage.metal_prep,
        tree_id=tree.id,
    )
    db.add(flask)
    db.flush()  # get flask.id

    # 5) Compute final metal weight from weights entered here
    tree_weight = float(payload.total_weight) - float(payload.gasket_weight)
    if tree_weight < 0:
        raise HTTPException(status_code=400, detail="total_weight must be >= gasket_weight")

    final_metal_weight = est_metal_weight(tree_weight, metal.name)

    # 6) Write the WaxingEntry (source of truth for required metal)
    db.add(models.WaxingEntry(
        flask_id=flask.id,
        gasket_weight=payload.gasket_weight,
        tree_weight=tree_weight,
        metal_weight=final_metal_weight,
        posted_by=payload.posted_by,
    ))

    # 7) Mark the tree consumed
    tree.status = models.TreeStatus.consumed

    db.commit()

    return {
        "flask_id": flask.id,
        "tree_id": tree.id,
        "metal_weight": float(final_metal_weight),
        "tree_weight": float(tree_weight),
        "status": models.Stage.metal_prep.value,
    }

@router.get("/check_flask_unique")
def check_flask_unique(date: dtdate, flask_no: str, db: Session = Depends(get_db)):
    # same per-date uniqueness check
    dupe = db.execute(
        select(models.Flask.id)
        .where(
            models.Flask.date == date,
            models.Flask.flask_no == flask_no,
        )
    ).first()
    if dupe:
        # identical message to post_to_prep
        raise HTTPException(
            status_code=409,
            detail=f"Flask #{flask_no} is already used on {date:%m-%d-%Y}",
        )
    return {"ok": True}
