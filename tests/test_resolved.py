from datetime import date

from app.models import LCApplication
from app.resolved_fees import display_fees_for_application


def test_waive_zoning_sets_zero_zc():
    row = LCApplication(
        lc_ctrl_no="T",
        date_of_application=date.today(),
        applicant_name="A",
        address="X",
        category="commercial",
        template_id="commercial_100k",
        project_cost=50_000.0,
        waive_zoning_cert=True,
    )
    base, disp = display_fees_for_application(row)
    assert base.zoning_cert == 500.0
    assert disp.zoning_cert == 0.0
    assert disp.zoning_waived is True
    assert disp.total == base.lc_fee + base.surcharge


def test_surcharge_override():
    row = LCApplication(
        lc_ctrl_no="T",
        date_of_application=date.today(),
        applicant_name="A",
        address="X",
        category="commercial",
        template_id="commercial_100k",
        project_cost=50_000.0,
        surcharge_override=99.5,
    )
    _base, disp = display_fees_for_application(row)
    assert disp.surcharge == 99.5
    assert disp.surcharge_overridden is True


def test_lc_fee_override():
    row = LCApplication(
        lc_ctrl_no="T",
        date_of_application=date.today(),
        applicant_name="A",
        address="X",
        category="commercial",
        template_id="commercial_100k",
        project_cost=50_000.0,
        lc_fee_override=100.0,
    )
    base, disp = display_fees_for_application(row)
    assert base.lc_fee != 100.0
    assert disp.lc_fee == 100.0
    assert disp.computed_lc_fee == base.lc_fee
    assert disp.lc_fee_overridden is True
    assert disp.total == round(100.0 + disp.surcharge + disp.zoning_cert, 2)
