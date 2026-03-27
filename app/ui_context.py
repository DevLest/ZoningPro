"""UI shell context for Jinja templates (navigation state, project labels).

Single responsibility: default layout/navigation values and merging into route context.
"""
from __future__ import annotations

from typing import Any

from app.models import LCApplication


def merge_shell(ctx: dict[str, Any], **shell: Any) -> dict[str, Any]:
    """Merge route-specific context with shell defaults."""
    defaults: dict[str, Any] = {
        "nav_active": "dashboard",
        "sidebar_active": "overview",
        "project_title": "ZoningPro",
        "project_subtitle": "Locational clearance",
        "app_id": None,
        "show_finalize_cta": False,
        "navbar_export_href": "/export/applications.xlsx",
        "mobile_fees_href": "/",
        "user_display_name": "Admin User",
    }
    defaults.update(shell)
    return {**ctx, **defaults}


def shell_for_application(
    row: LCApplication,
    *,
    nav_active: str,
    sidebar_active: str,
    show_finalize_cta: bool = False,
) -> dict[str, Any]:
    """Shell context when an LC application row is the current workflow focus."""
    title = (row.project_name or "").strip() or row.lc_ctrl_no
    subtitle_parts = []
    if row.applicant_name:
        subtitle_parts.append(row.applicant_name)
    if row.project_location:
        subtitle_parts.append(row.project_location)
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else "Application workspace"
    return merge_shell(
        {},
        nav_active=nav_active,
        sidebar_active=sidebar_active,
        project_title=title,
        project_subtitle=subtitle,
        app_id=row.id,
        show_finalize_cta=show_finalize_cta,
        mobile_fees_href=f"/applications/{row.id}/assessment",
    )
