import csv
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from src.loader import ucitaj_nedostupnost, ucitaj_vise
from src.model import Odeljenje, Predmet, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev
from src.proveravac import (
    Cas,
    Izvestaj,
    _proveri_dusan_ilijin,
    _proveri_istoriju_jedan_cas_dnevno,
    proveri,
)
from src.resavac import napravi_model


def _cas(
    dan: str,
    blok: int,
    odeljenja: tuple[str, ...],
    nastavnik: str = "Душан Илијин",
    red: int = 2,
) -> Cas:
    return Cas(
        dan=dan,
        blok=blok,
        predmet="Историја",
        odeljenja=odeljenja,
        nastavnik=nastavnik,
        korepetitor=None,
        prostorija="KM-уч2",
        red=red,
    )


def _ulaz_dusana() -> Ulaz:
    grupe = (("I1",), ("III1",))
    zahtevi = tuple(
        Zahtev("Историја", razred, grupa, 2, 0, "Душан Илијин", None, Smena.CEO_DAN, "цео дан", i + 2)
        for i, (razred, grupa) in enumerate(zip(("I", "III"), grupe))
    )
    odeljenja = {
        oznaka: Odeljenje(oznaka, razred, Smena.CEO_DAN, Skola.SREDNJA)
        for razred, grupa in zip(("I", "III"), grupe)
        for oznaka in grupa
    }
    return Ulaz(zahtevi, odeljenja, {"Историја": Predmet("Историја", False, False)}, Skola.SREDNJA)


def _model_dusana(sa_nedeljom_b: bool = False):
    ucionica = Prostorija("KM-уч2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, "")
    return napravi_model(_ulaz_dusana(), (ucionica,), (), Smena.CRVENA, sa_nedeljom_b=sa_nedeljom_b)


def _fiksiraj(model, jedinice, promenljive, termini, nedelja_b: bool = False) -> None:
    for jedinica, (dan, blok) in zip(jedinice, termini):
        p = promenljive[jedinica.indeks]
        model.add((p.dan_b if nedelja_b else p.dan) == dan)
        model.add((p.blok_b if nedelja_b else p.blok) == blok)


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


def test_dusan_ima_ukupan_fond_14() -> None:
    with Path("ulazi/ostali_casovi.csv").open(encoding="utf-8", newline="") as f:
        redovi = [
            red
            for red in csv.DictReader(f)
            if red["предмет"] == "Историја" and red["наставник"] == "Душан Илијин"
        ]
    assert len(redovi) == 7
    assert sum(int(red["недељни фонд часова"]) for red in redovi) == 14


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


def test_proveravac_prihvata_tacno_dva_bloka_pauze() -> None:
    izvestaj = Izvestaj()
    _proveri_dusan_ilijin(
        (
            _cas("понедељак", 2, ("I1",)),
            _cas("понедељак", 5, ("III1",)),
        ),
        izvestaj,
    )
    assert izvestaj.greske == []


def test_javni_proveravac_povezuje_oba_pravila_istorije() -> None:
    ulaz = _ulaz_dusana()
    ucionica = Prostorija(
        "KM-уч2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, ""
    )
    isti_dan = (
        _cas("понедељак", 1, ("I1",)),
        _cas("понедељак", 2, ("I1",)),
        _cas("четвртак", 1, ("III1",), red=3),
        _cas("петак", 1, ("III1",), red=3),
    )
    izvestaj = proveri(ulaz, (ucionica,), (), isti_dan)
    assert any("максимум је један" in greska for greska in izvestaj.greske)

    tri_prazna = (
        _cas("понедељак", 1, ("I1",)),
        _cas("четвртак", 1, ("I1",)),
        _cas("понедељак", 5, ("III1",), red=3),
        _cas("четвртак", 2, ("III1",), red=3),
    )
    izvestaj = proveri(ulaz, (ucionica,), (), tri_prazna)
    assert any("maksimum su 2" in greska for greska in izvestaj.greske)


def test_dusan_ne_sme_utorkom_ni_sredom() -> None:
    izvestaj = Izvestaj()
    _proveri_dusan_ilijin((_cas("уторак", 4, ("IV3", "IV5")),), izvestaj)
    assert any("ponedeljkom, četvrtkom i petkom" in g for g in izvestaj.greske)


@pytest.mark.parametrize("nedelja_b", [False, True])
def test_solver_razdvaja_dva_casa_iste_grupe_po_danima(nedelja_b: bool) -> None:
    model, jedinice, promenljive = _model_dusana(sa_nedeljom_b=nedelja_b)
    _fiksiraj(
        model,
        jedinice,
        promenljive,
        [(0, 1), (0, 2), (3, 1), (3, 2)],
        nedelja_b=nedelja_b,
    )
    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


@pytest.mark.parametrize("nedelja_b", [False, True])
@pytest.mark.parametrize(
    ("termini", "ocekivani_status"),
    [
        ([(0, 1), (3, 1), (0, 4), (3, 2)], cp_model.FEASIBLE),
        ([(0, 1), (3, 1), (0, 5), (3, 2)], cp_model.INFEASIBLE),
    ],
)
def test_solver_granica_ukupnih_praznih_blokova(
    nedelja_b: bool, termini, ocekivani_status: cp_model.CpSolverStatus
) -> None:
    model, jedinice, promenljive = _model_dusana(sa_nedeljom_b=nedelja_b)
    _fiksiraj(model, jedinice, promenljive, termini, nedelja_b=nedelja_b)
    status = cp_model.CpSolver().solve(model)
    if ocekivani_status == cp_model.FEASIBLE:
        assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
    else:
        assert status == ocekivani_status
