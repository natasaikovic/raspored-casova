from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ortools.sat.python import cp_model

import src.resavac as resavac
from src.model import (
    DostupnostProstorije, NivoPravilaProstorije, Odeljenje, Predmet,
    PraviloProstorije, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev,
)
from src.proveravac import Cas
from src.resavac import (
    LIMIT_KONFLIKATA_POPRAVKE_MASTER_HINTA,
    PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA,
    Rezultat,
    SukobProstorije,
    _broj_nevazecih_dodela_prostorija,
    _jedinice,
    _analiziraj_prostorije_hintova,
    _prenesi_resenje_kao_hint,
    _ponovo_dokazi_veliko_jezgro_soba,
    _upari_hintove,
    _vrednosti_hladnog_mastera,
    _zabrani_i_hintuj_master_dodelu,
    _zabrani_sukob_i_hintuj_master_dodelu,
    napravi_model,
    resi_obe_nedelje,
)


SALA = Prostorija("KM-1", "Кнез Милетина 8", TipProstorije.SALA, None, "")
UCIONICA = Prostorija("KM-уч2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, "")
SALA_2 = Prostorija("KM-2", "Кнез Милетина 8", TipProstorije.SALA, None, "")
SG_1 = Prostorija("SG-1", "Спортска гимназија", TipProstorije.SALA, None, "")
NP_SALA = Prostorija("NP-сала", "Народно позориште", TipProstorije.SALA, None, "")


def zahtev(predmet, odeljenje, fond, nastavnik, korepetitor=None, fond_korepeticije=None):
    if fond_korepeticije is None:
        fond_korepeticije = fond if korepetitor else 0
    return Zahtev(
        predmet=predmet, razred="први", odeljenja=(odeljenje,), fond=fond,
        fond_korepeticije=fond_korepeticije, nastavnik=nastavnik,
        korepetitor=korepetitor, smena=Smena.CRVENA,
        smena_opis=Smena.CRVENA.value, red=2,
    )


def ulaz(zahtevi):
    oznake = {o for z in zahtevi for o in z.odeljenja}
    odeljenja = {o: Odeljenje(o, "први", Smena.CRVENA, Skola.OSNOVNA) for o in oznake}
    predmeti = {}
    for z in zahtevi:
        igracki = bool(z.korepetitor)
        predmeti[z.predmet] = Predmet(z.predmet, igracki, igracki)
    return Ulaz(tuple(zahtevi), odeljenja, predmeti, Skola.OSNOVNA)


def _resi(u, hintovi=(), hintovi_b=()):
    return resi_obe_nedelje(
        u, (SALA, UCIONICA), (), vremensko_ogranicenje=5, broj_radnika=1,
        hintovi=hintovi, hintovi_b=hintovi_b,
    )


def _ulaz_za_dve_nedelje():
    return ulaz([
        zahtev("Класичан балет", "11", 4, "Мила", "Ива"),
        zahtev("Солфеђо", "11", 2, "Јана"),
    ])


def _hint_dvocas(
    prostorija, dan="понедељак", predmet="Класичан балет"
):
    return tuple(
        Cas(
            dan, blok, predmet, ("11",), "Мила", "Ива",
            prostorija, blok + 1,
        )
        for blok in (1, 2)
    )


def _analiza_soba(pravila=(), dostupnost=(), hintovi_b=()):
    u = ulaz([zahtev("Класичан балет", "11", 2, "Мила", "Ива")])
    u = replace(
        u, pravila_prostorija=tuple(pravila),
        dostupnost_prostorija=tuple(dostupnost),
    )
    jedinice = _jedinice(u)
    jedinice_zahteva = {0: list(jedinice)}
    slobodne, transformisane = _analiziraj_prostorije_hintova(
        u, (SALA, SALA_2, SG_1, NP_SALA), jedinice_zahteva,
        _hint_dvocas("KM-1"), hintovi_b,
    )
    return jedinice[0].indeks, slobodne, transformisane


def test_obavezno_ili_zabranjeno_menja_sobu_ali_ne_termin_na_istoj_lokaciji():
    for pravila in (
        (
            PraviloProstorije(
                "KM-2", NivoPravilaProstorije.OBAVEZNO,
                "Класичан балет", ("11",), None, "",
            ),
        ),
        (
            PraviloProstorije(
                "KM-1", NivoPravilaProstorije.ZABRANJENO,
                "Класичан балет", ("11",), None, "",
            ),
        ),
    ):
        _, slobodne, transformisane = _analiza_soba(pravila)
        assert slobodne == set()
        assert transformisane == 1


def test_obavezna_druga_lokacija_oslobadja_jedinicu():
    pravilo = PraviloProstorije(
        "SG-1", NivoPravilaProstorije.OBAVEZNO,
        "Класичан балет", ("11",), None, "",
    )
    indeks, slobodne, transformisane = _analiza_soba((pravilo,))
    assert slobodne == {indeks}
    assert transformisane == 0


def test_np_alias_postuje_dostupnost_kanonske_sale():
    predmet = "Репертоар класичног балета"
    u = ulaz([zahtev(predmet, "11", 2, "Мила", "Ива")])
    u = replace(
        u,
        pravila_prostorija=(PraviloProstorije(
            "NP-1", NivoPravilaProstorije.OBAVEZNO,
            predmet, ("11",), None, "",
        ),),
        dostupnost_prostorija=(DostupnostProstorije(
            "NP-2", "понедељак", 1, 2, "",
        ),),
    )
    jedinice = _jedinice(u)
    slobodne, transformisane = _analiziraj_prostorije_hintova(
        u, (NP_SALA,), {0: list(jedinice)},
        _hint_dvocas("NP-1", predmet=predmet), (),
    )
    assert slobodne == set()
    assert transformisane == 0


def test_problem_samo_u_nedelji_b_oslobadja_oba_termina():
    dostupnost = (
        DostupnostProstorije("KM-1", "понедељак", 1, 2, ""),
    )
    indeks, slobodne, transformisane = _analiza_soba(
        pravila=(PraviloProstorije(
            "KM-1", NivoPravilaProstorije.OBAVEZNO,
            "Класичан балет", ("11",), None, "",
        ),),
        dostupnost=dostupnost,
        hintovi_b=_hint_dvocas("KM-1", "уторак"),
    )
    assert slobodne == {indeks}
    assert transformisane == 0


def test_prethodni_raspored_se_prihvata_kao_fiksirani_hint(capsys):
    u = _ulaz_za_dve_nedelje()
    prvo_a, prvo_b = _resi(u)
    assert prvo_a.pronadjen and prvo_b.pronadjen

    drugo_a, drugo_b = _resi(u, hintovi=prvo_a.casovi, hintovi_b=prvo_b.casovi)

    assert "prethodni raspored prolazi uz 0 oslobođenih jedinica" in (
        capsys.readouterr().out
    )
    assert drugo_a.pronadjen and drugo_b.pronadjen
    assert drugo_a.izvestaj is not None and drugo_a.izvestaj.ispravan
    assert drugo_b.izvestaj is not None and drugo_b.izvestaj.ispravan


def test_prag_hladnog_starta_zadrzava_malu_a_odbacuje_veliku_izmenu():
    assert _broj_nevazecih_dodela_prostorija(
        ({0}, PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA - 1)
    ) == PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA
    assert _broj_nevazecih_dodela_prostorija(
        ({0, 1}, PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA - 1)
    ) > PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA


def test_veliki_broj_nevazecih_dodela_preskace_sve_pripremne_pokusaje(
    monkeypatch, capsys
):
    u = _ulaz_za_dve_nedelje()
    prvo_a, prvo_b = _resi(u)

    monkeypatch.setattr(
        resavac,
        "_analiziraj_prostorije_hintova",
        lambda *_args: (
            set(range(PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA + 1)), 0
        ),
    )

    def priprema_ne_sme_da_se_pokrene(*_args, **_kwargs):
        raise AssertionError("pripremni solve ne sme da se pokrene")

    monkeypatch.setattr(
        resavac, "_resi_fiksiranim_hintom", priprema_ne_sme_da_se_pokrene
    )
    drugo_a, drugo_b = _resi(
        u, hintovi=prvo_a.casovi, hintovi_b=prvo_b.casovi
    )

    izlaz = capsys.readouterr().out
    assert "одбацујем hint и покрећем хладни локацијски master" in izlaz
    assert "PRIPREMA — прескочена" in izlaz
    assert drugo_a.pronadjen and drugo_b.pronadjen


def test_mali_broj_nevazecih_dodela_zadrzava_topli_start(monkeypatch, capsys):
    u = _ulaz_za_dve_nedelje()
    prvo_a, prvo_b = _resi(u)
    capsys.readouterr()
    pravi_pokusaj = resavac._resi_fiksiranim_hintom
    broj_pokusaja = 0

    def izbroj_pokusaj(*args, **kwargs):
        nonlocal broj_pokusaja
        broj_pokusaja += 1
        return pravi_pokusaj(*args, **kwargs)

    monkeypatch.setattr(resavac, "_resi_fiksiranim_hintom", izbroj_pokusaj)
    drugo_a, drugo_b = _resi(
        u, hintovi=prvo_a.casovi, hintovi_b=prvo_b.casovi
    )

    assert broj_pokusaja == 1
    assert "PRIPREMA — прескочена" not in capsys.readouterr().out
    assert drugo_a.pronadjen and drugo_b.pronadjen


def test_bez_hinta_gradi_jedan_lokacijski_master(monkeypatch, capsys):
    pravi_napravi_model = resavac.napravi_model
    samo_lokacije_pozivi = 0

    def izbroj_modele(*args, **kwargs):
        nonlocal samo_lokacije_pozivi
        samo_lokacije_pozivi += bool(kwargs.get("samo_lokacije"))
        return pravi_napravi_model(*args, **kwargs)

    monkeypatch.setattr(resavac, "napravi_model", izbroj_modele)
    rezultat_a, rezultat_b = _resi(_ulaz_za_dve_nedelje())

    assert samo_lokacije_pozivi == 1
    assert "PRIPREMA — прескочена" in capsys.readouterr().out
    assert rezultat_a.pronadjen and rezultat_b.pronadjen


def test_hladni_master_ima_jedan_solve_i_cuva_rezervu_za_sobe(monkeypatch):
    pravi_solver = cp_model.CpSolver
    solve_pozivi = []

    class TimeoutSolver:
        def __init__(self):
            self.parameters = pravi_solver().parameters

        def solve(self, model):
            solve_pozivi.append(
                (model, self.parameters.max_time_in_seconds)
            )
            return cp_model.UNKNOWN

    vremena = iter((0.0, 0.2, 0.3, 0.4, 1.0, 1800.0))
    monkeypatch.setattr(resavac.time, "monotonic", lambda: next(vremena))
    monkeypatch.setattr(resavac.cp_model, "CpSolver", TimeoutSolver)

    solver, _, _, status, sobe_a, sobe_b = resavac._resi_u_dve_faze(
        ulaz([zahtev("Класичан балет", "11", 2, "Мила", "Ива")]),
        (SALA, UCIONICA), (), Smena.CRVENA,
        vremensko_ogranicenje=1800, broj_radnika=1, seme=1,
    )

    assert solver is None
    assert sobe_a is None and sobe_b is None
    assert "lokacijski master" in status
    assert len(solve_pozivi) == 1
    assert solve_pozivi[0][1] == 1679.8


def test_hladni_tok_dodeljuje_a_i_b_sobe_sa_preostalim_budzetom(monkeypatch):
    pravi_poziv = resavac._dodeli_prostorije_obe
    pozivi = []

    def zabelezi(*args, **kwargs):
        pozivi.append(kwargs["vremensko_ogranicenje"])
        return pravi_poziv(*args, **kwargs)

    monkeypatch.setattr(resavac, "_dodeli_prostorije_obe", zabelezi)
    rezultat_a, rezultat_b = _resi(_ulaz_za_dve_nedelje())

    assert len(pozivi) == 1 and 0 < pozivi[0] <= 5
    assert rezultat_a.pronadjen and rezultat_b.pronadjen
    assert all(cas.prostorija for cas in rezultat_a.casovi)
    assert all(cas.prostorija for cas in rezultat_b.casovi)
    assert rezultat_a.izvestaj is not None and rezultat_a.izvestaj.ispravan
    assert rezultat_b.izvestaj is not None and rezultat_b.izvestaj.ispravan
    assert rezultat_a.cilj is None and rezultat_b.cilj is None


def test_hladni_tok_posle_prvog_infeasible_sobe_uspeva_na_drugom(monkeypatch):
    pravi_poziv = resavac._dodeli_prostorije_obe
    broj_poziva = 0

    def prvi_neuspeva(*args, **kwargs):
        nonlocal broj_poziva
        broj_poziva += 1
        if broj_poziva == 1:
            kwargs["status_out"].append(cp_model.INFEASIBLE)
            return None
        return pravi_poziv(*args, **kwargs)

    monkeypatch.setattr(resavac, "_dodeli_prostorije_obe", prvi_neuspeva)
    pravi_full_rez = resavac._zabrani_i_hintuj_master_dodelu
    broj_full_rezova = 0

    def izbroj_full_rez(*args, **kwargs):
        nonlocal broj_full_rezova
        broj_full_rezova += 1
        return pravi_full_rez(*args, **kwargs)

    monkeypatch.setattr(
        resavac, "_zabrani_i_hintuj_master_dodelu", izbroj_full_rez
    )
    rezultat_a, rezultat_b = _resi(_ulaz_za_dve_nedelje())

    assert broj_poziva == 2
    assert broj_full_rezova == 1
    assert rezultat_a.pronadjen and rezultat_b.pronadjen


def test_popravka_hinta_vazi_samo_za_hladni_master_retry(monkeypatch):
    pravi_solver = cp_model.CpSolver
    parametri_mastera = []

    class SolverKojiBelezi:
        def __init__(self):
            self._solver = pravi_solver()
            self.parameters = self._solver.parameters

        def solve(self, model):
            parametri_mastera.append(
                (self.parameters.repair_hint, self.parameters.hint_conflict_limit)
            )
            return self._solver.solve(model)

        def __getattr__(self, naziv):
            return getattr(self._solver, naziv)

    broj_dodela = 0

    def prvi_room_core_pa_timeout(*args, **kwargs):
        nonlocal broj_dodela
        broj_dodela += 1
        if broj_dodela == 1:
            solver, _, _, jedinice, promenljive = args[:5]
            jedinica = jedinice[0]
            p = promenljive[jedinica.indeks]
            lokacija = next(
                naziv for naziv, koristi in p.lokacije.items()
                if solver.boolean_value(koristi)
            )
            kwargs["sukob_out"].append(
                SukobProstorije(
                    jedinica.indeks, False, solver.value(p.start), lokacija
                )
            )
            kwargs["status_out"].append(cp_model.INFEASIBLE)
        else:
            kwargs["status_out"].append(cp_model.UNKNOWN)
        return None

    monkeypatch.setattr(resavac.cp_model, "CpSolver", SolverKojiBelezi)
    monkeypatch.setattr(
        resavac, "_dodeli_prostorije_obe", prvi_room_core_pa_timeout
    )

    rezultat_a, rezultat_b = _resi(_ulaz_za_dve_nedelje())

    assert not rezultat_a.pronadjen and not rezultat_b.pronadjen
    assert parametri_mastera == [
        (False, 10),
        (True, LIMIT_KONFLIKATA_POPRAVKE_MASTER_HINTA),
    ]


def test_mali_core_rez_sa_popravkom_hinta_nalazi_susedno_resenje():
    model = cp_model.CpModel()
    izbori = [model.new_bool_var(f"izbor_{i}") for i in range(40)]
    model.add_exactly_one(izbori)

    prvi = cp_model.CpSolver()
    prvi.parameters.num_search_workers = 1
    assert prvi.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    staro = tuple(prvi.boolean_value(x) for x in izbori)
    model.add(sum(x for x, vrednost in zip(izbori, staro) if vrednost) == 0)
    for promenljiva, vrednost in zip(izbori, staro):
        model.add_hint(promenljiva, vrednost)

    retry = cp_model.CpSolver()
    retry.parameters.num_search_workers = 1
    retry.parameters.repair_hint = True
    retry.parameters.hint_conflict_limit = (
        LIMIT_KONFLIKATA_POPRAVKE_MASTER_HINTA
    )
    assert retry.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    novo = tuple(retry.boolean_value(x) for x in izbori)

    # Jedan mali no-good pomera izbor na neposrednog suseda: stari true postaje
    # false, a tačno jedan drugi false postaje true.
    assert sum(a != b for a, b in zip(staro, novo)) == 2


def _hall_sukob(nedelja_b=False):
    zahtevi = [
        zahtev("Предмет 1", "11", 1, "Наставник 1", "Корепетитор 1"),
        zahtev("Предмет 2", "12", 1, "Наставник 2", "Корепетитор 2"),
    ]
    u = ulaz(zahtevi)
    u = replace(
        u,
        pravila_prostorija=tuple(
            PraviloProstorije(
                "KM-1", NivoPravilaProstorije.OBAVEZNO,
                z.predmet, z.odeljenja, None, "",
            )
            for z in zahtevi
        ),
    )
    _, jedinice, promenljive = napravi_model(
        u, (SALA, SALA_2), (), Smena.CRVENA,
        sa_nedeljom_b=True, samo_lokacije=True, sa_ciljem=False,
    )
    vrednosti = {}
    for redni_broj, jedinica in enumerate(jedinice):
        p = promenljive[jedinica.indeks]
        assert p.start_b is not None
        vrednosti[p.start.index] = 61 if not nedelja_b else 61 + redni_broj
        vrednosti[p.start_b.index] = 70 if nedelja_b else 70 + redni_broj

    class FiksniMaster:
        def value(self, varijabla):
            return vrednosti[varijabla.index]

        def boolean_value(self, _varijabla):
            return True

    statusi = []
    sukob = []
    dodela = resavac._dodeli_prostorije_obe(
        FiksniMaster(), u, (SALA, SALA_2), jedinice, promenljive,
        broj_radnika=1, status_out=statusi, sukob_out=sukob,
    )
    assert dodela is None
    assert statusi == [cp_model.INFEASIBLE]
    return sukob


def test_hall_sukob_vraca_malo_jezgro_i_rez_menja_master_odluku():
    sukob = _hall_sukob()
    assert len(sukob) == 2
    assert {stavka.nedelja_b for stavka in sukob} == {False}

    model = cp_model.CpModel()
    promenljive = {}
    for stavka in sukob:
        start = model.new_int_var(60, 62, f"start_{stavka.jedinica_indeks}")
        lokacija = model.new_bool_var(f"lokacija_{stavka.jedinica_indeks}")
        model.add(lokacija == 1)
        promenljive[stavka.jedinica_indeks] = SimpleNamespace(
            start=start, start_b=start,
            lokacije={stavka.lokacija: lokacija},
            lokacije_b={stavka.lokacija: lokacija},
        )
    broj_varijabli_reza = _zabrani_sukob_i_hintuj_master_dodelu(
        model, promenljive, sukob, (), (),
    )
    assert broj_varijabli_reza == 4

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert any(
        solver.value(promenljive[x.jedinica_indeks].start) != x.start
        for x in sukob
    )


def test_room_jezgro_razlikuje_nedelju_b():
    sukob = _hall_sukob(nedelja_b=True)
    assert len(sukob) == 2
    assert {stavka.nedelja_b for stavka in sukob} == {True}


def test_core_rez_deduplikuje_deljene_a_b_master_varijable():
    model = cp_model.CpModel()
    start = model.new_int_var(0, 1, "start")
    lokacija = model.new_bool_var("lokacija")
    p = SimpleNamespace(
        start=start, start_b=start,
        lokacije={"KM": lokacija}, lokacije_b={"KM": lokacija},
    )
    sukob = (
        SukobProstorije(0, False, 0, "KM"),
        SukobProstorije(0, True, 0, "KM"),
    )
    broj_varijabli_reza = _zabrani_sukob_i_hintuj_master_dodelu(
        model, {0: p}, sukob, (start, lokacija), (0, 1),
    )

    assert broj_varijabli_reza == 2
    assert len(model.proto.solution_hint.vars) == 2
    solver = cp_model.CpSolver()
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert (solver.value(start), solver.value(lokacija)) != (0, 1)


def test_objective_free_reproof_smanjuje_jezgro_sa_1128_na_pravi_sukob():
    model = cp_model.CpModel()
    cuvari = [model.new_bool_var(f"cuvar_{i}") for i in range(1128)]
    bezopasne = [model.new_bool_var(f"x_{i}") for i in range(1128)]
    for cuvar, promenljiva in zip(cuvari, bezopasne, strict=True):
        model.add(promenljiva == 0).only_enforce_if(cuvar)
    model.add(cuvari[-2] + cuvari[-1] <= 1)
    model.add_assumptions(cuvari)
    model.minimize(sum(bezopasne))

    prvi = cp_model.CpSolver()
    prvi.parameters.num_search_workers = 1
    assert prvi.solve(model) == cp_model.INFEASIBLE
    originalno = list(prvi.sufficient_assumptions_for_infeasibility())
    assert len(originalno) == 1128

    jezgro = _ponovo_dokazi_veliko_jezgro_soba(
        model, originalno, {cuvar.index for cuvar in cuvari}, 10.0, 1
    )

    assert len(jezgro) == 2
    assert set(jezgro) == {cuvari[-2].index, cuvari[-1].index}
    assert not model.has_objective()


def test_unknown_reproof_zadrzava_originalno_jezgro(monkeypatch):
    model = cp_model.CpModel()
    cilj = model.new_bool_var("cilj")
    model.minimize(cilj)
    originalno = list(range(65))

    class SolverKojiNeDokazuje:
        def __init__(self):
            self.parameters = SimpleNamespace()

        def solve(self, prosledjeni_model):
            assert prosledjeni_model is model
            assert not prosledjeni_model.has_objective()
            return cp_model.UNKNOWN

    monkeypatch.setattr(resavac.cp_model, "CpSolver", SolverKojiNeDokazuje)

    assert _ponovo_dokazi_veliko_jezgro_soba(
        model, originalno, originalno, 10.0, 1
    ) == originalno


def test_reproof_koristi_celo_novo_delimicno_preklopljeno_jezgro(monkeypatch):
    model = cp_model.CpModel()
    cilj = model.new_bool_var("cilj")
    model.minimize(cilj)
    originalno = list(range(65))
    novo = list(range(32, 97))

    class SolverSaDrugimDovoljnimJezgrom:
        def __init__(self):
            self.parameters = SimpleNamespace()

        def solve(self, prosledjeni_model):
            assert prosledjeni_model is model
            assert not prosledjeni_model.has_objective()
            return cp_model.INFEASIBLE

        def sufficient_assumptions_for_infeasibility(self):
            return novo

    monkeypatch.setattr(
        resavac.cp_model, "CpSolver", SolverSaDrugimDovoljnimJezgrom
    )

    assert _ponovo_dokazi_veliko_jezgro_soba(
        model, originalno, range(97), 10.0, 1
    ) == novo
    assert _ponovo_dokazi_veliko_jezgro_soba(
        model, originalno, range(96), 10.0, 1
    ) == originalno


def test_no_good_menja_kompletnu_master_dodelu():
    u = _ulaz_za_dve_nedelje()
    model, jedinice, promenljive = napravi_model(
        u, (SALA, UCIONICA), (), Smena.CRVENA,
        sa_nedeljom_b=True, samo_lokacije=True, sa_ciljem=False,
    )
    prvi = cp_model.CpSolver()
    prvi.parameters.num_search_workers = 1
    assert prvi.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    varijable, vrednosti = _vrednosti_hladnog_mastera(
        prvi, jedinice, promenljive
    )

    _zabrani_i_hintuj_master_dodelu(model, varijable, vrednosti)
    drugi = cp_model.CpSolver()
    drugi.parameters.num_search_workers = 1
    assert drugi.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    _, druge_vrednosti = _vrednosti_hladnog_mastera(
        drugi, jedinice, promenljive
    )

    assert druge_vrednosti != vrednosti
    assert len(model.proto.solution_hint.vars) == len(set(model.proto.solution_hint.vars))


def test_unknown_dodela_soba_ne_pokrece_novi_master(monkeypatch):
    broj_poziva = 0
    broj_rezova = 0

    def timeout_soba(*args, **kwargs):
        nonlocal broj_poziva
        broj_poziva += 1
        kwargs["status_out"].append(cp_model.UNKNOWN)
        return None

    def rez_ne_sme(*args, **kwargs):
        nonlocal broj_rezova
        broj_rezova += 1

    monkeypatch.setattr(resavac, "_dodeli_prostorije_obe", timeout_soba)
    monkeypatch.setattr(resavac, "_zabrani_i_hintuj_master_dodelu", rez_ne_sme)
    monkeypatch.setattr(
        resavac, "_zabrani_sukob_i_hintuj_master_dodelu", rez_ne_sme
    )
    rezultat_a, rezultat_b = _resi(_ulaz_za_dve_nedelje())

    assert broj_poziva == 1
    assert broj_rezova == 0
    assert not rezultat_a.pronadjen and not rezultat_b.pronadjen


def test_main_ne_izvozi_delimican_par_nedelja(monkeypatch, tmp_path):
    u = _ulaz_za_dve_nedelje()
    izvestaj = resavac.proveri(u, (SALA, UCIONICA), (), (), Smena.CRVENA)
    a = Rezultat("dopustivo", _hint_dvocas("KM-1"), izvestaj, None)
    b = Rezultat("neuspeh dodele konkretnih prostorija", (), None, None)
    monkeypatch.setattr(
        resavac, "ucitaj_standardne_ulaze", lambda _putanja: (u, (SALA, UCIONICA), ())
    )
    monkeypatch.setattr(resavac, "resi_obe_nedelje", lambda *_args, **_kwargs: (a, b))

    izlaz = tmp_path / "izlaz"
    assert resavac.main(["--izlaz", str(izlaz)]) == 1
    assert not (izlaz / "nedelja_a.csv").exists()
    assert not (izlaz / "nedelja_b.csv").exists()
    assert not (izlaz / "raspored.html").exists()


def test_atomski_izvoz_ne_ostavlja_parcijalne_nove_fajlove(monkeypatch, tmp_path):
    u = _ulaz_za_dve_nedelje()
    a, b = _resi(u)
    monkeypatch.setattr(
        resavac, "ucitaj_standardne_ulaze", lambda _putanja: (u, (SALA, UCIONICA), ())
    )
    monkeypatch.setattr(resavac, "resi_obe_nedelje", lambda *_args, **_kwargs: (a, b))
    pravi_sacuvaj = resavac.sacuvaj_csv
    broj_poziva = 0

    def prekini_drugi_csv(putanja, casovi):
        nonlocal broj_poziva
        broj_poziva += 1
        if broj_poziva == 2:
            raise RuntimeError("simuliran prekid")
        pravi_sacuvaj(putanja, casovi)

    monkeypatch.setattr(resavac, "sacuvaj_csv", prekini_drugi_csv)
    izlaz = tmp_path / "izlaz"
    with pytest.raises(RuntimeError, match="simuliran prekid"):
        resavac.main(["--izlaz", str(izlaz)])

    assert not (izlaz / "nedelja_a.csv").exists()
    assert not (izlaz / "nedelja_b.csv").exists()
    assert not (izlaz / "raspored.html").exists()
    assert not list(izlaz.glob(".raspored-*"))


def test_atomski_replace_na_gresci_vraca_prethodni_skup(monkeypatch, tmp_path):
    u = _ulaz_za_dve_nedelje()
    a, b = _resi(u)
    izlaz = tmp_path / "izlaz"
    izlaz.mkdir()
    prethodni = {
        "nedelja_a.csv": "staro A",
        "nedelja_b.csv": "staro B",
        "raspored.html": "stari HTML",
    }
    for ime, sadrzaj in prethodni.items():
        (izlaz / ime).write_text(sadrzaj, encoding="utf-8")
    pravi_replace = resavac.os.replace
    prekid_iskoriscen = False

    def prekini_postavljanje_b(izvor, cilj):
        nonlocal prekid_iskoriscen
        izvor, cilj = Path(izvor), Path(cilj)
        if (
            not prekid_iskoriscen
            and izvor.name == "nedelja_b.csv"
            and cilj.parent == izlaz
            and izvor.parent.name != "prethodni"
        ):
            prekid_iskoriscen = True
            raise OSError("simuliran prekid replace")
        return pravi_replace(izvor, cilj)

    monkeypatch.setattr(resavac.os, "replace", prekini_postavljanje_b)
    with pytest.raises(OSError, match="simuliran prekid replace"):
        resavac._sacuvaj_izlaze_atomski(izlaz, a.casovi, b.casovi)

    assert {
        ime: (izlaz / ime).read_text(encoding="utf-8")
        for ime in prethodni
    } == prethodni
    assert not list(izlaz.glob(".raspored-*"))


def test_stalna_smena_ne_duplira_hintove_izmedju_nedelja(capsys):
    z = replace(
        zahtev("Класичан балет", "11", 2, "Мила", "Ива"),
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
    )
    u = ulaz([z])

    rezultat_a, rezultat_b = _resi(u)

    izlaz = capsys.readouterr().out
    assert "INVALID_MODEL" not in izlaz
    assert rezultat_a.pronadjen and rezultat_b.pronadjen
    assert rezultat_a.izvestaj is not None and rezultat_a.izvestaj.ispravan
    assert rezultat_b.izvestaj is not None and rezultat_b.izvestaj.ispravan


def test_druga_faza_prima_jedinstven_potpun_hint_sa_prostorijama():
    z = replace(
        zahtev("Класичан балет", "11", 2, "Мила", "Ива"),
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
    )
    u = ulaz([z])
    sobe = (SALA, UCIONICA)
    model_1, jedinice, promenljive_1 = napravi_model(
        u, sobe, (), Smena.CRVENA, sa_nedeljom_b=True,
        samo_lokacije=False, sa_ciljem=False,
    )
    solver_1 = cp_model.CpSolver()
    assert solver_1.solve(model_1) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    model_2, _, promenljive_2 = napravi_model(
        u, sobe, (), Smena.CRVENA, sa_nedeljom_b=True,
        samo_lokacije=False, sa_ciljem=True,
    )

    _prenesi_resenje_kao_hint(
        model_2, solver_1, jedinice, promenljive_1, promenljive_2
    )

    hintovani = list(model_2.proto.solution_hint.vars)
    room_indeksi = {
        promenljiva.index
        for p in promenljive_2.values()
        for izbori in (p.prostorije, p.prostorije_b or {})
        for promenljiva in izbori.values()
    }
    assert len(hintovani) == len(set(hintovani))
    assert room_indeksi <= set(hintovani)
    assert model_2.validate() == ""
    solver_2 = cp_model.CpSolver()
    solver_2.parameters.fix_variables_to_their_hinted_value = True
    assert solver_2.solve(model_2) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_lokacijska_priprema_daje_dopustiv_hint_strogoj_fazi():
    u = ulaz([zahtev("Класичан балет", "11", 2, "Мила", "Ива")])
    sobe = (SALA, UCIONICA)
    model_pripreme, jedinice, promenljive_pripreme = napravi_model(
        u, sobe, (), Smena.CRVENA, sa_nedeljom_b=True,
        samo_lokacije=True, sa_ciljem=False,
    )
    solver_pripreme = cp_model.CpSolver()
    assert solver_pripreme.solve(model_pripreme) in (
        cp_model.OPTIMAL, cp_model.FEASIBLE,
    )
    model_1, _, promenljive_1 = napravi_model(
        u, sobe, (), Smena.CRVENA, sa_nedeljom_b=True,
        samo_lokacije=False, sa_ciljem=False,
    )

    _prenesi_resenje_kao_hint(
        model_1, solver_pripreme, jedinice,
        promenljive_pripreme, promenljive_1,
    )

    hintovani = list(model_1.proto.solution_hint.vars)
    assert len(hintovani) == len(set(hintovani))
    assert model_1.validate() == ""
    solver_1 = cp_model.CpSolver()
    solver_1.parameters.fix_variables_to_their_hinted_value = True
    assert solver_1.solve(model_1) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_neuspeh_dodele_soba_ne_vraca_raspored(monkeypatch):
    pravi_solver = cp_model.CpSolver
    broj_solvera = 0

    class TimeoutSolver:
        def __init__(self):
            self.parameters = pravi_solver().parameters

        def solve(self, _model):
            return cp_model.UNKNOWN

    def solver_fabrika():
        nonlocal broj_solvera
        broj_solvera += 1
        return pravi_solver() if broj_solvera == 1 else TimeoutSolver()

    monkeypatch.setattr(resavac.cp_model, "CpSolver", solver_fabrika)
    rezultat_a, rezultat_b = _resi(
        ulaz([zahtev("Класичан балет", "11", 2, "Мила", "Ива")])
    )

    assert "dodela konkretnih prostorija" in rezultat_a.status
    assert not rezultat_a.pronadjen and not rezultat_b.pronadjen
    assert rezultat_a.casovi == () and rezultat_b.casovi == ()


def test_neupotrebljiv_hint_se_popravlja_pomocu_infeasible_jezgra(capsys):
    u = _ulaz_za_dve_nedelje()
    prvo_a, _ = _resi(u)
    prvi_termin = prvo_a.casovi[0]
    # Svi časovi u isti termin: odeljenje 11 bi se preklapalo, pa fiksirani
    # hint ne može biti dopustiv.
    pokvareni = tuple(
        replace(c, dan=prvi_termin.dan, blok=prvi_termin.blok) for c in prvo_a.casovi
    )

    drugo_a, drugo_b = _resi(u, hintovi=pokvareni)

    izlaz = capsys.readouterr().out
    assert "језгро" in izlaz
    assert "prethodni raspored prolazi uz" in izlaz
    assert drugo_a.pronadjen and drugo_b.pronadjen
    assert drugo_a.izvestaj is not None and drugo_a.izvestaj.ispravan


def test_uparivanje_hintova_postuje_obrazac_korepeticije():
    # Fond 4 uz 3 časa korepeticije daje dvočas sa korepeticijom (0, 1) i
    # dvočas sa korepeticijom samo u prvom bloku (0,).
    u = ulaz([zahtev("Класичан балет", "11", 4, "Мила", "Ива", fond_korepeticije=3)])
    jedinice = _jedinice(u)
    assert [j.korepeticija for j in jedinice] == [(0, 1), (0,)]
    jedinice_zahteva = {0: list(jedinice)}

    def cas(dan, blok, korepetitor):
        return Cas(
            dan=dan, blok=blok, predmet="Класичан балет", odeljenja=("11",),
            nastavnik="Мила", korepetitor=korepetitor, prostorija="KM-1", red=0,
        )

    # Hronološki prvi dvočas ima korepeticiju samo u prvom bloku.
    hintovi = (
        cas("понедељак", 1, "Ива"), cas("понедељак", 2, None),
        cas("среда", 1, "Ива"), cas("среда", 2, "Ива"),
    )

    upareno = _upari_hintove(u, jedinice_zahteva, hintovi)

    assert upareno == {
        jedinice[0].indeks: (2, 1, "KM-1"),
        jedinice[1].indeks: (0, 1, "KM-1"),
    }


def test_nivoi_oslobadjanja_sire_se_preko_zajednickih_resursa():
    from src.resavac import _nivoi_oslobadjanja

    # 11: balet (Мила) i solfeđo (Јана); 12: solfeđo (Јана); 13: istorija (Пера).
    u = ulaz([
        zahtev("Класичан балет", "11", 2, "Мила", "Ива"),
        zahtev("Солфеђо", "11", 1, "Јана"),
        zahtev("Солфеђо", "12", 1, "Јана"),
        zahtev("Историја", "13", 1, "Пера"),
    ])
    jedinice = _jedinice(u)
    po_zahtevu = {j.zahtev_indeks: j.indeks for j in jedinice}
    # Samo balet 11 je bez hinta (npr. izmenjen red ulaza).
    hintovi_jedinica = {
        j.indeks: [] for j in jedinice if j.zahtev_indeks != 0
    }

    nivoi = _nivoi_oslobadjanja(u, jedinice, hintovi_jedinica)

    assert nivoi[0] == {po_zahtevu[0]}
    # Nivo 1: solfeđo 11 deli odeljenje sa baletom 11.
    assert nivoi[1] == {po_zahtevu[0], po_zahtevu[1]}
    # Nivo 2: solfeđo 12 deli nastavnika sa solfeđom 11; istorija 13 ostaje.
    assert nivoi[2] == {po_zahtevu[0], po_zahtevu[1], po_zahtevu[2]}
