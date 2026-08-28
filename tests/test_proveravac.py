import csv
from dataclasses import replace

import pytest

from src.model import (
    Odeljenje,
    Predmet,
    Prostorija,
    Skola,
    Smena,
    TipProstorije,
    Ulaz,
    Zahtev,
)
from src.proveravac import Cas, ResenjeGreska, proveri, ucitaj_resenje


def zahtev(
    predmet,
    odeljenja,
    fond,
    nastavnik,
    *,
    razred="први",
    smena=Smena.CRVENA,
    korepetitor=None,
    fond_korepeticije=0,
    red=2,
):
    return Zahtev(
        predmet=predmet,
        razred=razred,
        odeljenja=tuple(odeljenja),
        fond=fond,
        fond_korepeticije=fond_korepeticije,
        nastavnik=nastavnik,
        korepetitor=korepetitor,
        smena=smena,
        smena_opis=smena.value,
        red=red,
        datoteka="test.csv",
    )


def napravi_ulaz(zahtevi, igracki=()):
    igracki = set(igracki)
    odeljenja = {}
    for z in zahtevi:
        skola = Skola.SREDNJA if z.razred in {"I", "II", "III", "IV"} else Skola.OSNOVNA
        for oznaka in z.odeljenja:
            odeljenja[oznaka] = Odeljenje(oznaka, z.razred, z.smena, skola)
    for oznaka, odeljenje in tuple(odeljenja.items()):
        if oznaka.endswith(("А", "Б")) and oznaka[:-1] in odeljenja:
            odeljenja[oznaka] = replace(odeljenje, roditelj=oznaka[:-1])
    predmeti = {
        z.predmet: Predmet(z.predmet, z.predmet in igracki, z.predmet in igracki)
        for z in zahtevi
    }
    return Ulaz(tuple(zahtevi), odeljenja, predmeti, None)


SALE = (
    Prostorija("S1", "Школа", TipProstorije.SALA, 1, ""),
    Prostorija("S2", "Школа", TipProstorije.SALA, 1, ""),
)
UCIONICE = (
    Prostorija("U1", "Школа", TipProstorije.UCIONICA, None, ""),
    Prostorija("U2", "Школа", TipProstorije.UCIONICA, None, ""),
)


def test_ucitava_jedan_red_resenja(tmp_path):
    putanja = tmp_path / "resenje.csv"
    with putanja.open("w", encoding="utf-8", newline="") as datoteka:
        pisac = csv.writer(datoteka)
        pisac.writerow(
            ["дан", "блок", "предмет", "одељења", "наставник", "корепетитор", "просторија"]
        )
        pisac.writerow(["понедељак", "1", "Историја", "I1;I2", "Ана", "", "U1"])

    casovi = ucitaj_resenje(putanja)

    assert casovi == (
        Cas("понедељак", 1, "Историја", ("I1", "I2"), "Ана", None, "U1", 2),
    )


def test_odeljenja_se_ne_razdvajaju_zarezom(tmp_path):
    putanja = tmp_path / "resenje.csv"
    putanja.write_text(
        "дан,блок,предмет,одељења,наставник,корепетитор,просторија\n"
        'понедељак,1,Историја,"I1,I2",Ана,,U1\n',
        encoding="utf-8",
    )

    with pytest.raises(ResenjeGreska, match="раздвајају знаком ;"):
        ucitaj_resenje(putanja)


