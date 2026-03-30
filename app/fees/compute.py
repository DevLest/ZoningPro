from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.fees.registry import get_template
from app.settings_store import DEFAULT_ZONING_CERTIFICATION_PRICE, get_zoning_certification_price


@dataclass
class FeeResult:
    lc_fee: float
    surcharge: float
    zoning_cert: float
    total: float
    breakdown: dict[str, Any]
    template_label: str


def _excess_chain(cost: float, threshold: float) -> tuple[float, float, float]:
    """K17, K18, K19 style: excess, 1% of excess, 10% of that."""
    k17 = max(0.0, cost - threshold)
    k18 = k17 * 0.01
    k19 = k18 * 0.1
    return k17, k18, k19


def compute_fees(
    template_id: str,
    project_cost: float,
    lot_area_sqm: float | None = None,
    optional_units: float | None = None,
    *,
    zoning_cert_price: float | None = None,
) -> FeeResult:
    """Compute fees. *zoning_cert_price* defaults to Settings → zoning certification amount."""
    zcp = float(zoning_cert_price) if zoning_cert_price is not None else get_zoning_certification_price()
    meta = get_template(template_id)
    cost = float(project_cost)
    lot = float(lot_area_sqm) if lot_area_sqm is not None else 0.0
    units = float(optional_units) if optional_units is not None else 0.0

    b: dict[str, Any] = {
        "project_cost": cost,
        "template_id": template_id,
        "zoning_certification_price": zcp,
    }

    lc = sur = zc = 0.0

    if template_id == "residential_100k":
        lc = round(cost * 0.0011, 2)
        sur = 0.0
        zc = 500.0
        b["note"] = "LC fee ≈ 0.11% of project cost (from workbook sample)"

    elif template_id == "residential_100k_plus":
        ex = max(0.0, cost - 100_000.0)
        lc = ex * 0.001 + zcp
        sur = 0.0
        # Workbook used 400×38 at the default zoning rate; scale if Settings differs.
        zc = (400.0 * 38.0) * (zcp / DEFAULT_ZONING_CERTIFICATION_PRICE)
        b["excess_over_100k"] = ex

    elif template_id == "residential_200k_plus":
        # Matches Excel Residential-200K+: K17=excess over ₱200K, K18=K17*1%, K19=K18/10 (1 tenth),
        # LC Fee (C18/P17) = base + K19 — same as base + (excess × 0.001) when base equals the configured rate.
        k17, k18, k19 = _excess_chain(cost, 200_000.0)
        lc = zcp + k19
        sur = 0.0
        zc = zcp
        b["k17_excess_over_200k"] = k17
        b["k18_one_percent_of_excess"] = k18
        b["k19_one_tenth_of_one_percent"] = k19
        b["p17_lc_fee"] = lc
        b["excel_note"] = (
            f"LC Fee = {zcp} + K19 ({zcp} + one-tenth of 1% of excess over ₱200K)"
        )

    elif template_id == "apartment_500k":
        lc = 2160.0
        sur = units * 0.01
        zc = 500.0
        b["optional_units"] = units

    elif template_id == "apartment_500k_plus":
        lc = 2160.0
        sur = 0.0
        zc = 500.0

    elif template_id == "apartment_2m_plus":
        k17, k18, k19 = _excess_chain(cost, 2_000_000.0)
        lc = 3600.0 + k19
        sur = 0.0
        zc = zcp
        b.update({"k17": k17, "k18": k18, "k19": k19})

    elif template_id == "dormitory_2m":
        lc = 2160.0
        sur = 0.0
        zc = 300.0

    elif template_id == "dormitory_2m_plus":
        k17, k18, k19 = _excess_chain(cost, 2_000_000.0)
        lc = 3600.0 + k19
        sur = 0.0
        zc = zcp
        b.update({"k17": k17, "k18": k18, "k19": k19})

    elif template_id == "commercial_100k":
        lc = 1440.0
        sur = 0.0
        zc = 500.0

    elif template_id == "commercial_100k_plus":
        lc = 2160.0
        sur = 0.0
        zc = 500.0

    elif template_id == "commercial_500k_plus":
        lc = 2880.0
        sur = 0.0
        zc = zcp

    elif template_id == "commercial_1m_plus":
        lc = 4320.0
        sur = 0.0
        zc = zcp

    elif template_id == "commercial_2m_plus":
        k17, k18, k19 = _excess_chain(cost, 2_000_000.0)
        lc = k19 + 7200.0
        sur = 0.0
        zc = 500.0
        b.update({"k17": k17, "k18": k18, "k19": k19})

    elif template_id == "institutional_2m":
        lc = 2880.0
        sur = 0.0
        zc = zcp

    elif template_id == "institutional_2m_plus":
        k17, k18, k19 = _excess_chain(cost, 2_000_000.0)
        lc = 2880.0 + k19
        sur = 0.0
        zc = (lot / 10_000.0) * zcp
        b.update({"k17": k17, "k18": k18, "k19": k19, "lot_area_sqm": lot})

    elif template_id == "special_use_2m":
        lc = 7200.0
        sur = 0.0
        zc = 500.0

    elif template_id == "special_use_2m_plus":
        lc = 7200.0 + (cost * 0.001)
        sur = 0.0
        zc = zcp
        b["cost_component_0_1pct"] = cost * 0.001

    else:
        raise ValueError(f"Unknown template_id: {template_id}")

    total = round(lc + sur + zc, 2)
    return FeeResult(
        lc_fee=round(lc, 2),
        surcharge=round(sur, 2),
        zoning_cert=round(zc, 2),
        total=total,
        breakdown=b,
        template_label=meta.label,
    )
