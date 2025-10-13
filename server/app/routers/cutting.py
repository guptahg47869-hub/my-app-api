from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from decimal import Decimal

from ..db import get_db
from .. import models, schemas
from ..websockets import manager

router = APIRouter(prefix="/cutting", tags=["cutting"])


@router.post("")
async def post_cutting(payload: schemas.CuttingCreate, db: Session = Depends(get_db)):
    """
    Cutting now STAGES the result to Reconciliation (no reserve/loss side-effects here).
    Expected payload:
    {
      "flask_id": 1,
      "before_cut_A": 100.0,
      "after_scrap_B": 5.0,
      "after_casting_C": 92.0,
      "posted_by": "cutter1"
    }
    """
    if payload.flask_id is None:
        raise HTTPException(422, "flask_id required")

    flask = db.get(models.Flask, payload.flask_id)
    if not flask or flask.status != models.Stage.cutting:
        raise HTTPException(400, "Flask not in cutting stage")

    # basic input validation (strong checks will happen at Reconciliation)
    try:
        A = Decimal(str(payload.before_cut_A or 0))
        B = Decimal(str(payload.after_scrap_B or 0))
        C = Decimal(str(payload.after_casting_C or 0))
    except Exception:
        raise HTTPException(400, "Invalid numeric values")

    if A < 0 or B < 0 or C < 0:
        raise HTTPException(400, "Weights must be >= 0")

    # --- Compute supplied weight from Supply (scrap + fine24k/pure + alloy)
    sup_row = db.execute(
        select(models.Supply).where(models.Supply.flask_id == flask.id)
    ).scalar_one_or_none()

    supplied = Decimal("0.000")
    if sup_row:
        supplied += Decimal(str(getattr(sup_row, "scrap_supplied", 0) or 0))
        # 'fine_24k_supplied' for gold; 'pure_supplied' for Pt/Ag (fallback)
        fine_or_pure = getattr(sup_row, "fine_24k_supplied", None)
        if fine_or_pure is None:
            fine_or_pure = getattr(sup_row, "pure_supplied", 0)
        supplied += Decimal(str(fine_or_pure or 0))
        supplied += Decimal(str(getattr(sup_row, "alloy_supplied", 0) or 0))

    # --- 5% validations --------------------------------------------------------
    # 1) A (before_cut) must be within 5% of supplied
    if supplied <= Decimal('0'):
        raise HTTPException(400, "No supplied weight found for this flask. Supply before cutting.")
    delta_as = abs(A - supplied)
    if delta_as > (supplied * Decimal('0.05')):
        raise HTTPException(
            400,
            f"Before-cut weight must be within 5% of supplied ({float(supplied):.3f}). "
            f"Got before={float(A):.3f}, supplied={float(supplied):.3f}."
        )

    # 2) (B+C) must be within 5% of A
    delta_bc = abs((B + C) - A)
    if A > Decimal('0') and delta_bc > (A * Decimal('0.05')):
        raise HTTPException(
            400,
            "Sum of after-cut weights (casting + scrap) must be within 5% of before-cut weight. "
            f"Got before={float(A):.3f}, after_sum={float(B+C):.3f}."
        )
    # (scrap loss can be negative; we do not block that)

    # loss components for preview (final checks will be at Recon)
    loss_i = supplied - A                               # (i) supplied - before
    loss_ii = A - (B + C)                               # (ii) before - (after_cast + after_scrap)
    loss_total = supplied - (B + C)                     # (i) + (ii)

    now = datetime.utcnow()
    try:
        # Upsert Cutting row (so historical inputs remain visible)
        cut = db.execute(
            select(models.Cutting).where(models.Cutting.flask_id == flask.id)
        ).scalar_one_or_none()
        if cut:
            cut.before_cut_A = float(A)
            cut.after_scrap_B = float(B)
            cut.after_casting_C = float(C)
            # keep an informative preview value (will be finalized at recon)
            cut.loss = float(loss_total)
            cut.posted_at = now
            cut.posted_by = payload.posted_by
        else:
            db.add(models.Cutting(
                flask_id=flask.id,
                before_cut_A=float(A),
                after_scrap_B=float(B),
                after_casting_C=float(C),
                loss=float(loss_total),   # provisional; finalized at recon
                posted_by=payload.posted_by,
            ))

        # Upsert Reconciliation staging record with SAME values
        r = db.execute(
            select(models.Reconciliation).where(models.Reconciliation.flask_id == flask.id)
        ).scalar_one_or_none()
        if r:
            r.supplied_weight = float(supplied)
            r.before_cut_weight = float(A)
            r.after_cast_weight = float(C)
            r.after_scrap_weight = float(B)
            r.loss_part_i = float(loss_i)
            r.loss_part_ii = float(loss_ii)
            r.loss_total = float(loss_total)
            r.posted_by = payload.posted_by
            r.updated_at = now
        else:
            db.add(models.Reconciliation(
                flask_id=flask.id,
                supplied_weight=float(supplied),
                before_cut_weight=float(A),
                after_cast_weight=float(C),
                after_scrap_weight=float(B),
                loss_part_i=float(loss_i),
                loss_part_ii=float(loss_ii),
                loss_total=float(loss_total),
                posted_by=payload.posted_by,
            ))

        # Advance to reconciliation (NO scrap movement / NO final booking here)
        flask.status = models.Stage.reconciliation
        flask.updated_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise

    await manager.broadcast({"event": "cutting_staged", "flask_id": flask.id})
    return {
        "flask_id": flask.id,
        "moved_to": "reconciliation",
        "preview": {
            "supplied": float(supplied),
            "before": float(A),
            "after_cast": float(C),
            "after_scrap": float(B),
            "loss_i": float(loss_i),
            "loss_ii": float(loss_ii),
            "loss_total": float(loss_total),
        },
    }
