from pathlib import Path

from ortools.sat.python import cp_model

from src.izuzeci import dozvoljen_peti_cas, dozvoljen_peti_cas_solfedja
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
from src.proveravac import Cas, Izvestaj, _proveri_smenu, proveri
from src.resavac import (
    _dozvoljeni_poceci,
    napravi_model,
    ucitaj_standardne_ulaze,
)


SALA = Prostorija("KM-4", "Кнез Милетина 8", TipProstorije.SALA, 1, "")


def _zahtev(ulaz, nastavnik, odeljenje):
    return next(z for z in ulaz.zahtevi if z.predmet == "Солфеђо" and z.nastavnik == nastavnik and odeljenje in z.odeljenja)


def test_peti_cas_samo_za_tri_odobrena_solfedja():
    assert dozvoljen_peti_cas_solfedja("Солфеђо", "Марија Цветковић", ("41",))
    assert dozvoljen_peti_cas_solfedja("Солфеђо", "Соња Пана Виријевић", ("42",))
    assert dozvoljen_peti_cas_solfedja("Солфеђо", "Јелена Михаиловић Красић", ("43",))
    assert not dozvoljen_peti_cas_solfedja("Солфеђо", "Ђорђина Убовић", ("31",))
    assert not dozvoljen_peti_cas_solfedja("Класичан балет", "Марија Цветковић", ("41",))
    assert not dozvoljen_peti_cas_solfedja(
        "Историјско балске игре", "Теодора Мартиновски", ("41",)
    )


def test_opsti_predikat_dozvoljava_samo_odobrene_kombinacije():
    assert dozvoljen_peti_cas("Солфеђо", "Марија Цветковић", ("41",))
    assert dozvoljen_peti_cas(
        "Историјско балске игре", "Теодора Мартиновски", ("41",)
    )
    assert not dozvoljen_peti_cas(
        "Класичан балет", "Теодора Мартиновски", ("41",)
    )
    assert not dozvoljen_peti_cas(
        "Историјско балске игре", "Други наставник", ("41",)
    )
    assert not dozvoljen_peti_cas(
        "Историјско балске игре", "Теодора Мартиновски", ("42",)
    )


def test_solver_dozvoljava_blok_5_samo_kad_je_ta_smena_jutarnja():
    ulaz, _, nedostupnosti = ucitaj_standardne_ulaze(Path("ulazi"))
    marija = _zahtev(ulaz, "Марија Цветковић", "41")
    assert any(blok == 5 for _, blok in _dozvoljeni_poceci(marija, 1, Smena.CRVENA, nedostupnosti))
    assert all(blok != 5 for _, blok in _dozvoljeni_poceci(marija, 1, Smena.PLAVA, nedostupnosti))


def test_proveravac_prihvata_peti_cas_odobrenog_solfedja():
    ulaz, _, _ = ucitaj_standardne_ulaze(Path("ulazi"))
    zahtev = _zahtev(ulaz, "Марија Цветковић", "41")
    cas = Cas("понедељак", 5, "Солфеђо", ("41",), "Марија Цветковић", None, "KM-уч2", 2)
    izvestaj = Izvestaj()
    _proveri_smenu(cas, zahtev, Smena.CRVENA, izvestaj)
    assert not izvestaj.greske


def _zahtev_41(predmet, fond, nastavnik, korepetitor, red):
    return Zahtev(
        predmet=predmet,
        razred="четврти",
        odeljenja=("41",),
        fond=fond,
        fond_korepeticije=fond,
        nastavnik=nastavnik,
        korepetitor=korepetitor,
        smena=Smena.CRVENA,
        smena_opis=Smena.CRVENA.value,
        red=red,
        datoteka="test.csv",
    )


def _ulaz_41(*, fond_klasicnog=10, sa_dodatnim_dvocasom=False):
    zahtevi = [
        _zahtev_41(
            "Класичан балет", fond_klasicnog,
            "Теодора Мартиновски", "Ана Никчевић Торбица", 2,
        ),
        _zahtev_41(
            "Историјско балске игре", 1,
            "Теодора Мартиновски", "Мирјана Анђелковић", 3,
        ),
    ]
    if sa_dodatnim_dvocasom:
        zahtevi.append(
            _zahtev_41("Савремена игра", 2, "Нина Пантовић", "Василије Пуцар", 4)
        )
    predmeti = {
        z.predmet: Predmet(z.predmet, igracki=True, trazi_salu=True)
        for z in zahtevi
    }
    return Ulaz(
        tuple(zahtevi),
        {"41": Odeljenje("41", "четврти", Smena.CRVENA, Skola.OSNOVNA)},
        predmeti,
        Skola.OSNOVNA,
    )


def _fiksiraj(model, ulaz, jedinice, promenljive, predmet, dan, blok):
    jedinica = next(
        j
        for j in jedinice
        if j.redni_broj == 0
        and ulaz.zahtevi[j.zahtev_indeks].predmet == predmet
    )
    model.add(promenljive[jedinica.indeks].dan == dan)
    model.add(promenljive[jedinica.indeks].blok == blok)


def _status_fiksiranog_rasporeda(pozicije, *, sa_dodatnim_dvocasom=False):
    ulaz = _ulaz_41(sa_dodatnim_dvocasom=sa_dodatnim_dvocasom)
    model, jedinice, promenljive = napravi_model(
        ulaz,
        (SALA,), (), Smena.CRVENA, sa_ciljem=False,
    )
    for predmet, blok in pozicije:
        _fiksiraj(model, ulaz, jedinice, promenljive, predmet, 0, blok)
    return cp_model.CpSolver().solve(model)


def test_solver_prihvata_klasicni_3_4_i_istorijsko_balske_5():
    status = _status_fiksiranog_rasporeda((
        ("Класичан балет", 3),
        ("Историјско балске игре", 5),
    ))
    assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)


def test_solver_i_dalje_odbija_vise_od_cetiri_stvarna_casa():
    status = _status_fiksiranog_rasporeda((
        ("Савремена игра", 1),
        ("Класичан балет", 3),
        ("Историјско балске игре", 5),
    ), sa_dodatnim_dvocasom=True)
    assert status == cp_model.INFEASIBLE


def test_solver_i_dalje_odbija_prazan_blok_pre_pete_casa():
    status = _status_fiksiranog_rasporeda((
        ("Класичан балет", 2),
        ("Историјско балске игре", 5),
    ))
    assert status == cp_model.INFEASIBLE


def test_proveravac_prihvata_tri_uzastopna_stvarna_casa_u_blokovima_3_do_5():
    ulaz = _ulaz_41(fond_klasicnog=2)
    casovi = (
        Cas(
            "понедељак", 3, "Класичан балет", ("41",),
            "Теодора Мартиновски", "Ана Никчевић Торбица", "KM-4", 2,
        ),
        Cas(
            "понедељак", 4, "Класичан балет", ("41",),
            "Теодора Мартиновски", "Ана Никчевић Торбица", "KM-4", 3,
        ),
        Cas(
            "понедељак", 5, "Историјско балске игре", ("41",),
            "Теодора Мартиновски", "Мирјана Анђелковић", "KM-4", 4,
        ),
    )

    izvestaj = proveri(ulaz, (SALA,), (), casovi, jutarnja_smena=Smena.CRVENA)

    assert izvestaj.ispravan, izvestaj.tekst()
