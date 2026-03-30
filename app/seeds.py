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
        ("locational_clearance", True, True),
        ("settings", False, False),
        ("export", True, False),
        ("users", False, False),
        ("permissions", False, False),
    ]


def seed_role_permissions(db: Session) -> None:
    """Insert default staff permissions if none exist; add rows for new modules on upgrade."""
    existing = {r.module_key for r in db.query(RolePermission).filter(RolePermission.role == ROLE_STAFF).all()}
    defaults = {k: (cr, cw) for k, cr, cw in _default_staff_permissions() if k in MODULE_KEYS}
    if not existing:
        for key, (cr, cw) in defaults.items():
            db.add(RolePermission(role=ROLE_STAFF, module_key=key, can_read=cr, can_write=cw))
        db.commit()
        return
    for key, (cr, cw) in defaults.items():
        if key not in existing:
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
