from ortools.sat.python import cp_model

from src.resavac import (
    _TelemetrijaFaze2,
    _ispisi_zavrsnu_telemetriju_faze_2,
    _relativni_gap,
)


def test_telemetrija_ispisuje_incumbent_i_zavrsne_pokazatelje(capsys):
    model = cp_model.CpModel()
    izbor = model.new_bool_var("izbor")
    model.minimize(izbor)

    solver = cp_model.CpSolver()
    telemetrija = _TelemetrijaFaze2()
    status = solver.solve(model, telemetrija)
    _ispisi_zavrsnu_telemetriju_faze_2(solver, status)

    izlaz = capsys.readouterr().out
    assert "FAZA 2 — incumbent 1:" in izlaz
    assert "objective=" in izlaz
    assert "best_bound=" in izlaz
    assert "relativni_gap=" in izlaz
    assert "branches=" in izlaz
    assert "conflicts=" in izlaz


def test_relativni_gap_koristi_vecu_apsolutnu_magnitudu():
    assert _relativni_gap(-20, -100) == 0.8


def _resi_deterministicki_model(sa_telemetrijom: bool):
    model = cp_model.CpModel()
    prvi = model.new_bool_var("prvi")
    drugi = model.new_bool_var("drugi")
    model.add(prvi + drugi == 1)
    model.minimize(2 * prvi + drugi)

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    status = solver.solve(
        model,
        _TelemetrijaFaze2() if sa_telemetrijom else None,
    )
    assert status == cp_model.OPTIMAL
    return solver.value(prvi), solver.value(drugi), solver.objective_value


def test_telemetrija_ne_menja_deterministicko_resenje():
    assert _resi_deterministicki_model(True) == _resi_deterministicki_model(False)
