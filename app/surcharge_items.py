"""Parse and normalize itemized surcharge lines (name + price), similar to doc requirements."""

from __future__ import annotations

import json
from typing import Any


def parse_surcharge_items(raw: str | None) -> list[dict[str, Any]]:
    """Return list of {name, price} from stored JSON; empty if missing or invalid."""
    s = (raw or "").strip()
    if not s:
        return []
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            price = float(item.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0
        if price < 0:
            price = 0.0
        out.append({"name": name, "price": round(price, 2)})
    return out


def sum_surcharge_items(items: list[dict[str, Any]]) -> float:
    return round(sum(float(i.get("price", 0)) for i in items), 2)


def normalize_surcharge_items_from_api(items: list[dict[str, Any]] | None) -> str | None:
    """Persistable JSON from API body; None if no itemized lines."""
    if not items:
        return None
    cleaned: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        try:
            price = float(item.get("price", 0))
        except (TypeError, ValueError):
            price = 0.0
        if price < 0:
            price = 0.0
        cleaned.append({"name": name, "price": round(price, 2)})
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def surcharge_items_json_for_form(
    surcharge_items_raw: str | None,
    surcharge_override: float | None,
) -> list[dict[str, Any]]:
    """Rows to show in the assessment editor: stored lines, or legacy override as one row."""
    parsed = parse_surcharge_items(surcharge_items_raw)
    if parsed:
        return parsed
    if surcharge_override is not None:
        return [{"name": "Surcharge", "price": round(float(surcharge_override), 2)}]
    return []
