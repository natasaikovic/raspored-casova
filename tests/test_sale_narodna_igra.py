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
from src.resavac import _moguce_prostorije


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
    pravila = ()
    if predmet == GLAVNI:
        pravila = (
            PraviloProstorije(
                "SG-1", NivoPravilaProstorije.OBAVEZNO,
                GLAVNI, (odeljenje,), None, "",
            ),
        )
    return Ulaz(
        (zahtev,),
        {odeljenje: Odeljenje(odeljenje, "IV", Smena.CEO_DAN, Skola.SREDNJA)},
        {predmet: Predmet(predmet, True, True)},
        None,
        pravila,
    ), zahtev


def _casovi(predmet, odeljenje, prostorija):
    return (
        Cas("понедељак", 1, predmet, (odeljenje,), "Маја", None, prostorija, 2),
        Cas("понедељак", 2, predmet, (odeljenje,), "Маја", None, prostorija, 3),
    )


def test_resavac_oba_predmeta_ogranicava_na_sportsku_gimnaziju():
    ulaz, zahtev = _ulaz(GLAVNI)
    assert {p.oznaka for p in _moguce_prostorije(zahtev, ulaz, SALE)} == {"SG-1"}
    ulaz, zahtev = _ulaz(REPERTOAR)
    assert {p.oznaka for p in _moguce_prostorije(zahtev, ulaz, SALE)} == {
        "SG-1", "SG-2", "SG-3",
    }


def test_proveravac_zabranjuje_narodnu_igru_van_sportske_gimnazije():
    for predmet in (GLAVNI, REPERTOAR):
        ulaz, _ = _ulaz(predmet)
        izvestaj = proveri(ulaz, SALE, (), _casovi(predmet, "IV5", "KM-1"))
        assert izvestaj.greske


def test_proveravac_zabranjuje_nepostojecu_sg_salu():
    ulaz, _ = _ulaz(REPERTOAR)
    sale = SALE + (
        Prostorija("SG-4", "Спортска гимназија", TipProstorije.SALA, None, ""),
    )
    izvestaj = proveri(ulaz, sale, (), _casovi(REPERTOAR, "IV5", "SG-4"))
    assert any("мора бити у SG-1, SG-2 или SG-3" in g for g in izvestaj.greske)


def test_sg2_vise_nije_izuzetak_za_glavni_predmet():
    ulaz, _ = _ulaz(GLAVNI, "IV5")
    izvestaj = proveri(ulaz, SALE, (), _casovi(GLAVNI, "IV5", "SG-2"))
    assert any("структурисана правила забрањују" in g for g in izvestaj.greske)
    assert not any("приоритет је SG-1" in u for u in izvestaj.upozorenja)
