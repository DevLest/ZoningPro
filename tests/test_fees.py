import pytest

from app.fees import compute_fees, suggest_template
from app.settings_store import DEFAULT_ZONING_CERTIFICATION_PRICE


def test_suggest_residential():
    assert suggest_template("residential", 50_000) == "residential_100k"
    assert suggest_template("residential", 150_000) == "residential_100k_plus"
    assert suggest_template("residential", 500_000) == "residential_200k_plus"


def test_suggest_commercial():
    assert suggest_template("commercial", 50_000) == "commercial_100k"
    assert suggest_template("commercial", 200_000) == "commercial_100k_plus"
    assert suggest_template("commercial", 800_000) == "commercial_500k_plus"
    assert suggest_template("commercial", 1_500_000) == "commercial_1m_plus"
    assert suggest_template("commercial", 3_000_000) == "commercial_2m_plus"


def test_residential_200k_plus_matches_workbook_sample():
    """Excel Residential-200K+: K17=excess, K18=K17*1%, K19=K18/10, LC=base+K19; base = Settings zoning rate."""
    cost = 2_045_831.0
    base = DEFAULT_ZONING_CERTIFICATION_PRICE
    r = compute_fees("residential_200k_plus", cost, zoning_cert_price=base)
    excess = cost - 200_000.0
    k18 = excess * 0.01
    k19 = k18 * 0.1
    expected_lc = base + k19
    assert r.breakdown["k17_excess_over_200k"] == pytest.approx(excess)
    assert r.breakdown["k18_one_percent_of_excess"] == pytest.approx(k18)
    assert r.breakdown["k19_one_tenth_of_one_percent"] == pytest.approx(k19)
    assert r.lc_fee == pytest.approx(expected_lc, abs=0.02)
    assert r.zoning_cert == base
    assert r.total == pytest.approx(expected_lc + base, abs=0.02)


def test_residential_100k_plus_uses_settings_zcp():
    cost = 150_000.0
    zcp = 500.0
    r = compute_fees("residential_100k_plus", cost, zoning_cert_price=zcp)
    ex = 50_000.0
    assert r.lc_fee == pytest.approx(ex * 0.001 + zcp, abs=0.02)
    assert r.zoning_cert == pytest.approx((400.0 * 38.0) * (zcp / DEFAULT_ZONING_CERTIFICATION_PRICE), abs=0.02)


def test_commercial_2m_plus():
    cost = 1_300_000.0
    r = compute_fees("commercial_2m_plus", cost)
    k17 = max(0.0, cost - 2_000_000.0)
    assert k17 == 0.0
    assert r.lc_fee == 7200.0
    assert r.zoning_cert == 500.0


def test_commercial_2m_plus_with_excess():
    cost = 2_500_000.0
    r = compute_fees("commercial_2m_plus", cost)
    k17 = 500_000.0
    k18 = k17 * 0.01
    k19 = k18 * 0.1
    assert r.lc_fee == pytest.approx(k19 + 7200.0)
    assert r.total == pytest.approx(r.lc_fee + r.surcharge + r.zoning_cert)


def test_institutional_2m_plus_zoning():
    lot = 52146.0
    base = DEFAULT_ZONING_CERTIFICATION_PRICE
    r = compute_fees(
        "institutional_2m_plus", 3_000_000.0, lot_area_sqm=lot, zoning_cert_price=base
    )
    assert r.zoning_cert == pytest.approx((lot / 10_000.0) * base)


def test_special_use_2m_plus():
    cost = 3_058_388.05
    base = DEFAULT_ZONING_CERTIFICATION_PRICE
    r = compute_fees("special_use_2m_plus", cost, zoning_cert_price=base)
    assert r.lc_fee == pytest.approx(7200.0 + cost * 0.001)
    assert r.zoning_cert == base


def test_apartment_500k_surcharge_units():
    r = compute_fees("apartment_500k", 2_880_000.0, optional_units=100.0)
    assert r.surcharge == 1.0
    assert r.lc_fee == 2160.0
