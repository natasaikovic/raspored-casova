from pathlib import Path

from src.izuzeci import dozvoljen_peti_cas_solfedja
from src.model import Smena
from src.proveravac import Cas, Izvestaj, _proveri_smenu
from src.resavac import _dozvoljeni_poceci, ucitaj_standardne_ulaze


def _zahtev(ulaz, nastavnik, odeljenje):
    return next(z for z in ulaz.zahtevi if z.predmet == "Солфеђо" and z.nastavnik == nastavnik and odeljenje in z.odeljenja)


def test_peti_cas_samo_za_tri_odobrena_solfedja():
    assert dozvoljen_peti_cas_solfedja("Солфеђо", "Марија Цветковић", ("41",))
    assert dozvoljen_peti_cas_solfedja("Солфеђо", "Соња Пана Виријевић", ("42",))
    assert dozvoljen_peti_cas_solfedja("Солфеђо", "Јелена Михаиловић Красић", ("43",))
    assert not dozvoljen_peti_cas_solfedja("Солфеђо", "Ђорђина Убовић", ("31",))
    assert not dozvoljen_peti_cas_solfedja("Класичан балет", "Марија Цветковић", ("41",))


def test_solver_dozvoljava_blok_5_samo_kad_je_ta_smena_jutarnja():
    ulaz, _, nedostupnosti = ucitaj_standardne_ulaze(Path("ulazi"))
    marija = _zahtev(ulaz, "Марија Цветковић", "41")
    assert any(blok == 5 for _, blok in _dozvoljeni_poceci(marija, 1, Smena.CRVENA, nedostupnosti))
    assert all(blok != 5 for _, blok in _dozvoljeni_poceci(marija, 1, Smena.PLAVA, nedostupnosti))


def test_proveravac_prihvata_peti_cas_odobrenog_solfedja():
    ulaz, _, _ = ucitaj_standardne_ulaze(Path("ulazi"))
    zahtev = _zahtev(ulaz, "Марија Цветковић", "41")
    cas = Cas("понедељак", 5, "Солфеђо", ("41",), "Марија Цветковић", None, "KM-уч2", 2)
    izvestaj = Izvestaj()
    _proveri_smenu(cas, zahtev, Smena.CRVENA, izvestaj)
    assert not izvestaj.greske
