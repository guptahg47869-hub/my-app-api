from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..db import get_db
from .. import models

router = APIRouter(prefix="/metals", tags=["metals"])

@router.get("")
def list_metals(db: Session = Depends(get_db)):
  rows = db.execute(select(models.Metal).order_by(models.Metal.name)).scalars().all()
  return [{"id": m.id, "name": m.name} for m in rows]
