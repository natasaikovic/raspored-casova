from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from src.model import (
    DostupnostProstorije,
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
from src.pravila_prostorija import (
    dozvoljena_prostorija,
    kazna_prostorije,
    prostorija_dostupna,
)
from src.resavac import napravi_model, ucitaj_standardne_ulaze
from src.resavac import _moguce_prostorije
from src.loader import UlazGreska, proveri_veze_pravila_prostorija
from src.proveravac import Cas, proveri


def _pravilo(soba, nivo, predmet="Тест", odeljenje=()):
    return PraviloProstorije(soba, nivo, predmet, odeljenje, None, "")


def test_redosled_prvi_drugi_nepokriveno_izuzetno():
    ulaz, _, _ = ucitaj_standardne_ulaze("ulazi")
    zahtev = replace(ulaz.zahtevi[0], predmet="Тест", odeljenja=("I1",))
    pravila = (
        _pravilo("A", NivoPravilaProstorije.PRVI),
        _pravilo("B", NivoPravilaProstorije.DRUGI),
        _pravilo("D", NivoPravilaProstorije.IZUZETNO),
    )

    kazne = [kazna_prostorije(pravila, zahtev, soba, 1) for soba in "ABCD"]
    assert kazne == [0, 1_000, 10_000, 100_000]


def test_grupisani_cas_mora_zadovoljiti_obavezni_skup_svakog_odeljenja():
    ulaz, _, _ = ucitaj_standardne_ulaze("ulazi")
    zahtev = replace(ulaz.zahtevi[0], predmet="Тест", odeljenja=("I1", "I2"))
    pravila = (
        _pravilo("A", NivoPravilaProstorije.OBAVEZNO, odeljenje=("I1",)),
        _pravilo("A", NivoPravilaProstorije.OBAVEZNO, odeljenje=("I2",)),
        _pravilo("B", NivoPravilaProstorije.OBAVEZNO, odeljenje=("I1",)),
    )

    assert dozvoljena_prostorija(pravila, zahtev, "A", 1)
    assert not dozvoljena_prostorija(pravila, zahtev, "B", 1)


def test_grupisani_cas_sabira_meke_nivoe_svih_odeljenja():
    ulaz, _, _ = ucitaj_standardne_ulaze("ulazi")
    zahtev = replace(ulaz.zahtevi[0], predmet="Тест", odeljenja=("I1", "I2"))
    pravila = (
        _pravilo("A", NivoPravilaProstorije.PRVI, odeljenje=("I1",)),
        _pravilo("A", NivoPravilaProstorije.DRUGI, odeljenje=("I2",)),
    )

    assert kazna_prostorije(pravila, zahtev, "A", 1) == 1_000
    assert kazna_prostorije(pravila, zahtev, "B", 1) == 20_000


def test_konkretni_predmet_nadglasava_wildcard_zabranu():
    ulaz, _, _ = ucitaj_standardne_ulaze("ulazi")
    zahtev = replace(ulaz.zahtevi[0], predmet="Тест", odeljenja=("I1",))
    pravila = (
        _pravilo("A", NivoPravilaProstorije.ZABRANJENO, predmet="*"),
        _pravilo("A", NivoPravilaProstorije.IZUZETNO),
    )

    assert dozvoljena_prostorija(pravila, zahtev, "A", 1)


def test_np_aliasi_daju_uniju_whitelist_dostupnosti():
    dostupnosti = (
        DostupnostProstorije("NP-1", "понедељак", 10, 11, ""),
        DostupnostProstorije("NP-2", "среда", 10, 11, ""),
    )

    assert prostorija_dostupna(dostupnosti, "NP-сала", "понедељак", (10, 11))
    assert prostorija_dostupna(dostupnosti, "NP-сала", "среда", (10, 11))
    assert not prostorija_dostupna(dostupnosti, "NP-сала", "уторак", (10, 11))


def test_loader_odbija_sukob_nivoa_posle_np_kanonizacije():
    ulaz, sobe, _ = ucitaj_standardne_ulaze("ulazi")
    pravila = (
        _pravilo(
            "NP-1", NivoPravilaProstorije.PRVI,
            predmet="Репертоар класичног балета", odeljenje=("III1",),
        ),
        _pravilo(
            "NP-2", NivoPravilaProstorije.DRUGI,
            predmet="Репертоар класичног балета", odeljenje=("III1",),
        ),
    )

    with pytest.raises(UlazGreska, match="NP канонизација даје сукоб"):
        proveri_veze_pravila_prostorija(ulaz, sobe, pravila, ())


def test_model_prve_faze_ima_konkretne_prostorije_i_nema_cilj():
    ulaz, prostorije, nedostupnosti = ucitaj_standardne_ulaze("ulazi")
    model, jedinice, promenljive = napravi_model(
        ulaz, prostorije, nedostupnosti,
        next(iter((ulaz.odeljenja[o].smena for o in ulaz.odeljenja if o == "11"))),
        samo_lokacije=False,
        sa_ciljem=False,
    )

    assert not model.has_objective()
    assert jedinice
    assert all(p.prostorije for p in promenljive.values())
    assert len(model.proto.constraints) > 0
    pg_jedinica = next(
        j for j in jedinice
        if ulaz.zahtevi[j.zahtev_indeks].predmet == "Примењена гимнастика"
    )
    assert set(promenljive[pg_jedinica.indeks].lokacije) == {
        "Кнез Милетина 8", "Спортска гимназија",
    }
    assert "KM-8" in promenljive[pg_jedinica.indeks].prostorije
    assert "SG-2" in promenljive[pg_jedinica.indeks].prostorije


def _mali_ulaz(pravila):
    zahtev = Zahtev(
        "Тест", "I", ("I1",), 2, 0, "Ана", None,
        Smena.CEO_DAN, Smena.CEO_DAN.value, 2, "test.csv",
    )
    return Ulaz(
        (zahtev,),
        {"I1": Odeljenje("I1", "I", Smena.CEO_DAN, Skola.SREDNJA)},
        {"Тест": Predmet("Тест", False, False)},
        None,
        pravila,
    )


def test_proveravac_tvrdu_zabranu_prijavljuje_kao_gresku():
    pravila = (_pravilo("U1", NivoPravilaProstorije.ZABRANJENO),)
    ulaz = _mali_ulaz(pravila)
    sobe = (Prostorija("U1", "Школа", TipProstorije.UCIONICA, None, ""),)
    casovi = (
        Cas("понедељак", 1, "Тест", ("I1",), "Ана", None, "U1", 2),
        Cas("понедељак", 2, "Тест", ("I1",), "Ана", None, "U1", 3),
    )

    izvestaj = proveri(ulaz, sobe, (), casovi)
    assert any("структурисана правила забрањују" in g for g in izvestaj.greske)


def test_proveravac_deduplicira_upozorenje_za_dvocas():
    pravila = (
        _pravilo("U1", NivoPravilaProstorije.PRVI),
        _pravilo("U2", NivoPravilaProstorije.DRUGI),
    )
    ulaz = _mali_ulaz(pravila)
    sobe = (
        Prostorija("U1", "Школа", TipProstorije.UCIONICA, None, ""),
        Prostorija("U2", "Школа", TipProstorije.UCIONICA, None, ""),
    )
    casovi = (
        Cas("понедељак", 1, "Тест", ("I1",), "Ана", None, "U2", 2),
        Cas("понедељак", 2, "Тест", ("I1",), "Ана", None, "U2", 3),
    )

    izvestaj = proveri(ulaz, sobe, (), casovi)
    poruke = [u for u in izvestaj.upozorenja if "бољи изричити избор" in u]
    assert len(poruke) == 1


def test_standardno_ucitavanje_jasno_prijavljuje_nedostajuci_novi_csv(tmp_path):
    izvor = Path("ulazi").resolve()
    for ime in (
        "osnovna_baletska_skola.csv",
        "srednja_baletska_skola.csv",
        "ostali_casovi.csv",
        "prostorije.csv",
        "nedostupnost.csv",
        "dostupnost_prostorija.csv",
    ):
        (tmp_path / ime).symlink_to(izvor / ime)

    with pytest.raises(UlazGreska, match="pravila_prostorija.csv"):
        ucitaj_standardne_ulaze(tmp_path)


def test_aktivna_pravila_dozvoljavaju_pg_u_svim_salama_i_filtriraju_np():
    ulaz, sobe, _ = ucitaj_standardne_ulaze("ulazi")
    pg = next(z for z in ulaz.zahtevi if z.predmet == "Примењена гимнастика")
    rkb = next(
        z for z in ulaz.zahtevi
        if z.predmet == "Репертоар класичног балета" and z.odeljenja == ("IV1",)
    )

    assert {p.oznaka for p in _moguce_prostorije(pg, ulaz, sobe, 2)} == {
        "KM-1", "KM-2", "KM-3", "KM-4", "KM-5", "KM-6", "KM-8",
        "SG-1", "SG-2", "SG-3",
    }
    assert {p.oznaka for p in _moguce_prostorije(rkb, ulaz, sobe, 2)} == {"NP-сала"}


def test_tradicionalno_pevanje_sme_izuzetno_u_km8():
    ulaz, sobe, _ = ucitaj_standardne_ulaze("ulazi")
    pevanje = next(
        z for z in ulaz.zahtevi if z.predmet == "Традиционално певање"
    )

    assert "KM-8" in {
        p.oznaka for p in _moguce_prostorije(pevanje, ulaz, sobe, 1)
    }


def test_model_termina_optimizuje_konkretnu_sobu_po_csv_nivou():
    pravila = (
        _pravilo("U1", NivoPravilaProstorije.PRVI),
        _pravilo("U2", NivoPravilaProstorije.IZUZETNO),
    )
    ulaz = _mali_ulaz(pravila)
    sobe = (
        Prostorija("U1", "Школа", TipProstorije.UCIONICA, None, ""),
        Prostorija("U2", "Школа", TipProstorije.UCIONICA, None, ""),
    )
    model, jedinice, promenljive = napravi_model(
        ulaz, sobe, (), Smena.CRVENA, samo_lokacije=False, sa_ciljem=True
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.solve(model) == cp_model.OPTIMAL
    izbor = promenljive[jedinice[0].indeks].prostorije
    assert solver.boolean_value(izbor["U1"])
