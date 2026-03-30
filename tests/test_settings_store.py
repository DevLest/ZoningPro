import json

import pytest

from app.fees.compute import compute_fees
from app.settings_store import (
    DEFAULT_ZONING_CERTIFICATION_PRICE,
    PRINT_PROFILE_LC,
    get_print_profile,
    get_zoning_certification_price,
    load_settings,
    save_settings,
)


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings_store.SETTINGS_PATH", tmp_path / "settings.json")
    s = load_settings()
    assert s["zoning_certification_price"] == DEFAULT_ZONING_CERTIFICATION_PRICE
    assert get_zoning_certification_price() == DEFAULT_ZONING_CERTIFICATION_PRICE
    assert PRINT_PROFILE_LC in s["print_profiles"]
    assert s["print_profiles"][PRINT_PROFILE_LC]["municipality_label"]
    assert get_print_profile(PRINT_PROFILE_LC)["signatory_name"]


def test_save_and_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr("app.settings_store.SETTINGS_PATH", path)
    save_settings({"zoning_certification_price": 850.0})
    assert path.exists()
    assert load_settings()["zoning_certification_price"] == 850.0
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["zoning_certification_price"] == 850.0


def test_print_profiles_save_merge(tmp_path, monkeypatch):
    monkeypatch.setattr("app.settings_store.SETTINGS_PATH", tmp_path / "settings.json")
    save_settings(
        {
            "print_profiles": {
                PRINT_PROFILE_LC: {
                    "signatory_name": "Jane Q. Public, EnP",
                    "signatory_role": "Zoning Administrator",
                },
            },
        }
    )
    s = load_settings()
    assert s["print_profiles"][PRINT_PROFILE_LC]["signatory_name"] == "Jane Q. Public, EnP"
    assert get_print_profile(PRINT_PROFILE_LC)["signatory_name"] == "Jane Q. Public, EnP"


def test_compute_uses_zoning_cert_price_override():
    r = compute_fees("commercial_500k_plus", 600_000.0, zoning_cert_price=1000.0)
    assert r.zoning_cert == 1000.0
    assert r.breakdown["zoning_certification_price"] == 1000.0


def test_compute_institutional_plus_scales_lot_rate():
    lot = 10_000.0
    r = compute_fees("institutional_2m_plus", 3_000_000.0, lot_area_sqm=lot, zoning_cert_price=900.0)
    assert r.zoning_cert == pytest.approx(900.0)
