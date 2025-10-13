from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from decimal import Decimal

from ..db import get_db
from .. import models, schemas
from ..websockets import manager

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.get("/{flask_id}")
def get_recon(flask_id: int, db: Session = Depends(get_db)):
    """Fetch staged reconciliation values plus context."""
    flask = db.get(models.Flask, flask_id)
    if not flask:
        raise HTTPException(404, "Flask not found")

    rec = db.execute(
        select(models.Reconciliation).where(models.Reconciliation.flask_id == flask.id)
    ).scalar_one_or_none()

    metal = db.get(models.Metal, flask.metal_id)
    tree_no = None
    if flask.tree_id:
        tree = db.get(models.Tree, flask.tree_id)
        tree_no = tree.tree_no if tree else None

    return {
        "flask_id": flask.id,
        "date": flask.date.isoformat() if flask.date else None,
        "flask_no": flask.flask_no,
        "tree_no": tree_no,
        "metal_id": flask.metal_id,
        "metal_name": metal.name if metal else None,
        "supplied_weight": float(getattr(rec, "supplied_weight", 0.0) or 0.0),
        "before_cut_weight": float(getattr(rec, "before_cut_weight", 0.0) or 0.0),
        "after_cast_weight": float(getattr(rec, "after_cast_weight", 0.0) or 0.0),
        "after_scrap_weight": float(getattr(rec, "after_scrap_weight", 0.0) or 0.0),
        "loss_part_i": float(getattr(rec, "loss_part_i", 0.0) or 0.0),
        "loss_part_ii": float(getattr(rec, "loss_part_ii", 0.0) or 0.0),
        "loss_total": float(getattr(rec, "loss_total", 0.0) or 0.0),
    }


@router.post("/confirm")
async def confirm(payload: schemas.ReconciliationCreate, db: Session = Depends(get_db)):
    """
    Finalize reconciliation:
      - recompute loss_i, loss_ii, loss_total
      - validations (non-negative; ≤5% of before-cut)
      - credit after_scrap to reserve
      - update Cutting row with final numbers
      - advance flask to 'done'
    """
    flask = db.get(models.Flask, payload.flask_id)
    if not flask or flask.status != models.Stage.reconciliation:
        raise HTTPException(400, "Flask not in reconciliation stage")

    try:
        supplied   = Decimal(str(payload.supplied_weight))
        before     = Decimal(str(payload.before_cut_weight))
        after_cast = Decimal(str(payload.after_cast_weight))
        after_scrap= Decimal(str(payload.after_scrap_weight))
    except Exception:
        raise HTTPException(400, "Invalid numeric values")

    if before < 0 or after_cast < 0 or after_scrap < 0 or supplied < 0:
        raise HTTPException(400, "Weights must be >= 0")

    loss_i   = supplied - before
    loss_ii  = before - (after_cast + after_scrap)
    loss_tot = supplied - after_cast - after_scrap

    # ---- Validations: same logic as cutting (tolerance 5%) ----
    tol = Decimal("0.05")

    # Rule A: before must be within ±5% of supplied
    if supplied > 0:
        if (before - supplied).copy_abs() > (supplied * tol):
            raise HTTPException(
                400,
                f"Before-cut ({before}) must be within 5% of supplied ({supplied}).",
            )

    # Rule B: (after_cast + after_scrap) must be within ±5% of before
    total_after = after_cast + after_scrap
    if before > 0:
        if (total_after - before).copy_abs() > (before * tol):
            raise HTTPException(
                400,
                "(After Cast + After Scrap) must be within 5% of Before-cut."
            )
        
    now = datetime.utcnow()
    try:
        # Upsert reconciliation with final numbers
        rec = db.execute(
            select(models.Reconciliation).where(models.Reconciliation.flask_id == flask.id)
        ).scalar_one_or_none()
        if rec:
            rec.supplied_weight = float(supplied)
            rec.before_cut_weight = float(before)
            rec.after_cast_weight = float(after_cast)
            rec.after_scrap_weight = float(after_scrap)
            rec.loss_part_i = float(loss_i)
            rec.loss_part_ii = float(loss_ii)
            rec.loss_total = float(loss_tot)
            rec.posted_by = payload.posted_by
            rec.updated_at = now
        else:
            db.add(models.Reconciliation(
                flask_id=flask.id,
                supplied_weight=float(supplied),
                before_cut_weight=float(before),
                after_cast_weight=float(after_cast),
                after_scrap_weight=float(after_scrap),
                loss_part_i=float(loss_i),
                loss_part_ii=float(loss_ii),
                loss_total=float(loss_tot),
                posted_by=payload.posted_by,
            ))

        # Update Cutting row with the final figures (keeps existing reports compatible)
        cut = db.execute(
            select(models.Cutting).where(models.Cutting.flask_id == flask.id)
        ).scalar_one_or_none()
        if cut:
            cut.before_cut_A = float(before)
            cut.after_casting_C = float(after_cast)
            cut.after_scrap_B = float(after_scrap)
            cut.loss = float(loss_tot)
            cut.posted_at = now
            cut.posted_by = payload.posted_by

        # Credit scrap to reserve (only now)
        reserve = db.query(models.ScrapReserve).filter(
            models.ScrapReserve.metal_id == flask.metal_id
        ).first()
        if not reserve:
            db.add(models.ScrapReserve(
                metal_id=flask.metal_id, qty_on_hand=float(after_scrap)
            ))
        else:
            reserve.qty_on_hand = float(reserve.qty_on_hand or 0.0) + float(after_scrap)

        # Log movement (optional but consistent with your usage elsewhere)
        db.add(models.ScrapMovement(
            metal_id=flask.metal_id,
            flask_id=flask.id,
            delta=float(after_scrap),
            source="reconciliation.add",
            created_by=payload.posted_by,
        ))

        # Advance to done
        flask.status = models.Stage.done
        flask.updated_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise

    await manager.broadcast({"event": "reconciliation_confirmed", "flask_id": flask.id})
    return {
        "flask_id": flask.id,
        "moved_to": "done",
        "loss_total": float(loss_tot),
        "scrap_added": float(after_scrap),
    }
