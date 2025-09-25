from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date as dtdate

from ..db import get_db
from .. import models, schemas
from ..formulas import est_metal_weight  # reuse your new helper

router = APIRouter(prefix="/waxing", tags=["waxing"])


@router.post("/post_to_supply")
def post_flask_from_tree(payload: schemas.PostFlaskFromTree, db: Session = Depends(get_db)):
    """
    From a Tree in transit, create a Flask and WaxingEntry, and move flask to SUPPLY.
    Input:
      - tree_id (must be in transit)
      - date, flask_no (unique per date)
      - gasket_weight, total_weight  => tree_weight = total - gasket
    Output:
      - flask_id, tree_id, metal_weight (final)
    """
    # 1) Load and validate the tree
    tree = db.get(models.Tree, payload.tree_id)
    if not tree or tree.status != models.TreeStatus.transit:
        raise HTTPException(status_code=400, detail="tree not in transit")

    # 2) Metal required for formula
    metal = db.get(models.Metal, tree.metal_id)
    if not metal:
        raise HTTPException(status_code=400, detail="invalid metal on tree")

    # 3) Prevent duplicate flask (date, flask_no)
    dup = db.execute(
        select(models.Flask).where(
            (models.Flask.date == payload.date) & (models.Flask.flask_no == payload.flask_no)
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="A flask with this Date and Flask No already exists")

    # 4) Create the flask directly in SUPPLY
    flask = models.Flask(
        date=payload.date,
        flask_no=payload.flask_no.strip(),
        metal_id=tree.metal_id,
        status=models.Stage.supply,
        tree_id=tree.id,
    )
    db.add(flask)
    db.flush()  # get flask.id without committing yet

    # 5) Compute final metal weight: (total - gasket) => tree_weight, then apply formula
    tree_weight = float(payload.total_weight) - float(payload.gasket_weight)
    if tree_weight < 0:
        raise HTTPException(status_code=400, detail="total_weight must be >= gasket_weight")

    final_metal_weight = est_metal_weight(tree_weight, metal.name)

    # 6) Write the WaxingEntry that becomes the source of truth for required metal
    db.add(models.WaxingEntry(
        flask_id=flask.id,
        gasket_weight=payload.gasket_weight,
        tree_weight=tree_weight,
        metal_weight=final_metal_weight,
        posted_by=payload.posted_by,
    ))

    # 7) Mark the tree consumed
    tree.status = models.TreeStatus.consumed

    # 8) Persist all
    db.commit()

    return {
        "flask_id": flask.id,
        "tree_id": tree.id,
        "metal_weight": float(final_metal_weight),
        "tree_weight": float(tree_weight),
        "status": models.Stage.supply.value,
    }
