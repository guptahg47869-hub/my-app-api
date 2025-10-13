# server/app/routers/metal_prep.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, conint, confloat  # local model to avoid schema drift
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime

from ..db import get_db
from .. import models
from ..websockets import manager


router = APIRouter(prefix="/metal-prep", tags=["metal-prep"])


class MetalPrepPost(BaseModel):
    flask_id: conint(gt=0)                          # type: ignore
    prepared: bool
    scrap_planned: confloat(ge=0) = 0.0             # type: ignore
    fine_24k_planned: confloat(ge=0) = 0.0          # type: ignore
    alloy_planned: confloat(ge=0) = 0.0             # type: ignore
    pure_planned: confloat(ge=0) = 0.0              # type: ignore
    posted_by: str


def _rule_for_metal(name: str | None):
    """
    Decide rule set for a given metal name.
    Gold (10/14/18*) => ratio on remaining (required - scrap)
    Platinum/Silver  => pure only
    """
    n = (name or "").strip().lower()
    if n in ("platinum", "silver"):
        return ("pure_only", None)
    if n.startswith("10"):
        return ("gold_pct", 0.417)
    if n.startswith("14"):
        return ("gold_pct", 0.587)
    if n.startswith("18"):
        return ("gold_pct", 0.752)
    return ("none", None)


@router.get("/preset/{flask_id}")
def get_preset(flask_id: int, db: Session = Depends(get_db)):
    """
    Return any prepped values for a flask (or zeros if none), plus context:
    - date, flask_no, metal name, required metal weight
    """
    flask = db.get(models.Flask, flask_id)
    if not flask:
        raise HTTPException(status_code=404, detail="Flask not found")

    metal = db.get(models.Metal, flask.metal_id)

    waxing = db.execute(
        select(models.WaxingEntry).where(models.WaxingEntry.flask_id == flask.id)
    ).scalar_one_or_none()

    prep = db.execute(
        select(models.MetalPrep).where(models.MetalPrep.flask_id == flask.id)
    ).scalar_one_or_none()

    return {
        "flask_id": flask.id,
        "flask_no": flask.flask_no,
        "date": flask.date.isoformat() if flask.date else None,
        "metal_id": flask.metal_id,
        "metal_name": metal.name if metal else None,
        "required_metal_weight": float(waxing.metal_weight) if waxing else 0.0,
        "prepared": bool(prep.prepared) if prep else False,
        # store as *_planned, consistent with table naming
        "scrap_planned": float(prep.scrap_planned or 0.0) if prep else 0.0,
        "fine_24k_planned": float(prep.fine_24k_planned or 0.0) if prep else 0.0,
        "alloy_planned": float(prep.alloy_planned or 0.0) if prep else 0.0,
        "pure_planned": float(prep.pure_planned or 0.0) if prep else 0.0,
    }


