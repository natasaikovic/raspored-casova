from dataclasses import replace
from types import SimpleNamespace

from src.model import Odeljenje, Predmet, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev
from src.proveravac import Cas, proveri
from src.resavac import (
    _dodeli_prostorije,
    _dodeli_prostorije_obe,
    _jedinice,
    _kazna_sala_narodne_igre,
    _moguce_prostorije,
)


GLAVNI = "Народна игра – главни предмет"
REPERTOAR = "Репертоар народне игре"

SALE = (
    Prostorija("KM-1", "Кнез Милетина 8", TipProstorije.SALA, None, ""),
    Prostorija("SG-1", "Спортска гимназија", TipProstorije.SALA, None, ""),
    Prostorija("SG-2", "Спортска гимназија", TipProstorije.SALA, None, ""),
    Prostorija("SG-3", "Спортска гимназија", TipProstorije.SALA, None, ""),
)


def _ulaz(predmet=GLAVNI, odeljenje="IV5"):
    zahtev = Zahtev(
        predmet=predmet,
        razred="IV",
        odeljenja=(odeljenje,),
        fond=2,
        fond_korepeticije=0,
        nastavnik="Маја",
        korepetitor=None,
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
        red=2,
        datoteka="test.csv",
    )
    return Ulaz(
        (zahtev,),
        {odeljenje: Odeljenje(odeljenje, "IV", Smena.CEO_DAN, Skola.SREDNJA)},
        {predmet: Predmet(predmet, True, True)},
        None,
    ), zahtev


def _casovi(predmet, odeljenje, prostorija):
    return (
        Cas("понедељак", 1, predmet, (odeljenje,), "Маја", None, prostorija, 2),
        Cas("понедељак", 2, predmet, (odeljenje,), "Маја", None, prostorija, 3),
    )


class _FiksniSolver:
    def value(self, _):
        return 1

    def boolean_value(self, _):
        return True


def _sukob_za_sg1(menjaju_se=False):
    _, iv5 = _ulaz(GLAVNI, "IV5")
    _, iv4 = _ulaz(GLAVNI, "IV4")
    smena = Smena.CRVENA if menjaju_se else Smena.CEO_DAN
    zahtevi = tuple(
        replace(z, smena=smena, smena_opis=smena.value)
        for z in (iv5, iv4)
    )
    ulaz = Ulaz(
        zahtevi,
        {
            oznaka: Odeljenje(oznaka, "IV", smena, Skola.SREDNJA)
            for oznaka in ("IV5", "IV4")
        },
        {GLAVNI: Predmet(GLAVNI, True, True)},
        None,
    )
    jedinice = _jedinice(ulaz)
    promenljive = {
        jedinica.indeks: SimpleNamespace(
            start=object(),
            start_b=object(),
            lokacije={"Спортска гимназија": object()},
            lokacije_b={"Спортска гимназија": object()},
        )
        for jedinica in jedinice
    }
    return ulaz, jedinice, promenljive


def test_resavac_oba_predmeta_ogranicava_na_sportsku_gimnaziju():
    for predmet in (GLAVNI, REPERTOAR):
        ulaz, zahtev = _ulaz(predmet)
        moguce = _moguce_prostorije(zahtev, ulaz, SALE)
        assert {p.oznaka for p in moguce} == {"SG-1", "SG-2", "SG-3"}


def test_proveravac_zabranjuje_narodnu_igru_van_sportske_gimnazije():
    for predmet in (GLAVNI, REPERTOAR):
        ulaz, _ = _ulaz(predmet)
        izvestaj = proveri(ulaz, SALE, (), _casovi(predmet, "IV5", "KM-1"))
        assert any("мора бити у Спортској гимназији" in g for g in izvestaj.greske)


def test_proveravac_zabranjuje_nepostojecu_sg_salu():
    ulaz, _ = _ulaz(REPERTOAR)
    sale = SALE + (
        Prostorija("SG-4", "Спортска гимназија", TipProstorije.SALA, None, ""),
    )
    izvestaj = proveri(ulaz, sale, (), _casovi(REPERTOAR, "IV5", "SG-4"))
    assert any("мора бити у SG-1, SG-2 или SG-3" in g for g in izvestaj.greske)


def test_prioritet_sg1_i_relativna_tezina_izuzetka():
    _, iv5 = _ulaz(GLAVNI, "IV5")
    _, iv4 = _ulaz(GLAVNI, "IV4")
    assert _kazna_sala_narodne_igre(iv5, "SG-1") == 0
    assert 0 < _kazna_sala_narodne_igre(iv5, "SG-2")
    assert _kazna_sala_narodne_igre(iv5, "SG-2") < _kazna_sala_narodne_igre(
        iv4, "SG-2"
    )


def test_dodela_jedne_nedelje_izuzetak_prvenstveno_daje_iv5():
    ulaz, jedinice, promenljive = _sukob_za_sg1()
    rezultat = _dodeli_prostorije(
        _FiksniSolver(), ulaz, SALE, jedinice, promenljive, broj_radnika=1
    )
    assert rezultat is not None
    assert rezultat[1] == "SG-1"
    assert rezultat[0] in {"SG-2", "SG-3"}


def test_zajednicka_dodela_a_i_b_izuzetak_prvenstveno_daje_iv5():
    ulaz, jedinice, promenljive = _sukob_za_sg1(menjaju_se=True)
    rezultat = _dodeli_prostorije_obe(
        _FiksniSolver(), ulaz, SALE, jedinice, promenljive, broj_radnika=1
    )
    assert rezultat is not None
    for nedelja in rezultat:
        assert nedelja[1] == "SG-1"
        assert nedelja[0] in {"SG-2", "SG-3"}


def test_sg2_je_dozvoljeni_izuzetak_za_iv5():
    ulaz, _ = _ulaz(GLAVNI, "IV5")
    izvestaj = proveri(ulaz, SALE, (), _casovi(GLAVNI, "IV5", "SG-2"))
    assert izvestaj.ispravan, izvestaj.tekst()
    assert any("IV5" in u and "дозвољени изузетак" in u for u in izvestaj.upozorenja)
    assert sum("дозвољени изузетак" in u for u in izvestaj.upozorenja) == 1


def test_sg2_za_drugo_odeljenje_upozorava_da_prednost_ima_iv5():
    ulaz, _ = _ulaz(GLAVNI, "IV4")
    izvestaj = proveri(ulaz, SALE, (), _casovi(GLAVNI, "IV4", "SG-2"))
    assert izvestaj.ispravan, izvestaj.tekst()
    assert any("изузетак треба дати IV5" in u for u in izvestaj.upozorenja)
