from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker


import os

# Use a dynamic path that works on both Windows and Linux (Cloud)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "certificates.db"

# Favor an external DATABASE_URL (for Postgres on Neon/Render)
# Fallback to local SQLite if none provided
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# Fix SQLAlchemy 1.4+ Postgres prefix issue if it exists
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Connect args only needed for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL, connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db() -> None:
    """
    Create tables and apply lightweight SQLite migrations for existing databases.
    This keeps the project 'run immediately' without requiring Alembic.
    """
    # Create new tables (does not alter existing tables)
    Base.metadata.create_all(bind=engine)

    # Lightweight migrations for participants table columns
    with engine.connect() as conn:
        # Only run these migration checks on SQLite
        if not DATABASE_URL.startswith("sqlite"):
            return

        table_check = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='participants'")
        ).fetchone()
        if not table_check:
            return

        cols = conn.execute(text("PRAGMA table_info(participants)")).fetchall()
        existing_cols = {row[1] for row in cols}  # row[1] is column name

        if "display_name" not in existing_cols:
            conn.execute(text("ALTER TABLE participants ADD COLUMN display_name VARCHAR(255)"))
        if "last_sent_at" not in existing_cols:
            conn.execute(text("ALTER TABLE participants ADD COLUMN last_sent_at DATETIME"))
        if "attempts" not in existing_cols:
            # SQLite requires DEFAULT if we want NOT NULL on add
            conn.execute(text("ALTER TABLE participants ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"))
        if "certificate_file" not in existing_cols:
            conn.execute(text("ALTER TABLE participants ADD COLUMN certificate_file VARCHAR(500)"))

        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