@router.post("")
async def post_prep(payload: MetalPrepPost, db: Session = Depends(get_db)):
    """
    Create/update MetalPrep row; move flask to SUPPLY.
    If prepared=True, enforce validations:
      - total within ±5% of required
      - ratio for gold on (required - scrap)
      - scrap availability in reserve
    If prepared=False, skip validations.
    """
    flask = db.get(models.Flask, payload.flask_id)
    if not flask:
        raise HTTPException(404, detail="Flask not found")

    # must be in metal_prep stage to post from here
    if flask.status != models.Stage.metal_prep:
        raise HTTPException(400, detail=f"Flask is not in metal_prep (currently {flask.status}).")

    metal = db.get(models.Metal, flask.metal_id)

    waxing = db.execute(
        select(models.WaxingEntry).where(models.WaxingEntry.flask_id == flask.id)
    ).scalar_one_or_none()
    required = float(waxing.metal_weight) if waxing else 0.0

    # Only validate when actually preparing
    if payload.prepared:
        tol = required * 0.05  # ±5%

        scrap = float(payload.scrap_planned or 0.0)
        fine  = float(payload.fine_24k_planned or 0.0)
        alloy = float(payload.alloy_planned or 0.0)
        pure  = float(payload.pure_planned or 0.0)

        # scrap availability
        reserve = db.query(models.ScrapReserve).filter(
            models.ScrapReserve.metal_id == flask.metal_id
        ).first()
        available_scrap = float(reserve.qty_on_hand or 0.0) if reserve else 0.0
        if scrap > 0 and scrap > available_scrap:
            raise HTTPException(
                400,
                detail=f"Not enough scrap in reserve. Need {scrap:.3f}, have {available_scrap:.3f}.",
            )

        rule, parts = _rule_for_metal(metal.name if metal else None)

        # total check
        if rule == "pure_only":
            total = scrap + pure
        elif rule == "gold_pct":
            total = scrap + fine + alloy
        else:
            total = scrap + pure  # safe default

        if abs(total - required) > tol:
            raise HTTPException(
                400,
                detail=f"Total {total:.3f} differs from required {required:.3f} by more than 5%.",
            )

        # ratio check for gold
        if rule == "gold_pct":
            # fine_part, alloy_part = parts
            karat_pct = float(parts or 0.0)
            remain = max(required - scrap, 0.0)
            # denom = fine_part + alloy_part
            # expected_fine = (remain * (fine_part / denom)) if denom else 0.0
            expected_fine = remain * karat_pct
            expected_alloy = remain - expected_fine
            leg_tol = remain * 0.05  # ±5% window on the remain piece

            if abs(fine - expected_fine) > leg_tol or abs(alloy - expected_alloy) > leg_tol:
                raise HTTPException(
                    400,
                    detail=(
                        f"Fine/Alloy must follow {karat_pct:.3f} fine of remaining. "
                        f"Expected ≈ {expected_fine:.1f}/{expected_alloy:.1f} for remain {remain:.1f}."                    
                    ),
                )

    # upsert MetalPrep row (do not touch reserves here)
    existing = db.execute(
        select(models.MetalPrep).where(models.MetalPrep.flask_id == flask.id)
    ).scalar_one_or_none()

    now = datetime.utcnow()
    
    # -------- NEW: delta-based reserve hold/release when prepared=True --------
    # previous reservation:
    prev_prepared = bool(existing.prepared) if existing else False
    prev_reserved = float(existing.scrap_planned or 0.0) if existing else 0.0
    # new reservation target:
    new_prepared = bool(payload.prepared)
    new_reserved = float(payload.scrap_planned or 0.0)

    target_reserved = new_reserved if new_prepared else 0.0
    prev_effective = prev_reserved if prev_prepared else 0.0
    delta_hold = target_reserved - prev_effective  # +ve = take from reserve, -ve = release

    # find reserve row for this metal
    reserve = db.query(models.ScrapReserve)\
                .filter(models.ScrapReserve.metal_id == flask.metal_id)\
                .first()

    try:
        # when actually changing a reservation:
        if abs(delta_hold) > 1e-9:
            if reserve is None:
                if delta_hold > 0:
                    raise HTTPException(400, detail="No scrap reserve for this metal.")
                # releasing to a non-existing row shouldn't happen; create if you prefer
                reserve = models.ScrapReserve(metal_id=flask.metal_id, qty_on_hand=0.0)
                db.add(reserve)
                db.flush()

            if delta_hold > 0 and float(reserve.qty_on_hand or 0.0) < delta_hold:
                raise HTTPException(400, detail="Not enough scrap in reserve for preparation hold.")

            # apply hold/release
            reserve.qty_on_hand = float(reserve.qty_on_hand or 0.0) - delta_hold
            db.add(models.ScrapMovement(
                metal_id=flask.metal_id,
                flask_id=flask.id,
                delta=-delta_hold,  # negative means we took from reserve
                source="prep.hold" if delta_hold > 0 else "prep.release",
                created_by=payload.posted_by,
            ))

        # upsert MetalPrep
        if existing:
            existing.prepared = new_prepared
            existing.scrap_planned = new_reserved
            existing.fine_24k_planned = float(payload.fine_24k_planned or 0.0)
            existing.alloy_planned = float(payload.alloy_planned or 0.0)
            existing.pure_planned = float(payload.pure_planned or 0.0)
            existing.posted_at = now
            existing.posted_by = payload.posted_by
        else:
            db.add(models.MetalPrep(
                flask_id=flask.id,
                prepared=new_prepared,
                scrap_planned=new_reserved,
                fine_24k_planned=float(payload.fine_24k_planned or 0.0),
                alloy_planned=float(payload.alloy_planned or 0.0),
                pure_planned=float(payload.pure_planned or 0.0),
                posted_at=now,
                posted_by=payload.posted_by,
            ))

        # advance to SUPPLY
        flask.status = models.Stage.supply
        flask.updated_at = now

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    await manager.broadcast({"event": "metal_prep_posted", "flask_id": flask.id})

    return {"flask_id": flask.id, "moved_to": models.Stage.supply.value, "prepared": new_prepared}