# server/app/db.py
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# --------------------------------------------------------------------------------------
# Load .env from either <project_root>/.env or <project_root>/server/.env
# --------------------------------------------------------------------------------------
SERVER_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_DIR.parent
ENV_CANDIDATES = [PROJECT_ROOT / ".env", SERVER_DIR / ".env"]

def _load_env():
    loaded_any = False
    try:
        from dotenv import load_dotenv
        for p in ENV_CANDIDATES:
            if p.exists():
                load_dotenv(p, override=False)
                loaded_any = True
    except Exception:
        for p in ENV_CANDIDATES:
            if p.exists():
                for line in p.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
                loaded_any = True
    return loaded_any

_load_env()

# --------------------------------------------------------------------------------------
# Database setup
# --------------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL missing. Ensure .env exists with something like:\n"
        "DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/jewelry"
    )

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --------------------------------------------------------------------------------------
# Dependency for FastAPI routes
# --------------------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
