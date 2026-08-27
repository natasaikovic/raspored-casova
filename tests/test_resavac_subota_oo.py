from pathlib import Path

from src.resavac import OPSTI_PREDMETI, _subota_dozvoljena, ucitaj_standardne_ulaze


def _zahtev(ulaz, predmet, odeljenje):
    return next(
        z for z in ulaz.zahtevi
        if z.predmet == predmet and odeljenje in z.odeljenja
    )


def test_strucni_neigracki_predmeti_nisu_opsteobrazovni():
    assert "Традиционално певање" not in OPSTI_PREDMETI
    assert "Етнологија" not in OPSTI_PREDMETI
    assert "Солфеђо" not in OPSTI_PREDMETI
    assert "Српски језик и књижевност" in OPSTI_PREDMETI
    assert "Математика" in OPSTI_PREDMETI


def test_subota_samo_igracki_kb_i_si():
    ulaz, _, _ = ucitaj_standardne_ulaze(Path("ulazi"))
    assert _subota_dozvoljena(
        _zahtev(ulaz, "Класичан балет – главни предмет", "I1"), ulaz
    )
    assert _subota_dozvoljena(
        _zahtev(ulaz, "Савремена игра – главни предмет", "I3"), ulaz
    )
    assert not _subota_dozvoljena(
        _zahtev(ulaz, "Народна игра – главни предмет", "I5"), ulaz
    )
    assert not _subota_dozvoljena(
        _zahtev(ulaz, "Српски језик и књижевност", "I1"), ulaz
    )
