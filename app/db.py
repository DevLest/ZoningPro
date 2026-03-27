from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATA_DIR, DB_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite_schema() -> None:
    """Add columns introduced after first deploy (SQLite has no ALTER complexity for new cols)."""
    insp = inspect(engine)
    if not insp.has_table("lc_applications"):
        return
    cols = {c["name"] for c in insp.get_columns("lc_applications")}
    with engine.begin() as conn:
        if "surcharge_override" not in cols:
            conn.execute(text("ALTER TABLE lc_applications ADD COLUMN surcharge_override REAL"))
        if "waive_zoning_cert" not in cols:
            conn.execute(text("ALTER TABLE lc_applications ADD COLUMN waive_zoning_cert BOOLEAN NOT NULL DEFAULT 0"))
        if "lc_fee_override" not in cols:
            conn.execute(text("ALTER TABLE lc_applications ADD COLUMN lc_fee_override REAL"))


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_schema()
