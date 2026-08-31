from src.model import Odeljenje, Predmet, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev
from src.proveravac import Cas, proveri
from src.resavac import _tokeni_odeljenja


def _zahtev(predmet, odeljenja, nastavnik, red):
    return Zahtev(
        predmet=predmet,
        razred="I",
        odeljenja=tuple(odeljenja),
        fond=1,
        fond_korepeticije=0,
        nastavnik=nastavnik,
        korepetitor=None,
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
        red=red,
        datoteka="test.csv",
    )


def _ulaz(zahtevi):
    odeljenja = {
        "I1": Odeljenje("I1", "I", Smena.CEO_DAN, Skola.SREDNJA),
        "I3": Odeljenje("I3", "I", Smena.CEO_DAN, Skola.SREDNJA),
        "I5": Odeljenje("I5", "I", Smena.CEO_DAN, Skola.SREDNJA),
        "I5А": Odeljenje("I5А", "I", Smena.CEO_DAN, Skola.SREDNJA, roditelj="I5"),
        "I5Б": Odeljenje("I5Б", "I", Smena.CEO_DAN, Skola.SREDNJA, roditelj="I5"),
    }
    predmeti = {
        z.predmet: Predmet(z.predmet, False, False)
        for z in zahtevi
    }
    return Ulaz(tuple(zahtevi), odeljenja, predmeti, None)


UCIONICE = (
    Prostorija("U1", "Кнез Милетина 8", TipProstorije.UCIONICA, None, ""),
    Prostorija("U2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, ""),
)


def test_resavac_siri_celo_odeljenje_na_sve_polugrupe_i_spojene_grupe():
    ulaz = _ulaz([])

    assert _tokeni_odeljenja(ulaz, ("I5",)) == frozenset({"I5А", "I5Б"})
    assert _tokeni_odeljenja(ulaz, ("I1", "I5")) == frozenset(
        {"I1", "I5А", "I5Б"}
    )
    assert _tokeni_odeljenja(ulaz, ("I5А",)) == frozenset({"I5А"})


def test_polugrupe_popunjavaju_cas_celog_odeljenja_bez_lazne_pauze():
    z_celo_1 = _zahtev("Предмет целог одељења 1", ["I5"], "Ана", 2)
    z_a = _zahtev("Предмет полугрупе А", ["I5А"], "Мила", 3)
    z_b = _zahtev("Предмет полугрупе Б", ["I5Б"], "Ива", 4)
    z_celo_2 = _zahtev("Предмет целог одељења 2", ["I5"], "Нина", 5)
    ulaz = _ulaz([z_celo_1, z_a, z_b, z_celo_2])
    casovi = (
        Cas("понедељак", 1, z_celo_1.predmet, ("I5",), "Ана", None, "U1", 2),
        Cas("понедељак", 2, z_a.predmet, ("I5А",), "Мила", None, "U1", 3),
        Cas("понедељак", 2, z_b.predmet, ("I5Б",), "Ива", None, "U2", 4),
        Cas("понедељак", 3, z_celo_2.predmet, ("I5",), "Нина", None, "U1", 5),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert not any("празан час" in g for g in izvestaj.greske), izvestaj.tekst()


def test_proveravac_prijavljuje_pauzu_jedne_polugrupe_iako_druga_ima_cas():
    z_celo = _zahtev("Заједнички предмет", ["I5"], "Ана", 2)
    z_b = _zahtev("Предмет полугрупе Б", ["I5Б"], "Ива", 3)
    z_a = _zahtev("Предмет полугрупе А", ["I5А"], "Мила", 4)
    ulaz = _ulaz([z_celo, z_b, z_a])
    casovi = (
        Cas("понедељак", 1, z_celo.predmet, ("I5",), "Ана", None, "U1", 2),
        Cas("понедељак", 2, z_b.predmet, ("I5Б",), "Ива", None, "U2", 3),
        Cas("понедељак", 3, z_a.predmet, ("I5А",), "Мила", None, "U1", 4),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert any("I5А има празан час" in g for g in izvestaj.greske), izvestaj.tekst()


def test_proveravac_prijavljuje_pauzu_unutar_spojene_grupe():
    z_spojeni = _zahtev("Спојени предмет", ["I1", "I3"], "Ана", 2)
    z_i1 = _zahtev("Самостални предмет I1", ["I1"], "Мила", 3)
    ulaz = _ulaz([z_spojeni, z_i1])
    casovi = (
        Cas("понедељак", 1, z_spojeni.predmet, ("I1", "I3"), "Ана", None, "U1", 2),
        Cas("понедељак", 3, z_i1.predmet, ("I1",), "Мила", None, "U1", 3),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert any("I1 има празан час" in g for g in izvestaj.greske), izvestaj.tekst()
