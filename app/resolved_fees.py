"""Apply manual LC fee / surcharge overrides and zoning waiver on top of computed fees."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.fees.compute import FeeResult, compute_fees
from app.models import LCApplication
from app.surcharge_items import parse_surcharge_items, sum_surcharge_items, surcharge_items_json_for_form


@dataclass(frozen=True)
class DisplayFees:
    lc_fee: float
    computed_lc_fee: float
    surcharge: float
    zoning_cert: float
    total: float
    computed_surcharge: float
    computed_zoning_cert: float
    surcharge_overridden: bool
    lc_fee_overridden: bool
    zoning_waived: bool
    #: True when surcharge comes from stored itemized JSON (name + price lines).
    surcharge_itemized: bool
    #: Lines for print slip / detailed table when itemized; else one line when surcharge > 0.
    surcharge_lines: tuple[dict[str, Any], ...]
    #: Rows for the assessment editor (syncs with API).
    surcharge_items: tuple[dict[str, Any], ...]


def display_fees_for_application(row: LCApplication) -> tuple[FeeResult, DisplayFees]:
    base = compute_fees(
        row.template_id or "",
        float(row.project_cost or 0),
        lot_area_sqm=row.lot_area_sqm,
        optional_units=row.optional_units,
    )
    eff_lc = base.lc_fee if row.lc_fee_override is None else float(row.lc_fee_override)
    raw_items = getattr(row, "surcharge_items", None)
    parsed = parse_surcharge_items(raw_items)
    if parsed:
        eff_sur = sum_surcharge_items(parsed)
        itemized = True
        sur_over = True
    elif row.surcharge_override is not None:
        eff_sur = float(row.surcharge_override)
        itemized = False
        sur_over = True
    else:
        eff_sur = base.surcharge
        itemized = False
        sur_over = False

    waived = bool(getattr(row, "waive_zoning_cert", False))
    eff_zc = 0.0 if waived else base.zoning_cert
    total = round(eff_lc + eff_sur + eff_zc, 2)

    if itemized:
        lines_for_slip = tuple({"name": p["name"], "price": p["price"]} for p in parsed)
    elif eff_sur > 0:
        lines_for_slip = ({"name": "Surcharge", "price": round(eff_sur, 2)},)
    else:
        lines_for_slip = ()

    edit_items = surcharge_items_json_for_form(raw_items, row.surcharge_override)

    disp = DisplayFees(
        lc_fee=round(eff_lc, 2),
        computed_lc_fee=base.lc_fee,
        surcharge=round(eff_sur, 2),
        zoning_cert=round(eff_zc, 2),
        total=total,
        computed_surcharge=base.surcharge,
        computed_zoning_cert=base.zoning_cert,
        surcharge_overridden=sur_over,
        lc_fee_overridden=row.lc_fee_override is not None,
        zoning_waived=waived,
        surcharge_itemized=itemized,
        surcharge_lines=lines_for_slip,
        surcharge_items=tuple(edit_items),
    )
    return base, disp
