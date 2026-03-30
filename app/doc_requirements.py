"""Document requirements stored as JSON array on LCApplication.doc_requirements."""

from __future__ import annotations

import json
from typing import Any


def normalize_doc_requirements_post(raw: str | None) -> str | None:
    """Parse hidden field JSON from intake; keep legacy plain text as-is."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return s
    if not isinstance(data, list):
        return s
    if not data:
        return None
    cleaned: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, qty)
        cleaned.append({"name": name, "qty": qty})
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def format_doc_requirements_for_export(value: str | None) -> str:
    """Human-readable line for spreadsheets; legacy non-JSON text unchanged."""
    if not value:
        return ""
    s = value.strip()
    if not s.startswith("["):
        return s
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return s
    if not isinstance(data, list):
        return s
    parts: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            qty = 1
        qty = max(1, qty)
        parts.append(f"{name} × {qty}")
    return ", ".join(parts)
