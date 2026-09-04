from dataclasses import replace

from ortools.sat.python import cp_model

import src.resavac as resavac
from src.model import (
    DostupnostProstorije, NivoPravilaProstorije, Odeljenje, Predmet,
    PraviloProstorije, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev,
)
from src.proveravac import Cas
from src.resavac import (
    _jedinice,
    _analiziraj_prostorije_hintova,
    _prenesi_resenje_kao_hint,
    _upari_hintove,
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

    assert "prethodni raspored je i dalje dopustiv" in capsys.readouterr().out
    assert drugo_a.pronadjen and drugo_b.pronadjen
    assert drugo_a.izvestaj is not None and drugo_a.izvestaj.ispravan
    assert drugo_b.izvestaj is not None and drugo_b.izvestaj.ispravan


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


def test_fallback_prve_faze_vec_sadrzi_konkretne_prostorije(monkeypatch):
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
        return pravi_solver() if broj_solvera <= 2 else TimeoutSolver()

    monkeypatch.setattr(resavac.cp_model, "CpSolver", solver_fabrika)
    rezultat_a, rezultat_b = _resi(
        ulaz([zahtev("Класичан балет", "11", 2, "Мила", "Ива")])
    )

    assert "faza 2 neuspeh/timeout" in rezultat_a.status
    assert rezultat_a.pronadjen and rezultat_b.pronadjen
    assert {cas.prostorija for cas in rezultat_a.casovi} <= {"KM-1", "KM-уч2"}
    assert {cas.prostorija for cas in rezultat_b.casovi} <= {"KM-1", "KM-уч2"}
    assert rezultat_a.izvestaj is not None and rezultat_a.izvestaj.ispravan
    assert rezultat_b.izvestaj is not None and rezultat_b.izvestaj.ispravan


def test_neupotrebljiv_hint_se_odbacuje_i_trazi_se_novo_resenje(capsys):
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
    assert "nije upotrebljiv kao fiksirani hint" in izlaz
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
