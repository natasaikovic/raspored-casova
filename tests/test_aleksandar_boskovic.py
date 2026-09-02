import csv
from pathlib import Path

from ortools.sat.python import cp_model

from src.model import Odeljenje, Predmet, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev
from src.proveravac import ALEKSANDAR_BOSKOVIC, Cas, Izvestaj, _proveri_aleksandra_boskovica
from src.resavac import napravi_model


def _cas(dan, blok, odeljenja, red):
    return Cas(dan, blok, "Историја", odeljenja, ALEKSANDAR_BOSKOVIC, None, "KM-уч2", red)


def _model_aleksandra():
    grupe = (("II1", "II3"), ("II2", "II4"), ("II5",))
    zahtevi = tuple(
        Zahtev("Историја", "II", grupa, 2, 0, ALEKSANDAR_BOSKOVIC, None, Smena.CEO_DAN, "цео дан", i + 2)
        for i, grupa in enumerate(grupe)
    )
    odeljenja = {
        oznaka: Odeljenje(oznaka, "II", Smena.CEO_DAN, Skola.SREDNJA)
        for grupa in grupe for oznaka in grupa
    }
    ulaz = Ulaz(zahtevi, odeljenja, {"Историја": Predmet("Историја", False, False)}, Skola.SREDNJA)
    ucionica = Prostorija("KM-уч2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, "")
    return napravi_model(ulaz, (ucionica,), (), Smena.CRVENA)


def _fiksiraj(model, jedinice, promenljive, dani_i_blokovi):
    for jedinica, (dan, blok) in zip(jedinice, dani_i_blokovi):
        model.add(promenljive[jedinica.indeks].dan == dan)
        model.add(promenljive[jedinica.indeks].blok == blok)


def test_ulaz_dodeljuje_aleksandru_sve_tri_grupe_drugog_razreda():
    with Path("ulazi/ostali_casovi.csv").open(encoding="utf-8", newline="") as f:
        redovi = list(csv.DictReader(f))
    istorija = [r for r in redovi if r["предмет"] == "Историја" and r["наставник"] == ALEKSANDAR_BOSKOVIC]
    assert len(istorija) == 3
    assert {r["разред"] for r in istorija} == {"II"}
    assert sum(int(r["недељни фонд часова"]) for r in istorija) == 6
    assert {r["одељење"] for r in istorija} == {"II1,II3", "II2,II4", "II5"}


def test_aleksandar_je_nedostupan_pre_sedmog_bloka_radnim_danima():
    with Path("ulazi/nedostupnost.csv").open(encoding="utf-8", newline="") as f:
        redovi = [r for r in csv.DictReader(f) if r["наставник"] == ALEKSANDAR_BOSKOVIC]
    assert len(redovi) == 5
    assert {r["дан"] for r in redovi} == {"понедељак", "уторак", "среда", "четвртак", "петак"}
    assert all(r["од блока"] == "1" and r["до блока"] == "6" for r in redovi)


def test_proveravac_prihvata_dva_dana_po_tri_uzastopna_casa():
    casovi = []
    red = 2
    for dan in ("понедељак", "четвртак"):
        for blok, grupa in zip((7, 8, 9), (("II1", "II3"), ("II2", "II4"), ("II5",))):
            casovi.append(_cas(dan, blok, grupa, red))
            red += 1
    izvestaj = Izvestaj()
    _proveri_aleksandra_boskovica(casovi, izvestaj)
    assert izvestaj.greske == []


def test_proveravac_odbija_rupu_u_aleksandrovom_trocasu():
    casovi = [
        _cas("понедељак", 7, ("II1", "II3"), 2),
        _cas("понедељак", 8, ("II2", "II4"), 3),
        _cas("понедељак", 10, ("II5",), 4),
        _cas("четвртак", 7, ("II1", "II3"), 5),
        _cas("четвртак", 8, ("II2", "II4"), 6),
        _cas("четвртак", 9, ("II5",), 7),
    ]
    izvestaj = Izvestaj()
    _proveri_aleksandra_boskovica(casovi, izvestaj)
    assert any("3 uzastopna" in greska for greska in izvestaj.greske)


def test_proveravac_odbija_tri_dana_i_ponovljenu_grupu():
    casovi = [
        _cas("понедељак", 7, ("II1", "II3"), 2),
        _cas("понедељак", 8, ("II1", "II3"), 3),
        _cas("понедељак", 9, ("II5",), 4),
        _cas("уторак", 7, ("II2", "II4"), 5),
        _cas("уторак", 8, ("II5",), 6),
        _cas("среда", 7, ("II1", "II3"), 7),
    ]
    izvestaj = Izvestaj()
    _proveri_aleksandra_boskovica(casovi, izvestaj)
    assert any("tačno dva dana" in greska for greska in izvestaj.greske)
    assert any("sve tri grupe" in greska for greska in izvestaj.greske)


def test_solver_prihvata_dva_dana_sa_sve_tri_grupe_uzastopno():
    model, jedinice, promenljive = _model_aleksandra()
    _fiksiraj(model, jedinice, promenljive, [(0, 7), (3, 7), (0, 8), (3, 8), (0, 9), (3, 9)])
    assert cp_model.CpSolver().solve(model) in (cp_model.FEASIBLE, cp_model.OPTIMAL)


def test_solver_odbija_cas_pre_sedmog_bloka():
    model, jedinice, promenljive = _model_aleksandra()
    model.add(promenljive[jedinice[0].indeks].blok == 6)
    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def test_solver_odbija_tri_radna_dana():
    model, jedinice, promenljive = _model_aleksandra()
    _fiksiraj(model, jedinice, promenljive, [(0, 7), (1, 7), (0, 8), (1, 8), (2, 7), (2, 8)])
    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def test_solver_odbija_rupu_u_trocasu():
    model, jedinice, promenljive = _model_aleksandra()
    _fiksiraj(model, jedinice, promenljive, [(0, 7), (3, 7), (0, 8), (3, 8), (0, 10), (3, 9)])
    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE
