from dataclasses import replace

import pytest
from ortools.sat.python import cp_model

from src.model import (
    NivoPravilaProstorije,
    Odeljenje,
    Predmet,
    PraviloProstorije,
    Prostorija,
    Skola,
    Smena,
    TipProstorije,
    Ulaz,
    Zahtev,
)
from src.proveravac import Cas, proveri
from src.resavac import (
    _dodeli_prostorije,
    _dodeli_prostorije_obe,
    _kazna_sale_km8,
    _moguce_prostorije,
    napravi_model,
)


PG = "Примењена гимнастика"
KLASICAN = "Класичан балет"
DRUGA_IGRA = "Друга игра"
KM = "Кнез Милетина 8"
SG = "Спортска гимназија"

SALE = (
    Prostorija("KM-1", KM, TipProstorije.SALA, None, ""),
    Prostorija("KM-8", KM, TipProstorije.SALA, 3, ""),
    Prostorija("SG-1", SG, TipProstorije.SALA, None, ""),
    Prostorija("SG-2", SG, TipProstorije.SALA, None, ""),
    Prostorija("SG-3", SG, TipProstorije.SALA, None, ""),
)


def _zahtev(predmet, nastavnik, korepetitor, red):
    return Zahtev(
        predmet=predmet,
        razred="први",
        odeljenja=("11",),
        fond=2,
        fond_korepeticije=2,
        nastavnik=nastavnik,
        korepetitor=korepetitor,
        smena=Smena.CRVENA,
        smena_opis=Smena.CRVENA.value,
        red=red,
        datoteka="test.csv",
    )


def _ulaz(sa_drugim=True):
    zahtevi = [_zahtev(PG, "Бранислава", "Ђорђина", 2)]
    if sa_drugim:
        zahtevi.append(_zahtev(DRUGA_IGRA, "Мила", "Ива", 3))
    predmeti = {
        zahtev.predmet: Predmet(zahtev.predmet, True, True)
        for zahtev in zahtevi
    }
    return Ulaz(
        tuple(zahtevi),
        {"11": Odeljenje("11", "први", Smena.CRVENA, Skola.OSNOVNA)},
        predmeti,
        Skola.OSNOVNA,
        (
            PraviloProstorije(
                "KM-8", NivoPravilaProstorije.OBAVEZNO, PG, (), None, "",
            ),
        ),
    )


def _casovi_pg(prostorija, sa_drugim_u_sg=False):
    casovi = [
        Cas("понедељак", 1, PG, ("11",), "Бранислава", "Ђорђина", prostorija, 2),
        Cas("понедељак", 2, PG, ("11",), "Бранислава", "Ђорђина", prostorija, 3),
    ]
    if sa_drugim_u_sg:
        casovi.extend(
            (
                Cas("понедељак", 3, DRUGA_IGRA, ("11",), "Мила", "Ива", "SG-1", 4),
                Cas("понедељак", 4, DRUGA_IGRA, ("11",), "Мила", "Ива", "SG-1", 5),
            )
        )
    return tuple(casovi)


def test_solver_csv_obavezno_ogranicava_pg_a_drugi_moze_u_km8_u_nuzdi():
    ulaz = _ulaz()
    pg, drugi = ulaz.zahtevi

    assert {p.oznaka for p in _moguce_prostorije(pg, ulaz, SALE)} == {"KM-8"}
    assert "KM-8" in {
        p.oznaka for p in _moguce_prostorije(drugi, ulaz, SALE)
    }
    assert _kazna_sale_km8(pg, "KM-8") == 0
    assert _kazna_sale_km8(drugi, "KM-8") == 100_000


def test_proveravac_prihvata_km8_za_pg():
    ulaz = _ulaz(False)
    izvestaj = proveri(ulaz, SALE, (), _casovi_pg("KM-8"))
    assert izvestaj.ispravan, izvestaj.tekst()


@pytest.mark.parametrize("prostorija", ("SG-1", "SG-2", "SG-3", "KM-1"))
def test_proveravac_odbija_pg_u_drugoj_sali(prostorija):
    izvestaj = proveri(_ulaz(False), SALE, (), _casovi_pg(prostorija))
    assert any("структурисана правила забрањују" in g for g in izvestaj.greske)


def test_proveravac_upozorava_za_drugi_predmet_u_km8():
    ulaz = _ulaz()
    casovi = (
        Cas("понедељак", 1, PG, ("11",), "Бранислава", "Ђорђина", "KM-8", 2),
        Cas("понедељак", 2, PG, ("11",), "Бранислава", "Ђорђина", "KM-8", 3),
        Cas("уторак", 1, DRUGA_IGRA, ("11",), "Мила", "Ива", "KM-8", 4),
        Cas("уторак", 2, DRUGA_IGRA, ("11",), "Мила", "Ива", "KM-8", 5),
    )
    izvestaj = proveri(ulaz, SALE, (), casovi)
    assert izvestaj.ispravan, izvestaj.tekst()
    assert any("дозвољен само у нужди" in u for u in izvestaj.upozorenja)
    assert sum("дозвољен само у нужди" in u for u in izvestaj.upozorenja) == 1


def _ulaz_pg_i_klasicni():
    zahtevi = (
        _zahtev(PG, "Бранислава", "Ђорђина", 2),
        _zahtev(KLASICAN, "Мила", "Ива", 3),
    )
    return Ulaz(
        zahtevi,
        {"11": Odeljenje("11", "први", Smena.CRVENA, Skola.OSNOVNA)},
        {
            PG: Predmet(PG, True, True),
            KLASICAN: Predmet(KLASICAN, True, True),
        },
        Skola.OSNOVNA,
        (
            PraviloProstorije(
                "KM-8", NivoPravilaProstorije.PRVI, PG, (), None, "",
            ),
        ),
    )


def test_pg_mora_pratiti_klasicni_balet_u_sportskoj_gimnaziji():
    ulaz = _ulaz_pg_i_klasicni()
    casovi = (
        Cas("понедељак", 1, PG, ("11",), "Бранислава", "Ђорђина", "KM-8", 2),
        Cas("понедељак", 2, PG, ("11",), "Бранислава", "Ђорђина", "KM-8", 3),
        Cas("понедељак", 3, KLASICAN, ("11",), "Мила", "Ива", "SG-1", 4),
        Cas("понедељак", 4, KLASICAN, ("11",), "Мила", "Ива", "SG-1", 5),
    )
    izvestaj = proveri(ulaz, SALE, (), casovi)
    assert any("мора бити у Спортској гимназији" in g for g in izvestaj.greske)


def test_model_zabranjuje_pg_u_km_kada_je_klasicni_u_sg_istog_dana():
    ulaz = _ulaz_pg_i_klasicni()
    model, jedinice, promenljive = napravi_model(
        ulaz, SALE, (), Smena.CRVENA, samo_lokacije=True, sa_ciljem=False
    )
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        model.add(p.dan == 0)
        if zahtev.predmet == PG:
            model.add(p.lokacije[KM] == 1)
        else:
            model.add(p.lokacije[SG] == 1)
    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def _ulaz_kapaciteta(vrste, menjaju_se=False):
    smena = Smena.CRVENA if menjaju_se else Smena.CEO_DAN
    zahtevi = []
    odeljenja = {}
    predmeti = {}
    for indeks, vrsta in enumerate(vrste):
        predmet = PG if vrsta == "pg" else f"Игра {indeks}"
        oznaka = f"O{indeks}"
        korepetitor = f"Корепетитор {indeks}" if vrsta == "pg" else None
        zahtevi.append(
            Zahtev(
                predmet=predmet,
                razred="први",
                odeljenja=(oznaka,),
                fond=1,
                fond_korepeticije=1 if korepetitor else 0,
                nastavnik=f"Наставник {indeks}",
                korepetitor=korepetitor,
                smena=smena,
                smena_opis=smena.value,
                red=indeks + 2,
                datoteka="test.csv",
            )
        )
        odeljenja[oznaka] = Odeljenje(
            oznaka, "први", smena, Skola.OSNOVNA
        )
        predmeti[predmet] = Predmet(
            predmet, korepetitor is not None, True
        )
    pravila = ()
    if "pg" in vrste:
        pravila = (
            PraviloProstorije(
                "KM-8", NivoPravilaProstorije.OBAVEZNO, PG, (), None, "",
            ),
        )
    return Ulaz(tuple(zahtevi), odeljenja, predmeti, Skola.OSNOVNA, pravila)


def _fiksiraj_sve(model, jedinice, promenljive, lokacija, blok=1, nedelja_b=False):
    for jedinica in jedinice:
        p = promenljive[jedinica.indeks]
        dan = p.dan_b if nedelja_b else p.dan
        vreme = p.blok_b if nedelja_b else p.blok
        lokacije = p.lokacije_b if nedelja_b else p.lokacije
        assert dan is not None and vreme is not None and lokacije is not None
        model.add(dan == 0)
        model.add(vreme == blok)
        model.add(lokacije[lokacija] == 1)


def test_location_model_km8_je_dozvoljena_za_drugi_predmet_u_nuzdi():
    ulaz = _ulaz_kapaciteta(("drugi", "drugi"))
    model, jedinice, promenljive = napravi_model(
        ulaz, SALE[:2], (), Smena.CRVENA, samo_lokacije=True, sa_ciljem=False
    )
    _fiksiraj_sve(model, jedinice, promenljive, KM)

    assert cp_model.CpSolver().solve(model) in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    )


def test_location_model_dve_pg_ne_mogu_istovremeno_u_km8():
    ulaz = _ulaz_kapaciteta(("pg", "pg"))
    model, jedinice, promenljive = napravi_model(
        ulaz, SALE[:2], (), Smena.CRVENA, samo_lokacije=True, sa_ciljem=False
    )
    _fiksiraj_sve(model, jedinice, promenljive, KM)

    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def test_location_model_dozvoljava_jednu_pg_i_sest_drugih_u_km():
    sale = tuple(
        Prostorija(f"KM-{broj}", KM, TipProstorije.SALA, None, "")
        for broj in range(1, 7)
    ) + (Prostorija("KM-8", KM, TipProstorije.SALA, 3, ""),)
    ulaz = _ulaz_kapaciteta(("pg",) + ("drugi",) * 6)
    model, jedinice, promenljive = napravi_model(
        ulaz, sale, (), Smena.CRVENA, samo_lokacije=True, sa_ciljem=False
    )
    _fiksiraj_sve(model, jedinice, promenljive, KM)
    solver = cp_model.CpSolver()

    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    dodela = _dodeli_prostorije(
        solver, ulaz, sale, jedinice, promenljive, broj_radnika=1
    )
    assert dodela is not None
    assert set(dodela.values()) == {f"KM-{broj}" for broj in range(1, 7)} | {
        "KM-8"
    }


def test_location_model_pomera_sedmi_cas_da_bi_izbegao_km8():
    sale = tuple(
        Prostorija(f"KM-{broj}", KM, TipProstorije.SALA, None, "")
        for broj in range(1, 7)
    ) + (Prostorija("KM-8", KM, TipProstorije.SALA, 3, ""),)
    ulaz = _ulaz_kapaciteta(("drugi",) * 7)
    model, jedinice, promenljive = napravi_model(
        ulaz, sale, (), Smena.CRVENA, samo_lokacije=True, sa_ciljem=True
    )
    for jedinica in jedinice:
        p = promenljive[jedinica.indeks]
        model.add(p.dan == 0)
        model.add(p.lokacije[KM] == 1)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.solve(model) == cp_model.OPTIMAL
    assert len({solver.value(promenljive[j.indeks].blok) for j in jedinice}) > 1
    dodela = _dodeli_prostorije(
        solver, ulaz, sale, jedinice, promenljive, broj_radnika=1
    )
    assert dodela is not None
    assert "KM-8" not in dodela.values()


def test_zajednicki_dodeljivac_obe_nedelje_bira_obicnu_salu():
    sale = (
        Prostorija("KM-1", KM, TipProstorije.SALA, None, ""),
        Prostorija("KM-8", KM, TipProstorije.SALA, 3, ""),
    )
    ulaz = _ulaz_kapaciteta(("drugi",))
    model, jedinice, promenljive = napravi_model(
        ulaz,
        sale,
        (),
        Smena.CRVENA,
        sa_nedeljom_b=True,
        samo_lokacije=True,
        sa_ciljem=True,
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.solve(model) == cp_model.OPTIMAL
    dodela = _dodeli_prostorije_obe(
        solver, ulaz, sale, jedinice, promenljive, broj_radnika=1
    )
    assert dodela is not None
    assert set(dodela[0].values()) == {"KM-1"}
    assert set(dodela[1].values()) == {"KM-1"}


def test_location_model_kaznjava_km8_i_u_zasebnom_izboru_nedelje_b():
    sale = tuple(
        Prostorija(f"KM-{broj}", KM, TipProstorije.SALA, None, "")
        for broj in range(1, 7)
    ) + (Prostorija("KM-8", KM, TipProstorije.SALA, 3, ""),)
    ulaz = _ulaz_kapaciteta(("drugi",) * 7, menjaju_se=True)
    model, jedinice, promenljive = napravi_model(
        ulaz,
        sale,
        (),
        Smena.CRVENA,
        sa_nedeljom_b=True,
        samo_lokacije=True,
        sa_ciljem=True,
    )
    for jedinica in jedinice:
        p = promenljive[jedinica.indeks]
        assert p.dan_b is not None and p.lokacije_b is not None
        model.add(p.dan == 0)
        model.add(p.lokacije[KM] == 1)
        model.add(p.dan_b == 0)
        model.add(p.lokacije_b[KM] == 1)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.solve(model) == cp_model.OPTIMAL
    assert len(
        {
            solver.value(promenljive[j.indeks].blok_b)
            for j in jedinice
        }
    ) > 1
    dodela_b = _dodeli_prostorije(
        solver,
        ulaz,
        sale,
        jedinice,
        promenljive,
        nedelja_b=True,
        broj_radnika=1,
    )
    assert dodela_b is not None
    assert "KM-8" not in dodela_b.values()


def test_location_model_meko_pravilo_vazi_i_za_nedelju_b():
    ulaz = _ulaz_kapaciteta(("drugi", "drugi"), menjaju_se=True)
    model, jedinice, promenljive = napravi_model(
        ulaz,
        SALE[:2],
        (),
        Smena.CRVENA,
        sa_nedeljom_b=True,
        samo_lokacije=True,
        sa_ciljem=False,
    )
    for jedinica, blok in zip(jedinice, (1, 2)):
        p = promenljive[jedinica.indeks]
        model.add(p.dan == 0)
        model.add(p.blok == blok)
        model.add(p.lokacije[KM] == 1)
    _fiksiraj_sve(model, jedinice, promenljive, KM, blok=9, nedelja_b=True)

    assert cp_model.CpSolver().solve(model) in (
        cp_model.OPTIMAL,
        cp_model.FEASIBLE,
    )


def test_location_model_dve_informatike_dele_jedinu_specijalnu_ucionicu():
    predmet = "Рачунарство и информатика"
    ulaz = _ulaz_kapaciteta(("drugi", "drugi"))
    zahtevi = tuple(
        Zahtev(
            predmet=predmet,
            razred=z.razred,
            odeljenja=z.odeljenja,
            fond=z.fond,
            fond_korepeticije=0,
            nastavnik=z.nastavnik,
            korepetitor=None,
            smena=z.smena,
            smena_opis=z.smena_opis,
            red=z.red,
            datoteka=z.datoteka,
        )
        for z in ulaz.zahtevi
    )
    ulaz = Ulaz(
        zahtevi,
        ulaz.odeljenja,
        {predmet: Predmet(predmet, False, False)},
        ulaz.skola,
        (
            PraviloProstorije(
                "KM-уч1", NivoPravilaProstorije.OBAVEZNO,
                predmet, (), None, "",
            ),
        ),
    )
    ucionice = (
        Prostorija("KM-уч1", KM, TipProstorije.UCIONICA, None, ""),
        Prostorija("KM-уч2", KM, TipProstorije.UCIONICA, None, ""),
    )
    model, jedinice, promenljive = napravi_model(
        ulaz, ucionice, (), Smena.CRVENA, samo_lokacije=True, sa_ciljem=False
    )
    _fiksiraj_sve(model, jedinice, promenljive, KM)

    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE
