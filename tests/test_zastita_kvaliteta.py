from dataclasses import replace

import pytest

import src.resavac as resavac_mod
from src.model import (
    Odeljenje,
    Predmet,
    Prostorija,
    Skola,
    Smena,
    TipProstorije,
    Ulaz,
    Zahtev,
)
from src.proveravac import Cas, Izvestaj, proveri
from src.resavac import (
    Rezultat,
    _izaberi_najbolji_kandidat,
    _izaberi_sa_regresionom_granicom,
    _hint_postuje_medjunedeljne_invarijante,
    _kandidat_originalnog_hinta,
    _materijalizuj_kandidata_faze_1,
    _validan_kandidat_para,
)


CAS = Cas(
    dan="понедељак",
    blok=1,
    predmet="Предмет",
    odeljenja=("I1",),
    nastavnik="Наставник",
    korepetitor=None,
    prostorija="KM-уч2",
    red=2,
)


def _par(
    naziv: str,
    upozorenja_a: int,
    upozorenja_b: int,
    greske_a: int = 0,
    greske_b: int = 0,
):
    def rezultat(upozorenja: int, greske: int) -> Rezultat:
        return Rezultat(
            naziv,
            (CAS,),
            Izvestaj(
                greske=["greška"] * greske,
                upozorenja=["upozorenje"] * upozorenja,
            ),
            None,
        )

    return naziv, rezultat(upozorenja_a, greske_a), rezultat(
        upozorenja_b, greske_b
    )


def test_faza_2_pobedjuje_kada_ima_manje_upozorenja():
    faza_1 = _par("FAZA 1", 5, 5)
    faza_2 = _par("FAZA 2", 4, 5)

    assert _izaberi_najbolji_kandidat((faza_1, faza_2)) is faza_2


def test_faza_1_pobedjuje_kada_faza_2_ima_vise_upozorenja():
    faza_1 = _par("FAZA 1", 5, 5)
    faza_2 = _par("FAZA 2", 6, 5)

    assert _izaberi_najbolji_kandidat((faza_1, faza_2)) is faza_1


def test_isti_broj_upozorenja_daje_prednost_fazi_2():
    faza_1 = _par("FAZA 1", 5, 5)
    faza_2 = _par("FAZA 2", 6, 4)

    assert _izaberi_najbolji_kandidat((faza_1, faza_2)) is faza_2


def test_kandidat_sa_greskom_se_odbacuje_bez_obzira_na_upozorenja():
    faza_1 = _par("FAZA 1", 5, 5)
    faza_2 = _par("FAZA 2", 0, 0, greske_a=1)

    assert _izaberi_najbolji_kandidat((faza_1, faza_2)) is faza_1


def test_validan_hint_pobedjuje_losiju_fazu_2_i_ne_pokrece_fazu_1():
    hint = _par("HINT", 3, 3)
    faza_2 = _par("FAZA 2", 4, 4)

    def ne_sme_se_pozvati():
        raise AssertionError("faza 1 ne treba da se materijalizuje uz validan hint")

    assert (
        _izaberi_sa_regresionom_granicom(faza_2, hint, ne_sme_se_pozvati)
        is hint
    )


def test_nevalidan_hint_aktivira_materijalizaciju_faze_1():
    hint = _par("HINT", 0, 0, greske_b=1)
    faza_1 = _par("FAZA 1", 3, 3)
    pozivi = 0

    def napravi_fazu_1():
        nonlocal pozivi
        pozivi += 1
        return faza_1

    assert _izaberi_sa_regresionom_granicom(None, hint, napravi_fazu_1) is faza_1
    assert pozivi == 1


def test_neuspesna_dodela_faze_2_vraca_fazu_1():
    faza_1 = _par("FAZA 1", 3, 3)
    pozivi = 0

    def napravi_fazu_1():
        nonlocal pozivi
        pozivi += 1
        return faza_1

    assert (
        _izaberi_sa_regresionom_granicom(None, None, napravi_fazu_1)
        is faza_1
    )
    assert pozivi == 1


KM = "Кнез Милетина 8"
UCIONICE = (
    Prostorija("KM-уч1", KM, TipProstorije.UCIONICA, None, ""),
    Prostorija("KM-уч2", KM, TipProstorije.UCIONICA, None, ""),
)


def _srednjoskolski_ulaz() -> Ulaz:
    zahtev = Zahtev(
        predmet="Теорија",
        razred="први",
        odeljenja=("I1",),
        fond=1,
        fond_korepeticije=0,
        nastavnik="Мила",
        korepetitor=None,
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
        red=2,
    )
    return Ulaz(
        (zahtev,),
        {"I1": Odeljenje("I1", "први", Smena.CEO_DAN, Skola.SREDNJA)},
        {zahtev.predmet: Predmet(zahtev.predmet, False, False)},
        Skola.SREDNJA,
    )


def _srednjoskolski_cas(dan: str, prostorija: str) -> Cas:
    return Cas(
        dan=dan,
        blok=1,
        predmet="Теорија",
        odeljenja=("I1",),
        nastavnik="Мила",
        korepetitor=None,
        prostorija=prostorija,
        red=2,
    )


@pytest.mark.parametrize(
    "cas_b",
    (
        _srednjoskolski_cas("уторак", "KM-уч1"),
        _srednjoskolski_cas("понедељак", "KM-уч2"),
    ),
    ids=("drugi-termin", "druga-soba"),
)
def test_pojedinacno_validan_hint_odbija_medjunedeljnu_razliku(cas_b):
    ulaz = _srednjoskolski_ulaz()
    cas_a = _srednjoskolski_cas("понедељак", "KM-уч1")
    assert proveri(ulaz, UCIONICE, (), (cas_a,), Smena.CRVENA).ispravan
    assert proveri(ulaz, UCIONICE, (), (cas_b,), Smena.PLAVA).ispravan

    kandidat = _kandidat_originalnog_hinta(
        ulaz, UCIONICE, (), (cas_a,), (cas_b,)
    )

    assert kandidat is not None
    assert not _validan_kandidat_para(kandidat)


def test_medjunedeljna_provera_ne_zavisi_od_redosleda_odeljenja():
    osnova = _srednjoskolski_ulaz()
    ulaz = Ulaz(
        osnova.zahtevi,
        {
            **osnova.odeljenja,
            "I2": Odeljenje("I2", "први", Smena.CEO_DAN, Skola.SREDNJA),
        },
        osnova.predmeti,
        osnova.skola,
    )
    cas_a = replace(
        _srednjoskolski_cas("понедељак", "KM-уч1"),
        odeljenja=("I1", "I2"),
    )
    cas_b = replace(cas_a, odeljenja=("I2", "I1"))

    assert _hint_postuje_medjunedeljne_invarijante(ulaz, (cas_a,), (cas_b,))


def test_faza_1_prosledjuje_stari_limit_prostorija_od_60_sekundi(monkeypatch):
    prosledjeno = {}
    marker = _par("FAZA 1", 0, 0)

    def lazna_materijalizacija(*args, **kwargs):
        prosledjeno["naziv"] = args[0]
        prosledjeno["limit"] = kwargs["vremensko_ogranicenje_prostorija"]
        return marker

    monkeypatch.setattr(
        resavac_mod,
        "_materijalizuj_kandidata_obe_nedelje",
        lazna_materijalizacija,
    )

    rezultat = _materijalizuj_kandidata_faze_1(
        object(), object(), (), (), broj_radnika=1
    )

    assert rezultat is marker
    assert prosledjeno == {"naziv": "FAZA 1", "limit": 60}
