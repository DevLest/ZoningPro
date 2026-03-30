import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Used for signed session cookies; set ZONINGPRO_SECRET_KEY in production.
SECRET_KEY = os.environ.get("ZONINGPRO_SECRET_KEY", "dev-zoningpro-secret-change-in-production")
DATA_DIR = PROJECT_ROOT / "data"
EXPORTS_DIR = PROJECT_ROOT / "exports"
DB_PATH = DATA_DIR / "zoning.db"

MUNICIPALITY = "Municipality of Binalbagan"
OFFICE = "MUNICIPAL PLANNING & DEVELOPMENT OFFICE"
ZC_ADMIN = "PEARL ANGELI P. FUENTES, EnP"

# Optional: Google Cloud API key with Places API enabled. If unset, address suggestions use
# OpenStreetMap Nominatim (free; respect ~1 req/s — the UI debounces requests).
# Create key: Google Cloud Console → APIs & Services → enable "Places API" → Credentials.
GOOGLE_MAPS_API_KEY = (os.environ.get("ZONINGPRO_GOOGLE_MAPS_API_KEY") or "").strip()

# Nominatim requires a valid User-Agent identifying the application (see OSM usage policy).
NOMINATIM_USER_AGENT = os.environ.get(
    "ZONINGPRO_NOMINATIM_USER_AGENT",
    "ZoningPro/1.0 (local government zoning; contact: edit-in-production)",
)

# Philippines bounding box for Photon (min_lon, min_lat, max_lon, max_lat). Narrows free-text search.
PH_VIEWBOX = os.environ.get("ZONINGPRO_PH_VIEWBOX", "116.0,4.6,127.0,21.2")

# Bias Google Places Autocomplete toward Binalbagan / Negros (helps street + subdivision text).
GEOCODE_BIAS_LAT = float(os.environ.get("ZONINGPRO_GEOCODE_BIAS_LAT", "10.195"))
GEOCODE_BIAS_LON = float(os.environ.get("ZONINGPRO_GEOCODE_BIAS_LON", "122.858"))
GEOCODE_BIAS_RADIUS_M = int(os.environ.get("ZONINGPRO_GEOCODE_BIAS_RADIUS_M", "120000"))

# Appended to geocode queries when the user has not already named the locality — keeps block/street
# suggestions relevant to this LGU. Set ZONINGPRO_ADDRESS_SEARCH_SUFFIX= to disable.
_raw_suffix = os.environ.get("ZONINGPRO_ADDRESS_SEARCH_SUFFIX")
if _raw_suffix is None:
    ADDRESS_SEARCH_SUFFIX = ", Binalbagan, Negros Occidental, Philippines"
else:
    ADDRESS_SEARCH_SUFFIX = _raw_suffix.strip()
