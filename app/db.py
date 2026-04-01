from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATA_DIR, DATABASE_URL, DB_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


if DATABASE_URL:
    normalized_database_url = DATABASE_URL
    if normalized_database_url.startswith("postgresql://") and "+psycopg" not in normalized_database_url:
        normalized_database_url = normalized_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(
        normalized_database_url,
        pool_pre_ping=True,
    )
else:
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
    )

IS_SQLITE = engine.dialect.name == "sqlite"
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite_schema() -> None:
    """Add columns introduced after first deploy (SQLite has no ALTER complexity for new cols)."""
    if not IS_SQLITE:
        return
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
        if "address_lat" not in cols:
            conn.execute(text("ALTER TABLE lc_applications ADD COLUMN address_lat REAL"))
        if "address_lon" not in cols:
            conn.execute(text("ALTER TABLE lc_applications ADD COLUMN address_lon REAL"))
        if "surcharge_items" not in cols:
            conn.execute(text("ALTER TABLE lc_applications ADD COLUMN surcharge_items TEXT"))


def _migrate_users_roles() -> None:
    """Add users.role from legacy is_admin; role_permissions table is created by create_all."""
    insp = inspect(engine)
    if not insp.has_table("users"):
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "role" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'staff'"))
        if "is_admin" in cols:
            conn.execute(text("UPDATE users SET role = 'admin' WHERE is_admin != 0"))
            conn.execute(text("UPDATE users SET role = 'staff' WHERE role IS NULL OR role = ''"))


def _migrate_applicants_fk() -> None:
    """Add applicant_id to lc_applications, backfill from legacy applicant_name, drop old column when possible."""
    from sqlalchemy import text

    from app.models import Applicant

    insp = inspect(engine)
    if not insp.has_table("lc_applications"):
        return
    cols = {c["name"] for c in insp.get_columns("lc_applications")}
    has_legacy_name = "applicant_name" in cols

    if "applicant_id" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE lc_applications ADD COLUMN applicant_id INTEGER REFERENCES applicants(id)")
            )

    db = SessionLocal()
    try:
        if has_legacy_name:
            rows = db.execute(
                text("SELECT id, applicant_name FROM lc_applications WHERE applicant_id IS NULL")
            ).all()
            for rid, legacy_raw in rows:
                legacy_name = (legacy_raw or "").strip() or "Unknown"
                ap = (
                    db.query(Applicant)
                    .filter(Applicant.first_name == "")
                    .filter(Applicant.last_name == legacy_name)
                    .filter(Applicant.middle_name.is_(None))
                    .filter(Applicant.suffix.is_(None))
                    .first()
                )
                if not ap:
                    ap = Applicant(first_name="", last_name=legacy_name, middle_name=None, suffix=None)
                    db.add(ap)
                    db.flush()
                db.execute(
                    text("UPDATE lc_applications SET applicant_id = :aid WHERE id = :id"),
                    {"aid": ap.id, "id": rid},
                )
            db.commit()

        if has_legacy_name:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE lc_applications DROP COLUMN applicant_name"))
            except Exception:
                pass
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_schema()
    _migrate_users_roles()
    _migrate_applicants_fk()
