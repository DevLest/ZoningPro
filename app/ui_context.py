"""UI shell context for Jinja templates (navigation state, project labels).

Single responsibility: default layout/navigation values and merging into route context.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models import LCApplication
from app.permission_defs import MODULE_KEYS, ROLE_ADMIN

if TYPE_CHECKING:
    from app.models import User


def merge_shell(
    ctx: dict[str, Any],
    *,
    current_user: "User | None" = None,
    db: Session | None = None,
    **shell: Any,
) -> dict[str, Any]:
    """Merge route-specific context with shell defaults."""
    display_name = "Guest"
    is_admin = False
    if current_user is not None:
        fn = (current_user.full_name or "").strip()
        display_name = fn or current_user.username
        is_admin = getattr(current_user, "role", None) == ROLE_ADMIN
    merged_shell = dict(shell)
    if "permissions" not in merged_shell:
        if current_user is not None and db is not None:
            from app.auth import build_permission_context

            merged_shell["permissions"] = build_permission_context(db, current_user)
        else:
            merged_shell["permissions"] = {
                k: {"read": False, "write": False} for k in MODULE_KEYS
            }
    defaults: dict[str, Any] = {
        "nav_active": "dashboard",
        "sidebar_active": "overview",
        "project_title": "ZoningPro",
        "project_subtitle": "Locational clearance",
        "app_id": None,
        "show_finalize_cta": False,
        "navbar_export_href": "/export/applications.xlsx",
        "mobile_fees_href": "/",
        "current_user": current_user,
        "user_display_name": display_name,
        "is_admin": is_admin,
    }
    defaults.update(merged_shell)
    return {**ctx, **defaults}


def shell_for_application(
    row: LCApplication,
    *,
    nav_active: str,
    sidebar_active: str,
    show_finalize_cta: bool = False,
    current_user: "User | None" = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Shell context when an LC application row is the current workflow focus."""
    title = (row.project_name or "").strip() or row.lc_ctrl_no
    subtitle_parts = []
    if row.applicant_display_name and row.applicant_display_name != "—":
        subtitle_parts.append(row.applicant_display_name)
    if row.project_location:
        subtitle_parts.append(row.project_location)
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Application workspace"
    return merge_shell(
        {},
        current_user=current_user,
        db=db,
        nav_active=nav_active,
        sidebar_active=sidebar_active,
        project_title=title,
        project_subtitle=subtitle,
        app_id=row.id,
        show_finalize_cta=show_finalize_cta,
        mobile_fees_href=f"/applications/{row.id}/assessment",
    )
