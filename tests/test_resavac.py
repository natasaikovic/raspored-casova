from pathlib import Path

from ortools.sat.python import cp_model

from src.model import (
    Nedostupnost,
    Odeljenje,
    Predmet,
    Prostorija,
    Skola,
    Smena,
    TipProstorije,
    Ulaz,
    Zahtev,
)
from src.proveravac import ucitaj_resenje
from src.resavac import napravi_model, resi_nedelju, resi_obe_nedelje, sacuvaj_csv


SALA = Prostorija("KM-1", "Кнез Милетина 8", TipProstorije.SALA, None, "")
UCIONICA = Prostorija("KM-уч2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, "")


def zahtev(predmet, odeljenje, fond, nastavnik, korepetitor=None):
    return Zahtev(
        predmet=predmet,
        razred="први",
        odeljenja=(odeljenje,),
        fond=fond,
        fond_korepeticije=fond if korepetitor else 0,
        nastavnik=nastavnik,
        korepetitor=korepetitor,
        smena=Smena.CRVENA,
        smena_opis=Smena.CRVENA.value,
        red=2,
    )


def ulaz(zahtevi):
    oznake = {o for z in zahtevi for o in z.odeljenja}
    odeljenja = {
        o: Odeljenje(o, "први", Smena.CRVENA, Skola.OSNOVNA) for o in oznake
    }
    predmeti = {}
    for z in zahtevi:
        igracki = bool(z.korepetitor)
        predmeti[z.predmet] = Predmet(z.predmet, igracki, igracki)
    return Ulaz(tuple(zahtevi), odeljenja, predmeti, Skola.OSNOVNA)


def test_resava_i_odmah_proverava_mali_raspored():
    z = zahtev("Класичан балет", "11", 2, "Мила", "Ива")

    rezultat = resi_nedelju(
        ulaz([z]), (SALA, UCIONICA), (), Smena.CRVENA,
        vremensko_ogranicenje=5, broj_radnika=1,
    )

    assert rezultat.pronadjen
    assert len(rezultat.casovi) == 2
    assert rezultat.casovi[0].blok + 1 == rezultat.casovi[1].blok
    assert rezultat.izvestaj is not None
    assert rezultat.izvestaj.ispravan, rezultat.izvestaj.tekst()


def test_isti_nastavnik_ne_moze_u_dva_odeljenja_istovremeno():
    z1 = zahtev("Теорија 1", "11", 1, "Мила")
    z2 = zahtev("Теорија 2", "12", 1, "Мила")

    rezultat = resi_nedelju(
        ulaz([z1, z2]), (SALA, UCIONICA), (), Smena.CRVENA,
        vremensko_ogranicenje=5, broj_radnika=1,
    )

    assert rezultat.pronadjen
    assert len({cas.termin for cas in rezultat.casovi}) == 2
    assert rezultat.izvestaj is not None and rezultat.izvestaj.ispravan


def test_druga_faza_dodeljuje_razlicite_prostorije_istog_tipa():
    z1 = zahtev("Теорија 1", "11", 1, "Мила")
    z2 = zahtev("Теорија 2", "12", 1, "Ана")
    druga = Prostorija(
        "KM-уч3", "Кнез Милетина 8", TipProstorije.UCIONICA, None, ""
    )

    rezultat = resi_nedelju(
        ulaz([z1, z2]), (UCIONICA, druga), (), Smena.CRVENA,
        vremensko_ogranicenje=5, broj_radnika=1,
    )

    assert rezultat.pronadjen
    po_terminu = {}
    for cas in rezultat.casovi:
        po_terminu.setdefault(cas.termin, []).append(cas.prostorija)
    assert all(
        len(prostorije) == len(set(prostorije))
        for prostorije in po_terminu.values()
    )
    assert rezultat.izvestaj is not None and rezultat.izvestaj.ispravan


def test_solver_zabranjuje_pauzu_osobe_duzu_od_dva_bloka():
    zahtevi = [
        zahtev("Теорија 1", "11", 1, "Мила"),
        zahtev("Теорија 2", "12", 1, "Мила"),
    ]
    model, jedinice, promenljive = napravi_model(
        ulaz(zahtevi), (UCIONICA,), (), Smena.CRVENA
    )
    for jedinica, blok in zip(jedinice, (1, 5)):
        model.add(promenljive[jedinica.indeks].dan == 0)
        model.add(promenljive[jedinica.indeks].blok == blok)

    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def test_solver_zabranjuje_dve_pauze_osobe_u_nedelji():
    zahtevi = [
        zahtev(f"Теорија {i}", odeljenje, 1, "Мила")
        for i, odeljenje in enumerate(("11", "12", "13", "14"), start=1)
    ]
    model, jedinice, promenljive = napravi_model(
        ulaz(zahtevi), (UCIONICA,), (), Smena.CRVENA
    )
    termini = ((0, 1), (0, 3), (1, 1), (1, 3))
    for jedinica, (dan, blok) in zip(jedinice, termini):
        model.add(promenljive[jedinica.indeks].dan == dan)
        model.add(promenljive[jedinica.indeks].blok == blok)

    assert cp_model.CpSolver().solve(model) == cp_model.INFEASIBLE


def test_csv_izlaz_je_na_latinici(tmp_path: Path):
    z = zahtev("Класичан балет", "11", 2, "Мила", "Ива")
    rezultat = resi_nedelju(
        ulaz([z]), (SALA, UCIONICA), (), Smena.CRVENA,
        vremensko_ogranicenje=5, broj_radnika=1,
    )
    putanja = tmp_path / "nedelja.csv"

    sacuvaj_csv(putanja, rezultat.casovi)

    tekst = putanja.read_text(encoding="utf-8")
    assert tekst.startswith("dan,blok,predmet,odeljenja,nastavnik,korepetitor,prostorija")
    assert "Klasičan balet" in tekst
    assert len(ucitaj_resenje(putanja)) == 2


def test_srednjoskolski_dvocasi_istog_predmeta_su_razlicitim_danima():
    z = Zahtev(
        predmet="Класичан балет",
        razred="I",
        odeljenja=("I1",),
        fond=6,
        fond_korepeticije=6,
        nastavnik="Мила",
        korepetitor="Ива",
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
        red=2,
    )
    u = Ulaz(
        (z,),
        {"I1": Odeljenje("I1", "I", Smena.CEO_DAN, Skola.SREDNJA)},
        {z.predmet: Predmet(z.predmet, True, True)},
        Skola.SREDNJA,
    )

    rezultat = resi_nedelju(
        u, (SALA,), (), Smena.CRVENA,
        vremensko_ogranicenje=5, broj_radnika=1,
    )

    assert rezultat.pronadjen
    po_danu = {}
    for cas in rezultat.casovi:
        po_danu.setdefault(cas.dan, []).append(cas.blok)
    assert len(po_danu) == 3
    assert all(sorted(blokovi)[1] == sorted(blokovi)[0] + 1 for blokovi in po_danu.values())
    assert rezultat.izvestaj is not None and rezultat.izvestaj.ispravan


def test_obs_klasicni_balet_ima_dvocas_svakog_radnog_dana():
    z = zahtev("Класичан балет", "11", 10, "Мила", "Ива")

    rezultat = resi_nedelju(
        ulaz([z]), (SALA,), (), Smena.CRVENA,
        vremensko_ogranicenje=5, broj_radnika=1,
    )

    assert rezultat.pronadjen
    po_danu = {}
    for cas in rezultat.casovi:
        po_danu.setdefault(cas.dan, []).append(cas.blok)
    assert set(po_danu) == {"понедељак", "уторак", "среда", "четвртак", "петак"}
    assert all(
        len(blokovi) == 2 and max(blokovi) - min(blokovi) == 1
        for blokovi in po_danu.values()
    )
    assert rezultat.izvestaj is not None and rezultat.izvestaj.ispravan


def test_nedelja_b_koristi_inverznu_smenu_a_srednja_ostaje_ista():
    osnovna = zahtev("Класичан балет", "11", 2, "Мила", "Ива")
    srednja = Zahtev(
        predmet="Савремена игра",
        razred="I",
        odeljenja=("I1",),
        fond=2,
        fond_korepeticije=2,
        nastavnik="Јована",
        korepetitor="Ана",
        smena=Smena.CEO_DAN,
        smena_opis=Smena.CEO_DAN.value,
        red=3,
    )
    u = Ulaz(
        (osnovna, srednja),
        {
            "11": Odeljenje("11", "први", Smena.CRVENA, Skola.OSNOVNA),
            "I1": Odeljenje("I1", "I", Smena.CEO_DAN, Skola.SREDNJA),
        },
        {
            osnovna.predmet: Predmet(osnovna.predmet, True, True),
            srednja.predmet: Predmet(srednja.predmet, True, True),
        },
        None,
    )

    a, b = resi_obe_nedelje(
        u, (SALA,), (), vremensko_ogranicenje=5, broj_radnika=1
    )

    assert a.pronadjen and b.pronadjen
    osnovna_a = [c for c in a.casovi if c.odeljenja == ("11",)]
    osnovna_b = [c for c in b.casovi if c.odeljenja == ("11",)]
    assert all(1 <= c.blok <= 4 for c in osnovna_a)
    assert all(9 <= c.blok <= 14 for c in osnovna_b)
    srednja_a = [
        (c.dan, c.blok, c.predmet, c.nastavnik, c.korepetitor, c.prostorija)
        for c in a.casovi if c.odeljenja == ("I1",)
    ]
    srednja_b = [
        (c.dan, c.blok, c.predmet, c.nastavnik, c.korepetitor, c.prostorija)
        for c in b.casovi if c.odeljenja == ("I1",)
    ]
    assert srednja_a == srednja_b
    assert a.izvestaj is not None and a.izvestaj.ispravan
    assert b.izvestaj is not None and b.izvestaj.ispravan


def test_promena_lokacije_ima_tacno_jedan_putni_blok():
    teorija = zahtev("Теорија", "11", 1, "Ана")
    balet = zahtev("Класичан балет", "11", 2, "Мила", "Ива")
    u = ulaz([teorija, balet])
    sala = Prostorija("S1", "Прва локација", TipProstorije.SALA, None, "")
    ucionica = Prostorija(
        "U1", "Друга локација", TipProstorije.UCIONICA, None, ""
    )
    nedostupnosti = tuple(
        Nedostupnost(osoba, dan, 1, 14, "тест")
        for osoba in ("Ана", "Мила", "Ива")
        for dan in ("уторак", "среда", "четвртак", "петак", "субота")
    )

    rezultat = resi_nedelju(
        u,
        (sala, ucionica),
        nedostupnosti,
        Smena.CRVENA,
        vremensko_ogranicenje=5,
        broj_radnika=1,
    )

    assert rezultat.pronadjen
    assert {cas.dan for cas in rezultat.casovi} == {"понедељак"}
    blokovi = sorted({cas.blok for cas in rezultat.casovi})
    assert [b - a for a, b in zip(blokovi, blokovi[1:])].count(2) == 1
    assert max(blokovi) - min(blokovi) + 1 == len(blokovi) + 1
    assert rezultat.izvestaj is not None
    assert rezultat.izvestaj.ispravan, rezultat.izvestaj.tekst()
