"""Address suggestions: OSM Nominatim + Photon (default), or Google Places Autocomplete."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    ADDRESS_SEARCH_SUFFIX,
    GEOCODE_BIAS_LAT,
    GEOCODE_BIAS_LON,
    GEOCODE_BIAS_RADIUS_M,
    GOOGLE_MAPS_API_KEY,
    NOMINATIM_USER_AGENT,
    PH_VIEWBOX,
)

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
PHOTON_SEARCH = "https://photon.komoot.io/api/"
GOOGLE_AUTOCOMPLETE = "https://maps.googleapis.com/maps/api/place/autocomplete/json"


# If the user names another Negros locality (or already says Binalbagan), do not append the LGU suffix.
_SKIP_LGU_SUFFIX_IF_CONTAINS = (
    "binalbagan",
    "negros occidental",
    "himamaylan",
    "kabankalan",
    "sipalay",
    "bacolod",
    "silay",
    "talisay",
    "cadiz",
    "escalante",
    "sagay",
    "san carlos",
    "murcia",
    "pulupandan",
    "valladolid",
    "la carlota",
    "bago",
    "hinigaran",
    "isabela",
    "moises padilla",
    "pontevedra",
    "la castellana",
    "san enrique",
    "toboso",
    "victorias",
    "manapla",
    "cauayan",
    "hinoba-an",
)


def _geocode_query(raw: str) -> str:
    """
    Nudge free-text toward the LGU so street/block/lot queries do not match random
    cities nationwide. Skipped when the user already names a locality.
    """
    q = (raw or "").strip()
    if not q or not ADDRESS_SEARCH_SUFFIX:
        return q
    ql = q.lower()
    if any(s in ql for s in _SKIP_LGU_SUFFIX_IF_CONTAINS):
        return q
    return f"{q}{ADDRESS_SEARCH_SUFFIX}"


def address_suggestions(query: str, *, limit: int = 8) -> tuple[list[dict[str, str]], str]:
    """
    Returns (suggestions, provider) where each suggestion has keys: label, value.
    provider is 'osm' (Nominatim + Photon), 'google', or 'none'.
    """
    q = (query or "").strip()
    if len(q) < 3:
        return [], "none"

    lim = max(1, min(limit, 10))
    gq = _geocode_query(q)
    if GOOGLE_MAPS_API_KEY:
        return _google_suggestions(gq, lim), "google"
    return _osm_combined_suggestions(gq, lim), "osm"


def _dedupe_append(
    out: list[dict[str, str]],
    seen: set[str],
    label: str,
    *,
    cap: int,
) -> None:
    key = label.casefold().strip()
    if len(key) < 3 or key in seen or len(out) >= cap:
        return
    seen.add(key)
    out.append({"label": label, "value": label})


def _parse_viewbox(vb: str) -> tuple[float, float, float, float] | None:
    parts = [p.strip() for p in vb.split(",")]
    if len(parts) != 4:
        return None
    try:
        a, b, c, d = (float(x) for x in parts)
    except ValueError:
        return None
    return (a, b, c, d)


def _nominatim_suggestions(q: str, limit: int) -> list[dict[str, str]]:
    """Country-scoped Nominatim search (single request per suggestion API call)."""
    params: dict[str, Any] = {
        "q": q,
        "format": "json",
        "limit": limit,
        "addressdetails": "1",
        "countrycodes": "ph",
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(
                NOMINATIM_SEARCH,
                params=params,
                headers={
                    "User-Agent": NOMINATIM_USER_AGENT,
                    "Accept-Language": "en",
                },
            )
            r.raise_for_status()
            data: list[dict[str, Any]] = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Nominatim request failed: %s", e)
        return []

    out: list[dict[str, str]] = []
    for row in data:
        disp = row.get("display_name")
        if isinstance(disp, str) and disp.strip():
            out.append({"label": disp.strip(), "value": disp.strip()})
    return out


def _photon_label(props: dict[str, Any]) -> str | None:
    """Build a readable line from Photon/OSM feature properties (streets, subdivisions, POIs)."""
    if not props:
        return None
    name = (props.get("name") or "").strip()
    street = (props.get("street") or "").strip()
    housenumber = (props.get("housenumber") or "").strip()
    district = (props.get("district") or props.get("county") or "").strip()
    city = (
        props.get("city")
        or props.get("town")
        or props.get("municipality")
        or props.get("village")
        or ""
    )
    city = str(city).strip()
    state = (props.get("state") or "").strip()
    postcode = (props.get("postcode") or "").strip()
    country = (props.get("country") or "").strip()

    parts: list[str] = []
    if housenumber and street:
        line = f"{housenumber} {street}"
    elif street:
        line = street
    else:
        line = ""

    if name:
        if not line or name.lower() != line.lower():
            parts.append(name)
    if line:
        parts.append(line)
    if district and district.lower() not in {p.lower() for p in parts}:
        parts.append(district)
    if city:
        parts.append(city)
    if state and state.lower() != city.lower():
        parts.append(state)
    if postcode:
        parts.append(postcode)
    if country:
        parts.append(country)

    if not parts:
        return None
    return ", ".join(parts)


def _photon_suggestions(q: str, limit: int) -> list[dict[str, str]]:
    vb = _parse_viewbox(PH_VIEWBOX)
    params: dict[str, Any] = {
        "q": q,
        "limit": limit,
        "lang": "en",
        # Prefer matches near Binalbagan / Negros when the query is ambiguous.
        "lat": GEOCODE_BIAS_LAT,
        "lon": GEOCODE_BIAS_LON,
    }
    if vb:
        min_lon, min_lat, max_lon, max_lat = vb
        params["bbox"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"

    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(
                PHOTON_SEARCH,
                params=params,
                headers={"User-Agent": NOMINATIM_USER_AGENT},
            )
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Photon request failed: %s", e)
        return []

    feats = payload.get("features") or []
    out: list[dict[str, str]] = []
    for f in feats:
        if not isinstance(f, dict):
            continue
        props = f.get("properties") or {}
        if not isinstance(props, dict):
            continue
        label = _photon_label(props)
        if label:
            out.append({"label": label, "value": label})
    return out


def _osm_combined_suggestions(q: str, limit: int) -> list[dict[str, str]]:
    """
    Merge Nominatim + Photon. Photon is listed first — it usually matches streets,
    blocks/lots, and named subdivisions better than Nominatim alone for partial input.
    """
    # Over-fetch per source so merge can still fill `limit` after deduping.
    per = min(10, max(limit + 3, 8))
    nom = _nominatim_suggestions(q, per)
    pho = _photon_suggestions(q, per)

    seen_set: set[str] = set()
    out: list[dict[str, str]] = []

    for row in pho:
        _dedupe_append(out, seen_set, row["label"], cap=limit)
    for row in nom:
        _dedupe_append(out, seen_set, row["label"], cap=limit)

    return out


def _google_suggestions(q: str, limit: int) -> list[dict[str, str]]:
    assert GOOGLE_MAPS_API_KEY
    try:
        with httpx.Client(timeout=12.0) as client:
            r = client.get(
                GOOGLE_AUTOCOMPLETE,
                params={
                    "input": q,
                    "key": GOOGLE_MAPS_API_KEY,
                    "components": "country:ph",
                    "language": "en",
                    # Bias toward Negros / Binalbagan so street + subdivision strings resolve locally.
                    "location": f"{GEOCODE_BIAS_LAT},{GEOCODE_BIAS_LON}",
                    "radius": GEOCODE_BIAS_RADIUS_M,
                },
            )
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Google Places autocomplete failed: %s", e)
        return []

    status = payload.get("status")
    if status not in ("OK", "ZERO_RESULTS"):
        logger.warning("Google Places status=%s error_message=%s", status, payload.get("error_message"))
        return []

    preds = payload.get("predictions") or []
    out: list[dict[str, str]] = []
    for p in preds[:limit]:
        desc = p.get("description")
        if isinstance(desc, str) and desc.strip():
            s = desc.strip()
            out.append({"label": s, "value": s})
    return out
