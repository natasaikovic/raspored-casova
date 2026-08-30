from pathlib import Path

from ortools.sat.python import cp_model

from src.resavac import (
    OPSTI_PREDMETI,
    _dodaj_subotnje_ogranicenje,
    _dodaj_subotnji_prioritet_sg,
    _subota_dozvoljena,
    ucitaj_standardne_ulaze,
)


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


def test_subota_ne_dozvoljava_nastavu_posle_1505():
    model = cp_model.CpModel()
    blok = model.new_int_var(1, 14, "blok")
    subota = model.new_bool_var("subota")
    kazne = []
    model.add(subota == 1)
    model.add(blok == 8)
    _dodaj_subotnje_ogranicenje(model, kazne, blok, subota, 2, "cas")

    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def test_subota_daje_prednost_sportskoj_gimnaziji():
    model = cp_model.CpModel()
    subota = model.new_bool_var("subota")
    km = model.new_bool_var("km")
    sg = model.new_bool_var("sg")
    kazne = []
    model.add(subota == 1)
    model.add_exactly_one(km, sg)
    _dodaj_subotnji_prioritet_sg(
        model,
        kazne,
        subota,
        {"Кнез Милетина 8": km, "Спортска гимназија": sg},
        "cas",
    )
    model.minimize(sum(kazne))

    solver = cp_model.CpSolver()
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.value(sg) == 1
