# Jewelry Casting API (MVP)

FastAPI + PostgreSQL starter implementing the **Waxing → Supply** flow with real-time broadcasts and scrap reserve accounting.

## What’s included
- Docker Compose (Postgres + API)
- SQLAlchemy models and constraints (unique `date + flask_no`)
- Endpoints:
  - `POST /waxing`
  - `POST /supply`
  - `GET /queue/{stage}`
- WebSocket: `ws://localhost:8000/ws`
- Seed script for metals and scrap reserves

## Prereqs
- Docker + Docker Compose
- (Optional) Python 3.11+ if you want to run scripts locally

## Quick start
```bash
# from project root
docker compose up -d db
docker compose up --build api
```

Open Swagger UI: http://localhost:8000/docs

### Seed metals & reserves
```bash
docker compose exec api python scripts/seed.py
```

### Try the flow
1. **Waxing** — POST `/waxing`
```json
{
  "date": "2025-09-17",
  "flask_no": "F-001",
  "metal_id": 1,
  "gasket_weight": 10.5,
  "tree_weight": 25.2,
  "posted_by": "waxer1"
}
```
Response returns `flask_id` and `metal_weight`. The flask status becomes `supply`.

2. **Check the queue** — GET `/queue/supply`

3. **Top up scrap reserve** (temporary for MVP)
Open a shell and update directly (or add an endpoint later):
```bash
docker compose exec api python -c "from app.db import SessionLocal, engine, Base; from app.models import *; Base.metadata.create_all(bind=engine); s=SessionLocal(); r=s.query(ScrapReserve).filter_by(metal_id=1).first(); r.qty_on_hand=100; s.commit(); s.close(); print('added scrap');"
```

4. **Supply** — POST `/supply`
```json
{
  "flask_id": 1,
  "scrap_supplied": 5.0,
  "posted_by": "supply1"
}
```

### WebSocket (optional test)
Connect a WS client to `ws://localhost:8000/ws` to receive `waxing_posted` and `supply_posted` events.

## Next steps
- Add Casting / Quenching / Cutting routes (same pattern).
- Switch to Alembic migrations.
- Add auth & role-based access.
- Build a UI (NiceGUI/Reflex or desktop client).
