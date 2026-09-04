import pytest

from src.resavac import _preostali_limit_prve_faze


def test_fallback_dobija_samo_preostali_budzet_prve_faze():
    assert _preostali_limit_prve_faze(1500.0, 1800.0, 180.0) == 1320.0


def test_stroga_faza_prvo_cuva_rezervu_za_optimizaciju():
    assert _preostali_limit_prve_faze(1500.0, 1800.0, 1200.0) == 300.0


def test_stroga_faza_moze_dobiti_rezervu_za_validan_raspored():
    assert _preostali_limit_prve_faze(1800.0, 1800.0, 1501.0) == 299.0


@pytest.mark.parametrize(
    ("limit_prve", "ukupni_limit", "proteklo", "ocekivano"),
    (
        (1500.0, 1800.0, 1501.0, 0.0),
        (1500.0, 1800.0, 1801.0, 0.0),
        (1800.0, 1200.0, 180.0, 1020.0),
    ),
)
def test_fallback_postuje_granice_budzeta(
    limit_prve, ukupni_limit, proteklo, ocekivano
):
    assert (
        _preostali_limit_prve_faze(limit_prve, ukupni_limit, proteklo)
        == ocekivano
    )
