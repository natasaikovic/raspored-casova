from pathlib import Path

from ortools.sat.python import cp_model

from src.resavac import (
    KAZNA_ZA_SUBOTU,
    OPSTI_PREDMETI,
    _dodaj_kaznu_za_subotu,
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


def test_subota_se_naplacuje():
    kazne = []
    model = cp_model.CpModel()
    subota = model.new_bool_var("subota")
    _dodaj_kaznu_za_subotu(kazne, subota)

    model.add(subota == 1)
    model.minimize(sum(kazne))
    solver = cp_model.CpSolver()
    assert solver.solve(model) == cp_model.OPTIMAL
    assert solver.objective_value == KAZNA_ZA_SUBOTU


def test_petak_je_besplatan_a_subota_nije():
    """Uz slobodan izbor dana solver bira petak; subota mora da se isplati."""

    model = cp_model.CpModel()
    dan = model.new_int_var(0, 5, "dan")
    subota = model.new_bool_var("subota")
    model.add(dan == 5).only_enforce_if(subota)
    model.add(dan != 5).only_enforce_if(~subota)
    kazne = []
    _dodaj_kaznu_za_subotu(kazne, subota)
    model.minimize(sum(kazne))

    solver = cp_model.CpSolver()
    assert solver.solve(model) == cp_model.OPTIMAL
    assert solver.value(subota) == 0
    assert solver.objective_value == 0


def test_kazna_za_subotu_je_jaca_od_prekida_i_sale():
    """Subota se ne uzima da bi se izbegla rupa (500) ili sala van SG (500)."""

    assert KAZNA_ZA_SUBOTU > 500 + 500


def test_obavezna_subota_daje_konstantnu_kaznu():
    """Šest dvočasa na šest dana: subota je uvek tačno jednom, pa je pomeraj
    cilja isti u svakom rešenju i ne krivi izbor ostalih dana."""

    model = cp_model.CpModel()
    kazne = []
    dani = [model.new_int_var(0, 5, f"dan{i}") for i in range(6)]
    model.add_all_different(dani)
    for i, dan in enumerate(dani):
        subota = model.new_bool_var(f"subota{i}")
        model.add(dan == 5).only_enforce_if(subota)
        model.add(dan != 5).only_enforce_if(~subota)
        _dodaj_kaznu_za_subotu(kazne, subota)
    model.minimize(sum(kazne))

    solver = cp_model.CpSolver()
    assert solver.solve(model) == cp_model.OPTIMAL
    assert solver.objective_value == KAZNA_ZA_SUBOTU
