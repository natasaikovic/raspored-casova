from src.resavac import _preostali_limit_prve_faze


def test_fallback_dobija_samo_preostali_budzet_prve_faze():
    assert _preostali_limit_prve_faze(1500.0, 1800.0, 180.0) == 1320.0