def test_ispravan_dvocas_osnovne_skole():
    z = zahtev(
        "Класичан балет",
        ["11"],
        2,
        "Мила",
        korepetitor="Ива",
        fond_korepeticije=2,
    )
    ulaz = napravi_ulaz([z], igracki={z.predmet})
    casovi = (
        Cas("понедељак", 1, z.predmet, ("11",), "Мила", "Ива", "S1", 2),
        Cas("понедељак", 2, z.predmet, ("11",), "Мила", "Ива", "S1", 3),
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert izvestaj.ispravan
    assert izvestaj.greske == []


def test_obs_klasicni_fond_10_zahteva_dvocas_svakog_radnog_dana():
    z = zahtev(
        "Класичан балет",
        ["11"],
        10,
        "Мила",
        korepetitor="Ива",
        fond_korepeticije=10,
    )
    ulaz = napravi_ulaz([z], igracki={z.predmet})
    dani = ("понедељак", "уторак", "среда", "четвртак", "субота")
    casovi = tuple(
        Cas(dan, blok, z.predmet, ("11",), "Мила", "Ива", "S1", red)
        for red, (dan, blok) in enumerate(
            ((dan, blok) for dan in dani for blok in (1, 2)),
            start=2,
        )
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert not izvestaj.ispravan
    assert any(
        "мора имати тачно један двочас сваког дана од понедељка до петка" in greska
        for greska in izvestaj.greske
    )


def test_obs_klasicni_fond_10_zahteva_uzastopne_casove_svakog_dana():
    z = zahtev(
        "Класичан балет",
        ["11"],
        10,
        "Мила",
        korepetitor="Ива",
        fond_korepeticije=10,
    )
    ulaz = napravi_ulaz([z], igracki={z.predmet})
    dani = ("понедељак", "уторак", "среда", "четвртак", "петак")
    casovi = tuple(
        Cas(dan, blok, z.predmet, ("11",), "Мила", "Ива", "S1", red)
        for red, (dan, blok) in enumerate(
            ((dan, blok) for dan in dani for blok in (1, 3)),
            start=2,
        )
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert not izvestaj.ispravan
    assert any(
        "мора имати тачно један двочас сваког дана од понедељка до петка" in greska
        for greska in izvestaj.greske
    )


def test_latinicno_resenje_se_povezuje_sa_cirilicnim_ulazom():
    z = zahtev(
        "Класичан балет",
        ["11"],
        2,
        "Мила",
        korepetitor="Ива",
        fond_korepeticije=2,
    )
    ulaz = napravi_ulaz([z], igracki={z.predmet})
    casovi = (
        Cas("ponedeljak", 1, "Klasičan balet", ("11",), "Mila", "Iva", "S1", 2),
        Cas("ponedeljak", 2, "Klasičan balet", ("11",), "Mila", "Iva", "S1", 3),
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert izvestaj.ispravan, izvestaj.tekst(latinica=True)


def test_prijavljuje_sudar_nastavnika():
    z1 = zahtev("Класичан балет", ["11"], 1, "Мила", red=2)
    z2 = zahtev("Класичан балет", ["12"], 1, "Мила", red=3)
    ulaz = napravi_ulaz([z1, z2], igracki={z1.predmet})
    casovi = (
        Cas("понедељак", 1, z1.predmet, ("11",), "Мила", None, "S1", 2),
        Cas("понедељак", 1, z2.predmet, ("12",), "Мила", None, "S2", 3),
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert not izvestaj.ispravan
    assert any("особа Мила је заузета више пута" in g for g in izvestaj.greske)


def test_opsti_predmeti_mogu_drugacije_da_se_grupisu():
    z1 = zahtev(
        "Историја балета", ["I1", "I2"], 1, "Ана", razred="I", smena=Smena.CEO_DAN, red=2
    )
    z2 = zahtev(
        "Историја балета", ["I3"], 1, "Ана", razred="I", smena=Smena.CEO_DAN, red=3
    )
    ulaz = napravi_ulaz([z1, z2])
    casovi = (
        Cas("понедељак", 1, z1.predmet, ("I1", "I3"), "Ана", None, "U1", 2),
        Cas("понедељак", 2, z1.predmet, ("I2",), "Ана", None, "U1", 3),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert izvestaj.ispravan, izvestaj.tekst()


def test_verska_i_gradjansko_smeju_da_se_preklapaju():
    z1 = zahtev(VERSKA := "Верска настава", ["I1"], 1, "Ђорђе", razred="I", smena=Smena.CEO_DAN)
    z2 = zahtev(
        GRADJANSKO := "Грађанско васпитање",
        ["I1"],
        1,
        "Лидија",
        razred="I",
        smena=Smena.CEO_DAN,
        red=3,
    )
    ulaz = napravi_ulaz([z1, z2])
    casovi = (
        Cas("понедељак", 1, VERSKA, ("I1",), "Ђорђе", None, "U1", 2),
        Cas("понедељак", 1, GRADJANSKO, ("I1",), "Лидија", None, "U2", 3),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert izvestaj.ispravan, izvestaj.tekst()


def test_pogresan_fond_i_tip_prostorije_se_prijavljuju():
    z = zahtev("Историја балета", ["11"], 2, "Ана")
    ulaz = napravi_ulaz([z])
    casovi = (Cas("понедељак", 1, z.predmet, ("11",), "Ана", None, "S1", 2),)

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert any("потребно 2, распоређено 1" in g for g in izvestaj.greske)
    assert any("тражи учионица" in g for g in izvestaj.greske)


def test_celo_odeljenje_ne_sme_da_se_preklopi_sa_polugrupom():
    z1 = zahtev("Народна игра", ["I5"], 1, "Маја", razred="I", smena=Smena.CEO_DAN)
    z2 = zahtev("Класичан балет", ["I5А"], 1, "Нина", razred="I", smena=Smena.CEO_DAN, red=3)
    # Prisustvo I5Б omogućava modelu da prepozna obe polovine celog I5.
    z3 = zahtev("Класичан балет", ["I5Б"], 1, "Ива", razred="I", smena=Smena.CEO_DAN, red=4)
    ulaz = napravi_ulaz([z1, z2, z3], igracki={z1.predmet, z2.predmet})
    casovi = (
        Cas("понедељак", 1, z1.predmet, ("I5",), "Маја", None, "S1", 2),
        Cas("понедељак", 1, z2.predmet, ("I5А",), "Нина", None, "S2", 3),
        Cas("понедељак", 2, z3.predmet, ("I5Б",), "Ива", None, "S2", 4),
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert any("одељење/полугрупа I5А има преклапање" in g for g in izvestaj.greske)


def test_glavni_predmet_srednje_mora_biti_dvocas():
    z = zahtev(
        "Класичан балет – главни предмет",
        ["I1"],
        2,
        "Роса",
        razred="I",
        smena=Smena.CEO_DAN,
    )
    ulaz = napravi_ulaz([z], igracki={z.predmet})
    casovi = (
        Cas("понедељак", 1, z.predmet, ("I1",), "Роса", None, "S1", 2),
        Cas("уторак", 1, z.predmet, ("I1",), "Роса", None, "S1", 3),
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert any("очекује се 1 двочаса" in g for g in izvestaj.greske)
    assert any("тачно један двочас дневно" in g for g in izvestaj.greske)


def test_nedostupnost_nastavnika_se_postuje():
    from src.model import Nedostupnost

    z = zahtev("Историја", ["11"], 1, "Ана")
    ulaz = napravi_ulaz([z])
    casovi = (Cas("понедељак", 1, z.predmet, ("11",), "Ана", None, "U1", 2),)
    nedostupnost = (Nedostupnost("Ана", "понедељак", 1, 4, ""),)

    izvestaj = proveri(ulaz, UCIONICE, nedostupnost, casovi)

    assert any("наставник Ана није доступан" in g for g in izvestaj.greske)


def test_prazan_cas_bez_promene_lokacije_je_greska():
    z1 = zahtev("Историја", ["11"], 1, "Ана")
    z2 = zahtev("Солфеђо", ["11"], 1, "Ива", red=3)
    ulaz = napravi_ulaz([z1, z2])
    casovi = (
        Cas("понедељак", 1, z1.predmet, ("11",), "Ана", None, "U1", 2),
        Cas("понедељак", 3, z2.predmet, ("11",), "Ива", None, "U2", 3),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert any("има празан час без промене локације" in g for g in izvestaj.greske)


def test_promena_lokacije_trazi_tacno_jedan_slobodan_blok():
    z1 = zahtev("Историја", ["11"], 1, "Ана")
    z2 = zahtev("Солфеђо", ["11"], 1, "Ива", red=3)
    ulaz = napravi_ulaz([z1, z2])
    prostorije = (
        Prostorija("U1", "Прва локација", TipProstorije.UCIONICA, None, ""),
        Prostorija("U3", "Друга локација", TipProstorije.UCIONICA, None, ""),
    )
    casovi = (
        Cas("понедељак", 1, z1.predmet, ("11",), "Ана", None, "U1", 2),
        Cas("понедељак", 4, z2.predmet, ("11",), "Ива", None, "U3", 3),
    )

    izvestaj = proveri(ulaz, prostorije, (), casovi)

    assert any(
        "мења локацију са паузом дужом од једног блока" in g
        for g in izvestaj.greske
    )


def test_nepoznato_prvo_odeljenje_ne_obara_proveravac():
    z = zahtev("Историја", ["I1"], 1, "Ана", razred="I", smena=Smena.CEO_DAN)
    ulaz = napravi_ulaz([z])
    casovi = (
        Cas("понедељак", 1, z.predmet, ("XX", "I1"), "Ана", None, "U1", 2),
    )

    izvestaj = proveri(ulaz, UCIONICE, (), casovi)

    assert not izvestaj.ispravan
    assert any("непознато одељење XX" in g for g in izvestaj.greske)


def test_p1_koristi_vidljivu_privremenu_pretpostavku():
    z = zahtev(
        "Класичан балет",
        ["П1"],
        6,
        "Исидора",
        smena=Smena.POSEBNA,
    )
    z = replace(
        z,
        smena_opis="стално од 18,30 часова понедељком средом петком",
    )
    ulaz = napravi_ulaz([z], igracki={z.predmet})
    casovi = tuple(
        Cas(dan, blok, z.predmet, ("П1",), "Исидора", None, "S1", red)
        for red, (dan, blok) in enumerate(
            [
                ("понедељак", 13),
                ("понедељак", 14),
                ("среда", 13),
                ("среда", 14),
                ("петак", 13),
                ("петак", 14),
            ],
            start=2,
        )
    )

    izvestaj = proveri(ulaz, SALE, (), casovi)

    assert izvestaj.ispravan, izvestaj.tekst()
    assert any("привремено протумачено" in u for u in izvestaj.upozorenja)
