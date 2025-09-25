# server/scripts/seed.py
from __future__ import annotations
import os
import sys
from pathlib import Path

# --- ensure we can import "app.*" ---
SERVER_DIR = Path(__file__).resolve().parents[1]   # .../jewelry-casting/server
REPO_ROOT = SERVER_DIR.parent                       # .../jewelry-casting
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

# --- load .env from repo root ---
try:
    from dotenv import load_dotenv
except Exception:
    raise RuntimeError('Please install python-dotenv in this venv: pip install python-dotenv')

dotenv_path = REPO_ROOT / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f'Loaded .env from: {dotenv_path}')
else:
    print('WARNING: .env not found at repo root; relying on process env.')

# --- normal app imports ---
from sqlalchemy import text
from app.db import SessionLocal, engine, Base
from app.models import Metal, ScrapReserve

NEW_METALS = [
    "10W", "10Y", "10R",
    "14W", "14Y", "14R",
    "18W", "18Y", "18R",
    "Platinum", "Silver",
]

def main():
    print('DATABASE_URL =', os.getenv('DATABASE_URL'))
    # make sure tables exist
    Base.metadata.create_all(bind=engine)

    s = SessionLocal()
    try:
        print('Resetting metals & scrap_reserves…')
        s.execute(text('TRUNCATE TABLE scrap_reserves RESTART IDENTITY CASCADE;'))
        s.execute(text('TRUNCATE TABLE metals RESTART IDENTITY CASCADE;'))
        s.commit()

        # insert metals
        metal_objs = []
        for name in NEW_METALS:
            m = Metal(name=name)
            s.add(m)
            metal_objs.append(m)
        s.commit()

        # seed reserves with 0
        for m in metal_objs:
            s.add(ScrapReserve(metal_id=m.id, qty_on_hand=0))
        s.commit()

        print('Done: metals + reserves seeded.')
        print('Metals:')
        for m in s.query(Metal).order_by(Metal.id).all():
            print(f'  {m.id}: {m.name}')

    finally:
        s.close()

if __name__ == '__main__':
    main()
