"""Persisted app settings (JSON under data/)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, MUNICIPALITY, OFFICE, PROJECT_ROOT, ZC_ADMIN

SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_ZONING_CERTIFICATION_PRICE = 720.0

# Keys used for PDFs / printouts (per document type).
PRINT_PROFILE_KEYS = (
    "republic_label",
    "municipality_label",
    "office_label",
    "logo_static_relpath",
    "signatory_name",
    "signatory_role",
)

PRINT_PROFILE_LC = "locational_clearance"
PRINT_PROFILE_RECEIPT = "receipt"


def _default_print_profile() -> dict[str, str]:
    return {
        "republic_label": "Republic of the Philippines",
        "municipality_label": MUNICIPALITY,
        "office_label": OFFICE,
        "logo_static_relpath": "img/seal-binalbagan.png",
        "signatory_name": ZC_ADMIN,
        "signatory_role": "MPDC/Zoning Administrator",
    }


def _default_print_profiles() -> dict[str, dict[str, str]]:
    base = _default_print_profile()
    return {
        PRINT_PROFILE_LC: dict(base),
        PRINT_PROFILE_RECEIPT: dict(base),
    }


def _safe_logo_relpath(raw: str) -> str:
    s = (raw or "").strip().replace("\\", "/").lstrip("/")
    if not s or ".." in s:
        return _default_print_profile()["logo_static_relpath"]
    return s


def _merge_print_profiles(raw: Any) -> dict[str, dict[str, str]]:
    defaults = _default_print_profiles()
    if not isinstance(raw, dict):
        return defaults
    out: dict[str, dict[str, str]] = {}
    for pid in (PRINT_PROFILE_LC, PRINT_PROFILE_RECEIPT):
        base = dict(defaults[pid])
        cur = raw.get(pid)
        if isinstance(cur, dict):
            for k in PRINT_PROFILE_KEYS:
                if k in cur and isinstance(cur[k], str):
                    base[k] = cur[k].strip()
            base["logo_static_relpath"] = _safe_logo_relpath(base.get("logo_static_relpath", ""))
        out[pid] = base
    return out


def _defaults() -> dict[str, Any]:
    return {
        "zoning_certification_price": DEFAULT_ZONING_CERTIFICATION_PRICE,
        "print_profiles": _default_print_profiles(),
    }


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return _defaults()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _defaults()
    merged = _defaults()
    if isinstance(raw, dict) and "zoning_certification_price" in raw:
        try:
            v = float(raw["zoning_certification_price"])
            if v >= 0:
                merged["zoning_certification_price"] = v
        except (TypeError, ValueError):
            pass
    if isinstance(raw, dict) and "print_profiles" in raw:
        merged["print_profiles"] = _merge_print_profiles(raw["print_profiles"])
    return merged


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    if "zoning_certification_price" in updates:
        try:
            v = float(updates["zoning_certification_price"])
            if v >= 0:
                current["zoning_certification_price"] = v
        except (TypeError, ValueError):
            pass
    if "print_profiles" in updates and isinstance(updates["print_profiles"], dict):
        prev = _merge_print_profiles(current.get("print_profiles"))
        for pid in (PRINT_PROFILE_LC, PRINT_PROFILE_RECEIPT):
            inc = updates["print_profiles"].get(pid)
            if isinstance(inc, dict):
                prev[pid] = {**prev[pid], **inc}
        current["print_profiles"] = _merge_print_profiles(prev)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def get_zoning_certification_price() -> float:
    return float(load_settings()["zoning_certification_price"])


def get_print_profile(profile_id: str) -> dict[str, str]:
    """Resolved branding for a print profile (defaults + saved settings). Empty saved values fall back to defaults."""
    merged = _merge_print_profiles(load_settings().get("print_profiles"))
    prof = merged.get(profile_id) or _default_print_profile()
    defaults = _default_print_profile()
    out: dict[str, str] = {}
    for k in PRINT_PROFILE_KEYS:
        v = (prof.get(k) or "").strip()
        out[k] = v if v else defaults[k]
    out["logo_static_relpath"] = _safe_logo_relpath(out["logo_static_relpath"])
    return out


def logo_fs_path(logo_static_relpath: str) -> Path:
    """Absolute path under app/static for ReportLab / validation."""
    rel = _safe_logo_relpath(logo_static_relpath)
    return PROJECT_ROOT / "app" / "static" / rel
