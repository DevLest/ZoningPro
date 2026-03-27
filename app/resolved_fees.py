"""Apply manual LC fee / surcharge overrides and zoning waiver on top of computed fees."""

from __future__ import annotations

from dataclasses import dataclass

from app.fees.compute import FeeResult, compute_fees
from app.models import LCApplication


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


def display_fees_for_application(row: LCApplication) -> tuple[FeeResult, DisplayFees]:
    base = compute_fees(
        row.template_id or "",
        float(row.project_cost or 0),
        lot_area_sqm=row.lot_area_sqm,
        optional_units=row.optional_units,
    )
    eff_lc = base.lc_fee if row.lc_fee_override is None else float(row.lc_fee_override)
    eff_sur = base.surcharge if row.surcharge_override is None else float(row.surcharge_override)
    waived = bool(getattr(row, "waive_zoning_cert", False))
    eff_zc = 0.0 if waived else base.zoning_cert
    total = round(eff_lc + eff_sur + eff_zc, 2)
    disp = DisplayFees(
        lc_fee=round(eff_lc, 2),
        computed_lc_fee=base.lc_fee,
        surcharge=round(eff_sur, 2),
        zoning_cert=round(eff_zc, 2),
        total=total,
        computed_surcharge=base.surcharge,
        computed_zoning_cert=base.zoning_cert,
        surcharge_overridden=row.surcharge_override is not None,
        lc_fee_overridden=row.lc_fee_override is not None,
        zoning_waived=waived,
    )
    return base, disp
