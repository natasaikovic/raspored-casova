from ortools.sat.python import cp_model

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
from src.proveravac import Cas, Izvestaj, _proveri_dnevni_raspored
from src.resavac import napravi_model


KM = "Кнез Милетина 8"
SG = "Спортска гимназија"
NP = "Народно позориште"
REPERTOAR = "Репертоар класичног балета"

PROSTORIJE = (
    Prostorija("KM-уч1", KM, TipProstorije.UCIONICA, None, ""),
    Prostorija("SG-уч1", SG, TipProstorije.UCIONICA, None, ""),
    Prostorija("KM-1", KM, TipProstorije.SALA, None, ""),
    Prostorija("SG-1", SG, TipProstorije.SALA, None, ""),
    Prostorija("NP-сала", NP, TipProstorije.SALA, None, ""),
)


def _zahtev(
    predmet: str,
    fond: int,
    nastavnik: str,
    *,
    igracki: bool = False,
    red: int,
) -> Zahtev:
    return Zahtev(
        predmet=predmet,
        razred="IV",
        odeljenja=("IV1",),
        fond=fond,
        fond_korepeticije=fond if igracki else 0,
        nastavnik=nastavnik,
        korepetitor="Корепетитор" if igracki else None,
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
        red=red,
        datoteka="test.csv",
    )


def _ulaz() -> Ulaz:
    teorija = _zahtev("Теорија", 1, "Ана", red=2)
    igra = _zahtev(REPERTOAR, 2, "Мила", igracki=True, red=3)
    return Ulaz(
        (teorija, igra),
        {"IV1": Odeljenje("IV1", "IV", Smena.CEO_DAN, Skola.SREDNJA)},
        {
            teorija.predmet: Predmet(teorija.predmet, False, False),
            igra.predmet: Predmet(igra.predmet, True, True),
        },
        Skola.SREDNJA,
    )


def _greske_dnevnog_rasporeda(casovi: tuple[Cas, ...]) -> list[str]:
    izvestaj = Izvestaj()
    _proveri_dnevni_raspored(
        _ulaz(), {p.oznaka: p for p in PROSTORIJE}, casovi, izvestaj
    )
    return izvestaj.greske


def _cas(blok: int, prostorija: str, *, igra: bool = False, red: int = 2) -> Cas:
    return Cas(
        "понедељак",
        blok,
        REPERTOAR if igra else "Теорија",
        ("IV1",),
        "Мила" if igra else "Ана",
        "Корепетитор" if igra else None,
        prostorija,
        red,
    )


def test_proveravac_prihvata_neprekinut_dan_i_neposredan_prelaz_km_sg() -> None:
    casovi = (
        _cas(7, "KM-уч1"),
        _cas(8, "SG-1", igra=True, red=3),
    )

    assert _greske_dnevnog_rasporeda(casovi) == []


def test_proveravac_zabranjuje_prazan_blok_na_istoj_lokaciji() -> None:
    casovi = (
        _cas(7, "KM-уч1"),
        _cas(9, "KM-1", igra=True, red=3),
    )

    assert any("има празан час" in g for g in _greske_dnevnog_rasporeda(casovi))


def test_proveravac_prihvata_samo_blok_9_pre_np_u_bloku_10() -> None:
    casovi = (
        _cas(8, "KM-уч1"),
        _cas(10, "NP-сала", igra=True, red=3),
        _cas(11, "NP-сала", igra=True, red=4),
    )

    assert _greske_dnevnog_rasporeda(casovi) == []


def test_proveravac_zabranjuje_putni_blok_pre_np_van_bloka_9() -> None:
    casovi = (
        _cas(7, "KM-уч1"),
        _cas(9, "NP-сала", igra=True, red=3),
        _cas(10, "NP-сала", igra=True, red=4),
    )

    assert any("само у блоку 9" in g for g in _greske_dnevnog_rasporeda(casovi))


def test_proveravac_zabranjuje_pauzu_izmedju_km_i_sg() -> None:
    casovi = (
        _cas(7, "KM-уч1"),
        _cas(9, "SG-1", igra=True, red=3),
    )

    assert any("са паузом између" in g for g in _greske_dnevnog_rasporeda(casovi))


def _status_fiksiranog_modela(
    teorija_blok: int,
    igra_blok: int,
    teorija_lokacija: str,
    igra_lokacija: str,
) -> cp_model.CpSolverStatus:
    ulaz = _ulaz()
    model, jedinice, promenljive = napravi_model(
        ulaz,
        PROSTORIJE,
        (),
        Smena.CRVENA,
        samo_lokacije=True,
        sa_ciljem=False,
    )
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        promenljiva = promenljive[jedinica.indeks]
        model.add(promenljiva.dan == 0)
        if zahtev.predmet == "Теорија":
            model.add(promenljiva.blok == teorija_blok)
            model.add(promenljiva.lokacije[teorija_lokacija] == 1)
        else:
            model.add(promenljiva.blok == igra_blok)
            model.add(promenljiva.lokacije[igra_lokacija] == 1)
    return cp_model.CpSolver().solve(model)


def test_solver_dozvoljava_blok_9_samo_pre_np_u_bloku_10() -> None:
    assert _status_fiksiranog_modela(8, 10, KM, NP) in {
        cp_model.FEASIBLE,
        cp_model.OPTIMAL,
    }
    assert _status_fiksiranog_modela(7, 10, KM, NP) == cp_model.INFEASIBLE


def test_solver_zabranjuje_putni_blok_izmedju_drugih_lokacija() -> None:
    assert _status_fiksiranog_modela(8, 10, KM, SG) == cp_model.INFEASIBLE


def test_solver_dozvoljava_neposredan_prelaz_km_sg() -> None:
    assert _status_fiksiranog_modela(9, 10, KM, SG) in {
        cp_model.FEASIBLE,
        cp_model.OPTIMAL,
    }
