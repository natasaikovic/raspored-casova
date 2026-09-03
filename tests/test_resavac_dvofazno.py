from types import SimpleNamespace

from ortools.sat.python import cp_model

from src import resavac
from src.model import Smena


class _Model:
    def __init__(self, broj_promenljivih=2):
        self.proto = SimpleNamespace(variables=[object()] * broj_promenljivih)
        self.hintovi = []

    def get_int_var_from_proto_index(self, indeks):
        return f"promenljiva-{indeks}"

    def add_hint(self, promenljiva, vrednost):
        self.hintovi.append((promenljiva, vrednost))


class _Solver:
    def __init__(self, status):
        self.status = status
        self.parameters = SimpleNamespace()
        self.pozivi_value = []

    def solve(self, model):
        self.model = model
        return self.status

    def value(self, promenljiva):
        self.pozivi_value.append(promenljiva)
        return 10 + len(self.pozivi_value)


def _pokreni(
    monkeypatch,
    statusi,
    vremena,
    hintovi=("csv-hint-a",),
    hintovi_b=("csv-hint-b",),
    budzet=1800.0,
):
    modeli = [_Model(), _Model()]
    pozivi_modela = []
    solveri = []

    def napravi_model(*args, **kwargs):
        pozivi_modela.append(kwargs)
        model = modeli[len(pozivi_modela) - 1]
        return model, ("jedinica",), {0: "promenljiva"}

    def napravi_solver():
        solver = _Solver(statusi[len(solveri)])
        solveri.append(solver)
        return solver

    tok = iter(vremena)
    monkeypatch.setattr(resavac, "napravi_model", napravi_model)
    monkeypatch.setattr(resavac.cp_model, "CpSolver", napravi_solver)
    monkeypatch.setattr(resavac.time, "monotonic", lambda: next(tok))
    monkeypatch.setattr(
        resavac,
        "_resi_fiksiranim_hintom",
        lambda *args, **kwargs: cp_model.UNKNOWN,
    )

    rezultat = resavac._resi_u_dve_faze(
        object(),
        (),
        (),
        Smena.CEO_DAN,
        budzet,
        8,
        42,
        hintovi=hintovi,
        hintovi_b=hintovi_b,
    )
    return rezultat, modeli, pozivi_modela, solveri


def test_budzet_1800_ostavlja_300_sekundi_drugoj_fazi(monkeypatch):
    _, _, _, solveri = _pokreni(
        monkeypatch,
        (cp_model.UNKNOWN, cp_model.OPTIMAL),
        (0.0, 0.0, 1500.0, 1500.0, 1800.0),
    )

    assert solveri[0].parameters.max_time_in_seconds == 1500.0
    assert solveri[1].parameters.max_time_in_seconds == 300.0


def test_unknown_odmah_pokrece_fazu_2_sa_originalnim_csv_hintovima(monkeypatch):
    csv_hintovi_a = ("hint-a",)
    csv_hintovi_b = ("hint-b",)
    rezultat, modeli, pozivi_modela, solveri = _pokreni(
        monkeypatch,
        (cp_model.UNKNOWN, cp_model.FEASIBLE),
        (0.0, 0.0, 1500.0, 1500.0, 1600.0),
        hintovi=csv_hintovi_a,
        hintovi_b=csv_hintovi_b,
    )

    assert len(solveri) == 2
    assert solveri[0].pozivi_value == []
    assert pozivi_modela[0]["hintovi"] is csv_hintovi_a
    assert pozivi_modela[0]["hintovi_b"] is csv_hintovi_b
    assert pozivi_modela[1]["hintovi"] is csv_hintovi_a
    assert pozivi_modela[1]["hintovi_b"] is csv_hintovi_b
    assert modeli[1].hintovi == []
    assert rezultat[0] is solveri[1]


def test_feasible_rano_daje_stvarni_ostatak_i_prenosi_resenje(monkeypatch):
    rezultat, modeli, pozivi_modela, solveri = _pokreni(
        monkeypatch,
        (cp_model.FEASIBLE, cp_model.UNKNOWN),
        (0.0, 0.0, 100.0, 100.0, 1800.0),
    )

    assert solveri[1].parameters.max_time_in_seconds == 1700.0
    assert pozivi_modela[1]["hintovi"] == ()
    assert pozivi_modela[1]["hintovi_b"] == ()
    assert solveri[0].pozivi_value == ["promenljiva-0", "promenljiva-1"]
    assert modeli[1].hintovi == [
        ("promenljiva-0", 11),
        ("promenljiva-1", 12),
    ]
    assert rezultat[0] is solveri[0]
    assert "faza 2 neuspeh/timeout" in rezultat[3]


def test_infeasible_ne_pokrece_fazu_2(monkeypatch):
    rezultat, _, pozivi_modela, solveri = _pokreni(
        monkeypatch,
        (cp_model.INFEASIBLE,),
        (0.0, 0.0, 25.0),
    )

    assert len(pozivi_modela) == 1
    assert len(solveri) == 1
    assert rezultat[0] is None
    assert "nema rešenja" in rezultat[3]


def test_unknown_u_obe_faze_ne_vraca_nepostojece_resenje(monkeypatch):
    rezultat, _, _, solveri = _pokreni(
        monkeypatch,
        (cp_model.UNKNOWN, cp_model.UNKNOWN),
        (0.0, 0.0, 1500.0, 1500.0, 1800.0),
    )

    assert len(solveri) == 2
    assert rezultat[0] is None
    assert "obe faze" in rezultat[3]
