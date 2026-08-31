from src.model import Odeljenje, Predmet, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev
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


def test_sg2_je_dozvoljeni_izuzetak_za_iv5():
    ulaz, _ = _ulaz(GLAVNI, "IV5")
    izvestaj = proveri(ulaz, SALE, (), _casovi(GLAVNI, "IV5", "SG-2"))
    assert izvestaj.ispravan, izvestaj.tekst()
    assert any("IV5" in u and "дозвољени изузетак" in u for u in izvestaj.upozorenja)


def test_sg2_za_drugo_odeljenje_upozorava_da_prednost_ima_iv5():
    ulaz, _ = _ulaz(GLAVNI, "IV4")
    izvestaj = proveri(ulaz, SALE, (), _casovi(GLAVNI, "IV4", "SG-2"))
    assert izvestaj.ispravan, izvestaj.tekst()
    assert any("изузетак треба дати IV5" in u for u in izvestaj.upozorenja)
