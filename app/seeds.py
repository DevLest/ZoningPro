"""Database seeding: default admin user and staff role permissions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import RolePermission, User
from app.permission_defs import MODULE_KEYS, ROLE_ADMIN, ROLE_STAFF


def _default_staff_permissions() -> list[tuple[str, bool, bool]]:
    """(module_key, can_read, can_write) for staff role."""
    return [
        ("dashboard", True, False),
        ("applications", True, True),
        ("settings", False, False),
        ("export", True, False),
        ("users", False, False),
        ("permissions", False, False),
    ]


def seed_role_permissions(db: Session) -> None:
    """Insert default staff permissions if none exist."""
    n = db.query(RolePermission).filter(RolePermission.role == ROLE_STAFF).count()
    if n > 0:
        return
    for key, cr, cw in _default_staff_permissions():
        if key not in MODULE_KEYS:
            continue
        db.add(RolePermission(role=ROLE_STAFF, module_key=key, can_read=cr, can_write=cw))
    db.commit()


def seed_default_admin_user(db: Session) -> None:
    """Create the built-in admin account when there are no users (first run). Password: admin / admin."""
    if db.query(User).count() > 0:
        return
    admin = User(
        username="admin",
        password_hash=hash_password("admin"),
        full_name="Administrator",
        role=ROLE_ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.commit()


def run_all_seeds(db: Session) -> None:
    """Run after migrations. Safe to call on every startup."""
    seed_role_permissions(db)
    seed_default_admin_user(db)
