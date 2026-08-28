from pathlib import Path

from src.proveravac import OPSTI_PREDMETI
from src.resavac import ucitaj_standardne_ulaze


def test_validator_pravilno_razlikuje_opste_i_strucne_predmete():
    assert "Традиционално певање" not in OPSTI_PREDMETI
    assert "Етнологија" not in OPSTI_PREDMETI
    assert "Српски језик и књижевност" in OPSTI_PREDMETI


def test_iii5_nema_gradjansko_u_ulazu():
    ulaz, _, _ = ucitaj_standardne_ulaze(Path("ulazi"))
    assert any(z.predmet == "Верска настава" and "III5" in z.odeljenja for z in ulaz.zahtevi)
    assert not any(z.predmet == "Грађанско васпитање" and "III5" in z.odeljenja for z in ulaz.zahtevi)
