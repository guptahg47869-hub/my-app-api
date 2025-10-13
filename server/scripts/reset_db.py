# server/scripts/reset_db.py
import sys, os
from pathlib import Path

# Ensure we can import "app" package
SERVER_DIR = Path(__file__).resolve().parents[1]   # .../<project>/server
PROJECT_ROOT = SERVER_DIR.parent                   # .../<project>
sys.path.insert(0, str(SERVER_DIR))

# Load .env (prefer project root, then server/)
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    for p in [PROJECT_ROOT / ".env", SERVER_DIR / ".env"]:
        if p.exists():
            load_dotenv(p, override=True)
            print(f"Loaded .env from: {p}")
            break
except Exception:
    pass

# Optional: last-resort default for local dev if .env wasn't found
os.environ.setdefault("DATABASE_URL", "postgresql://jewelry_db_0xb1_user:Q12QnalVgyvo2zy7cFf3Y1O7EbzGh2xl@dpg-d3ajdabipnbc739ljt1g-a/jewelry_db_0xb1")
#os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/jewelry")

print("DATABASE_URL seen by reset_db.py =>", os.getenv("DATABASE_URL"))

from app.db import engine
from app.models import Base

def main():
    print("Dropping all tables…")
    Base.metadata.drop_all(bind=engine)
    print("Recreating tables from current models…")
    Base.metadata.create_all(bind=engine)
    print("DB reset complete.")

if __name__ == "__main__":
    main()


