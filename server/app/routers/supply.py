# server/app/routers/supply.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime

from ..db import get_db
from .. import models, schemas
from ..websockets import manager

router = APIRouter(prefix="/supply", tags=["supply"])

# ----- helpers -----
def metal_rule(metal_name: str):
    """Return a dict describing the rule for this metal."""
    if not metal_name:
        return {"type": "none"}
    m = metal_name.strip().lower()

    # platinum / silver: NO alloy at all
    if m in ("platinum", "silver"):
        return {"type": "pure_only"}  # alloy must be zero

    # gold alloys by karat: expected 24k:alloy ratio with 5% tolerance
    # 10K => 5:7, 14K => 7:5, 18K => 3:1
    if m.startswith("10"):
        return {"type": "gold_ratio", "fine": 5, "alloy": 7}
    if m.startswith("14"):
        return {"type": "gold_ratio", "fine": 7, "alloy": 5}
    if m.startswith("18"):
        return {"type": "gold_ratio", "fine": 3, "alloy": 1}

    return {"type": "none"}

def within_ratio(fine: float, alloy: float, fine_expected: int, alloy_expected: int, tol=0.05) -> bool:
    """Check if fine:alloy matches the given ratio within tolerance.
    We compare the fine fraction vs expected fine fraction."""
    total_fresh = fine + alloy
    if total_fresh <= 0:
        # nothing to check (e.g., all scrap); caller will verify grand total separately
        return True
    expected_fraction = fine_expected / (fine_expected + alloy_expected)  # e.g., 5/12, 7/12, 3/4
    actual_fraction = fine / total_fresh
    # relative tolerance around expected fraction
    return abs(actual_fraction - expected_fraction) <= tol * expected_fraction

@router.post("")
async def post_supply(payload: schemas.SupplyCreate, db: Session = Depends(get_db)):
    # 0) Load flask + stage
    flask = db.get(models.Flask, payload.flask_id)
    if not flask or flask.status != models.Stage.supply:
        raise HTTPException(400, "flask not in supply stage")

    # Load the metal (to apply rules)
    metal = db.get(models.Metal, flask.metal_id)
    metal_name = metal.name if metal else ""

    # 1) Required target from Waxing
    waxing = db.execute(
        select(models.WaxingEntry).where(models.WaxingEntry.flask_id == flask.id)
    ).scalar_one_or_none()
    if not waxing:
        raise HTTPException(400, "waxing entry missing for this flask")
    required = float(waxing.metal_weight)  # single source of truth

    # 2) Reserve check (for this flask's metal)
    reserve = db.execute(
        select(models.ScrapReserve).where(models.ScrapReserve.metal_id == flask.metal_id)
    ).scalar_one_or_none()
    if not reserve or float(reserve.qty_on_hand) < payload.scrap_supplied:
        raise HTTPException(400, "insufficient scrap reserve")

    # 3) ratio / composition rules per metal
    fine = float(payload.fine_24k_supplied or 0.0)
    alloy = float(payload.alloy_supplied or 0.0)
    scrap = float(payload.scrap_supplied)

    rule = metal_rule(metal_name)
    if rule["type"] == "pure_only":
        # platinum or silver: alloy must be 0 (allow tiny rounding noise)
        if alloy > 1e-3:
            raise HTTPException(400, f"{metal_name} must have alloy=0")
    elif rule["type"] == "gold_ratio":
        if not within_ratio(fine, alloy, rule["fine"], rule["alloy"], tol=0.05):
            f, a = rule["fine"], rule["alloy"]
            raise HTTPException(400, f"{metal_name}: fine:alloy must be {f}:{a} (±5%)")
    # type none => no extra constraint

    # 4) ±5% total check against required weight
    total = round(scrap + fine + alloy, 3)
    lo, hi = required * 0.95, required * 1.05
    if not (lo <= total <= hi):
        raise HTTPException(
            400,
            f"total supplied ({total:.3f}) must be within ±5% of required ({required:.3f})"
        )

    now = datetime.utcnow()

    # 5) Upsert into metal_supply (one row per flask)
    existing = db.execute(
        select(models.Supply).where(models.Supply.flask_id == flask.id)
    ).scalar_one_or_none()

    fresh = round(fine + alloy, 3)
    
    try:
        if existing is None:
            db.add(models.Supply(
                flask_id=flask.id,
                required_metal_weight=required,
                scrap_supplied=scrap,
                fine_24k_supplied=fine,
                alloy_supplied=alloy,
                fresh_supplied=fresh,
                posted_by=payload.posted_by,
            ))
            # Deduct scrap (only once)
            reserve.qty_on_hand = float(reserve.qty_on_hand) - scrap
        else:
            # If you prefer one-and-done, replace with:
            # raise HTTPException(409, "supply already posted for this flask")
            delta_scrap = scrap - float(existing.scrap_supplied)
            if delta_scrap > 0 and float(reserve.qty_on_hand) < delta_scrap:
                raise HTTPException(400, "insufficient scrap reserve for update delta")
            reserve.qty_on_hand = float(reserve.qty_on_hand) - delta_scrap

            existing.required_metal_weight = required
            existing.scrap_supplied = scrap
            existing.fine_24k_supplied = fine
            existing.alloy_supplied = alloy
            existing.fresh_supplied = fresh
            existing.posted_at = now
            existing.posted_by = payload.posted_by

        # Optional movement log for scrap consumption
        db.add(models.ScrapMovement(
            metal_id=flask.metal_id,
            flask_id=flask.id,
            delta=-scrap if existing is None else -delta_scrap,
            source="supply.consume",
            created_by=payload.posted_by
        ))

        # Advance to casting
        flask.status = models.Stage.casting
        flask.updated_at = now

        db.commit()
    except Exception:
        db.rollback()
        raise

    await manager.broadcast({"event": "supply_posted", "flask_id": flask.id})

    return {
        "flask_id": flask.id,
        "required_metal_weight": float(required),
        "scrap_supplied": float(scrap),
        "fine_24k_supplied": float(fine),
        "alloy_supplied": float(alloy),
        "total_supplied": float(total),
    }
