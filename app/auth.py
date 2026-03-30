"""Password hashing, sessions, and role-based module access (admin vs staff)."""

from __future__ import annotations

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RolePermission, User
from app.permission_defs import MODULE_KEYS, ROLE_ADMIN, ROLE_STAFF


class LoginRequired(Exception):
    """Handled by main app: redirect to /login."""


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("user_id")
    if uid is None:
        raise LoginRequired()
    u = db.get(User, int(uid))
    if u is None or not u.is_active:
        request.session.clear()
        raise LoginRequired()
    return u


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def _staff_row(db: Session, module_key: str) -> RolePermission | None:
    return (
        db.query(RolePermission)
        .filter(RolePermission.role == ROLE_STAFF, RolePermission.module_key == module_key)
        .first()
    )


def can_access_read(db: Session, user: User, module_key: str) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    row = _staff_row(db, module_key)
    if row is None:
        return False
    return bool(row.can_read or row.can_write)


def can_access_write(db: Session, user: User, module_key: str) -> bool:
    if user.role == ROLE_ADMIN:
        return True
    row = _staff_row(db, module_key)
    if row is None:
        return False
    return bool(row.can_write)


def build_permission_context(db: Session, user: User) -> dict[str, dict[str, bool]]:
    """Nested dict for templates: permissions[module_key]['read'|'write']."""
    out: dict[str, dict[str, bool]] = {}
    for key in MODULE_KEYS:
        if user.role == ROLE_ADMIN:
            out[key] = {"read": True, "write": True}
        else:
            row = _staff_row(db, key)
            if row is None:
                out[key] = {"read": False, "write": False}
            else:
                cr = bool(row.can_read or row.can_write)
                cw = bool(row.can_write)
                out[key] = {"read": cr, "write": cw}
    return out


def _make_read_dep(module_key: str):
    def dep(user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
        if not can_access_read(db, user, module_key):
            raise HTTPException(status_code=403, detail="You do not have access to this module.")
        return user

    return dep


def _make_write_dep(module_key: str):
    def dep(user: User = Depends(require_user), db: Session = Depends(get_db)) -> User:
        if not can_access_write(db, user, module_key):
            raise HTTPException(status_code=403, detail="You do not have permission to change this data.")
        return user

    return dep


require_dashboard_read = _make_read_dep("dashboard")
require_applications_read = _make_read_dep("applications")
require_applications_write = _make_write_dep("applications")
require_settings_read = _make_read_dep("settings")
require_settings_write = _make_write_dep("settings")
require_export_read = _make_read_dep("export")
require_users_read = _make_read_dep("users")
require_users_write = _make_write_dep("users")
require_locational_clearance_read = _make_read_dep("locational_clearance")
require_locational_clearance_write = _make_write_dep("locational_clearance")
