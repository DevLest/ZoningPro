"""Module keys and labels for role-based read/write access (admin vs staff)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDef:
    key: str
    label: str
    description: str


# Order shown on the permissions screen
MODULES: tuple[ModuleDef, ...] = (
    ModuleDef(
        "dashboard",
        "Dashboard",
        "View the project overview and recent applications list.",
    ),
    ModuleDef(
        "applications",
        "Applications & fees",
        "Create and edit LC applications, site analysis, fee calculator, print/PDF.",
    ),
    ModuleDef(
        "locational_clearance",
        "Locational clearance forms",
        "LC Forms 1–2 and zoning certification (Form 03): intake, saved cases, and printouts.",
    ),
    ModuleDef(
        "settings",
        "Fee settings",
        "View and edit zoning certification fee defaults.",
    ),
    ModuleDef(
        "export",
        "Export",
        "Download the Excel export of applications.",
    ),
    ModuleDef(
        "users",
        "Users",
        "View the user list and create accounts.",
    ),
    ModuleDef(
        "permissions",
        "Role permissions",
        "Configure read/write access for the Staff role (this screen).",
    ),
)

MODULE_KEYS: frozenset[str] = frozenset(m.key for m in MODULES)

ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_STAFF)
