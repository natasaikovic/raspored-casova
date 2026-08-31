from pathlib import Path

from src.loader import ucitaj_nedostupnost, ucitaj_vise
from src.proveravac import (
    Cas,
    Izvestaj,
    _proveri_dusan_ilijin,
    _proveri_istoriju_jedan_cas_dnevno,
)


def _cas(dan: str, blok: int, odeljenja: tuple[str, ...], nastavnik: str = "Душан Илијин") -> Cas:
    return Cas(
        dan=dan,
        blok=blok,
        predmet="Историја",
        odeljenja=odeljenja,
        nastavnik=nastavnik,
        korepetitor=None,
        prostorija="KM-уч2",
        red=2,
    )


def test_dusan_preuzima_iv3_iv5() -> None:
    ulaz = ucitaj_vise([
        Path("ulazi/osnovna_baletska_skola.csv"),
        Path("ulazi/srednja_baletska_skola.csv"),
        Path("ulazi/ostali_casovi.csv"),
    ])
    zahtev = next(
        z for z in ulaz.zahtevi
        if z.predmet == "Историја" and z.odeljenja == ("IV3", "IV5")
    )
    assert zahtev.nastavnik == "Душан Илијин"
    assert zahtev.fond == 2


def test_dusan_je_nedostupan_utorkom_i_sredom() -> None:
    stavke = ucitaj_nedostupnost(Path("ulazi/nedostupnost.csv"))
    nedostupni = {
        n.dan for n in stavke
        if n.nastavnik == "Душан Илијин" and n.od_bloka == 1 and n.do_bloka == 14
    }
    assert {"уторак", "среда", "субота"} <= nedostupni


def test_istorija_ne_sme_dvaput_istog_dana() -> None:
    izvestaj = Izvestaj()
    _proveri_istoriju_jedan_cas_dnevno(
        (
            _cas("понедељак", 3, ("IV3", "IV5")),
            _cas("понедељак", 5, ("IV3", "IV5")),
        ),
        izvestaj,
    )
    assert izvestaj.greske
    assert any("максимум је један" in g for g in izvestaj.greske)


def test_dusan_sme_najvise_dva_bloka_pauze() -> None:
    izvestaj = Izvestaj()
    _proveri_dusan_ilijin(
        (
            _cas("понедељак", 2, ("I1", "I2", "I3")),
            _cas("понедељак", 5, ("I4", "I5")),  # dva prazna bloka
            _cas("четвртак", 3, ("III1", "III3")),
            _cas("четвртак", 5, ("III2", "III4")),  # još jedan: ukupno 3
        ),
        izvestaj,
    )
    assert any("maksimum su 2" in g for g in izvestaj.greske)


def test_dusan_ne_sme_utorkom_ni_sredom() -> None:
    izvestaj = Izvestaj()
    _proveri_dusan_ilijin((_cas("уторак", 4, ("IV3", "IV5")),), izvestaj)
    assert any("ponedeljkom, četvrtkom i petkom" in g for g in izvestaj.greske)
