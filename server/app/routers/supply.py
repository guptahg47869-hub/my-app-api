# server/app/routers/supply.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime

from ..db import get_db
from .. import models, schemas

# websockets manager is optional
try:
    from ..websockets import manager  # type: ignore
except Exception:  # pragma: no cover
    manager = None  # type: ignore

router = APIRouter(prefix="/supply", tags=["supply"])


# ------------------ helpers ------------------
def metal_rule(metal_name: str):
    """
    Returns rule dict:
      - {'type': 'pure_only'} for Platinum/Silver
      - {'type': 'gold_ratio', 'fine': X, 'alloy': Y} for 10/14/18K
      - {'type': 'none'} otherwise
    """
    m = (metal_name or "").strip().lower()
    if not m:
        return {"type": "none"}
    if "platinum" in m or "silver" in m:
        return {"type": "pure_only"}
    if m.startswith("10"):
        return {"type": "gold_pct", "pct": 0.417}
    if m.startswith("14"):
        return {"type": "gold_pct", "pct": 0.587}
    if m.startswith("18"):
        return {"type": "gold_pct", "pct": 0.752}
    return {"type": "none"}


def ratio_ok(fine: float, alloy: float, exp_fine: int, exp_alloy: int, tol_frac: float = 0.05) -> bool:
    """Check that supplied fine:alloy is within ±5% (default) of the expected ratio."""
    total = fine + alloy
    if total <= 0:
        return True
    expected_fraction = exp_fine / (exp_fine + exp_alloy)
    actual_fraction = fine / total
    return abs(actual_fraction - expected_fraction) <= tol_frac * expected_fraction


# ------------------ queue (Prepared / Not Prepared split) ------------------
@router.get("/queue")
def supply_queue(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="optional search by flask_no or tree_no"),
):
    """
    List flasks currently in SUPPLY with:
      - prepared: bool (from MetalPrep)
      - prepped planned values (scrap_planned, fine_24k_planned, alloy_planned, pure_planned)
      - basic context (date, flask_no, metal_name, tree_no)

    UI can split rows into Prepared vs Not Prepared and pre-fill inputs from 'prepped'.
    """
    f = models.Flask
    m = models.Metal
    p = models.MetalPrep
    t = models.Tree

    stmt = (
        select(
            f.id.label("flask_id"),
            f.date,
            f.flask_no,
            m.name.label("metal_name"),
            t.tree_no.label("tree_no"),
            p.prepared.label("prepared"),
            p.scrap_planned.label("prep_scrap"),
            p.fine_24k_planned.label("prep_fine"),
            p.alloy_planned.label("prep_alloy"),
            p.pure_planned.label("prep_pure"),
        )
        .join(m, m.id == f.metal_id)
        .outerjoin(p, p.flask_id == f.id)
        .outerjoin(t, t.id == f.tree_id)
        .where(f.status == models.Stage.supply)
        .order_by(f.date.desc(), m.name.asc(), f.flask_no.asc())
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where((f.flask_no.ilike(like)) | (t.tree_no.ilike(like)))

    rows = db.execute(stmt).all()

    out = []
    for r in rows:
        out.append({
            "id": r.flask_id,
            "date": r.date.isoformat() if r.date else None,
            "flask_no": r.flask_no,
            "metal_name": r.metal_name,
            "tree_no": r.tree_no,
            "prepared": bool(r.prepared) if r.prepared is not None else False,
            "prepped": {
                "scrap_planned": float(r.prep_scrap or 0.0),
                "fine_24k_planned": float(r.prep_fine or 0.0),
                "alloy_planned": float(r.prep_alloy or 0.0),
                "pure_planned": float(r.prep_pure or 0.0),
            },
        })
    return out


# ------------------ post supply ------------------
@router.post("")
async def post_supply(payload: schemas.SupplyCreate, db: Session = Depends(get_db)):
    """
    Supply metal to a flask in SUPPLY stage:
      - Validates composition rules:
          * Pt/Ag: alloy must be 0
          * 10k/14k/18k: fine:alloy ratio within ±5%
      - Total (scrap + fine + alloy) must be within ±5% of required metal (from WaxingEntry)
      - Consumes scrap from ScrapReserve (delta on update)
      - Upserts Supply row
      - Records ScrapMovement
      - Moves flask to CASTING
    """
    # 1) Load flask and ensure stage
    flask = db.get(models.Flask, payload.flask_id)
    if not flask or flask.status != models.Stage.supply:
        raise HTTPException(status_code=400, detail="flask not in supply stage")

    # 2) Metal and required metal from WaxingEntry
    metal = db.get(models.Metal, flask.metal_id)
    metal_name = metal.name if metal else ""
    waxing = db.execute(
        select(models.WaxingEntry).where(models.WaxingEntry.flask_id == flask.id)
    ).scalar_one_or_none()
    if not waxing:
        raise HTTPException(status_code=400, detail="waxing entry missing for this flask")
    required = float(waxing.metal_weight or 0.0)

    # server/app/routers/supply.py  (inside post_supply)

    # ... you already loaded `flask`, ensured stage, loaded `metal_name` and `required`
    scrap = float(payload.scrap_supplied or 0.0)
    fine  = float(payload.fine_24k_supplied or 0.0)
    alloy = float(payload.alloy_supplied or 0.0)

    # find any prepped values
    prepped = db.execute(
        select(models.MetalPrep).where(models.MetalPrep.flask_id == flask.id)
    ).scalar_one_or_none()
    prepped_scrap = float(prepped.scrap_planned or 0.0) if (prepped and prepped.prepared) else 0.0

    # reserve row (already in your code)
    reserve = db.execute(
        select(models.ScrapReserve).where(models.ScrapReserve.metal_id == flask.metal_id)
    ).scalar_one_or_none()
    if reserve is None:
        raise HTTPException(status_code=400, detail="scrap reserve record not found for this metal")

    # ... rules + ±5% total check (keep as-is)

    existing = db.execute(
        select(models.Supply).where(models.Supply.flask_id == flask.id)
    ).scalar_one_or_none()

    now = datetime.utcnow()
    fresh = round(fine + alloy, 3)
    total_supplied = round(scrap + fresh, 3)


    try:
        if existing is None:
            # -------- NEW on CREATE: consume only the remainder after prep --------
            delta_scrap = scrap - prepped_scrap
            # if positive, we need extra from reserve; if negative, release the difference
            if delta_scrap > 0 and float(reserve.qty_on_hand or 0.0) < delta_scrap:
                raise HTTPException(status_code=400, detail="insufficient scrap reserve for supply delta")

            db.add(models.Supply(
                flask_id=flask.id,
                required_metal_weight=required,
                scrap_supplied=scrap,
                fine_24k_supplied=fine,
                alloy_supplied=alloy,
                fresh_supplied=fresh,
                posted_by=payload.posted_by,
            ))

            if abs(delta_scrap) > 1e-9:
                reserve.qty_on_hand = float(reserve.qty_on_hand or 0.0) - delta_scrap
                db.add(models.ScrapMovement(
                    metal_id=flask.metal_id,
                    flask_id=flask.id,
                    delta=-delta_scrap,  # negative: consume; positive: release back
                    source="supply.consume_delta" if delta_scrap > 0 else "supply.release_delta",
                    created_by=payload.posted_by,
                ))
        else:
            # -------- NEW on UPDATE: consume/release only the change vs previous --------
            prev_scrap = float(existing.scrap_supplied or 0.0)
            delta_scrap = scrap - prev_scrap
            if delta_scrap > 0 and float(reserve.qty_on_hand or 0.0) < delta_scrap:
                raise HTTPException(status_code=400, detail="insufficient scrap reserve for update delta")

            existing.required_metal_weight = required
            existing.scrap_supplied = scrap
            existing.fine_24k_supplied = fine
            existing.alloy_supplied = alloy
            existing.fresh_supplied = fresh
            existing.posted_by = payload.posted_by
            existing.posted_at = now

            if abs(delta_scrap) > 1e-9:
                reserve.qty_on_hand = float(reserve.qty_on_hand or 0.0) - delta_scrap
                db.add(models.ScrapMovement(
                    metal_id=flask.metal_id,
                    flask_id=flask.id,
                    delta=-delta_scrap,
                    source="supply.consume_delta" if delta_scrap > 0 else "supply.release_delta",
                    created_by=payload.posted_by,
                ))

        # move to CASTING (as in your code)
        flask.status = models.Stage.casting
        flask.updated_at = now
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # 9) Optional broadcast
    if manager:
        try:
            await manager.broadcast({"event": "supply_posted", "flask_id": flask.id})
        except Exception:
            pass

    return {
        "flask_id": flask.id,
        "required_metal_weight": float(required),
        "scrap_supplied": float(scrap),
        "fine_24k_supplied": float(fine),
        "alloy_supplied": float(alloy),
        "total_supplied": float(total_supplied),
    }
