from dataclasses import replace

from src.model import (
    Odeljenje, Predmet, Prostorija, Skola, Smena, TipProstorije, Ulaz, Zahtev,
)
from src.proveravac import Cas
from src.resavac import _jedinice, _upari_hintove, resi_obe_nedelje


SALA = Prostorija("KM-1", "Кнез Милетина 8", TipProstorije.SALA, None, "")
UCIONICA = Prostorija("KM-уч2", "Кнез Милетина 8", TipProstorije.UCIONICA, None, "")


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


def test_prethodni_raspored_se_prihvata_kao_fiksirani_hint(capsys):
    u = _ulaz_za_dve_nedelje()
    prvo_a, prvo_b = _resi(u)
    assert prvo_a.pronadjen and prvo_b.pronadjen

    drugo_a, drugo_b = _resi(u, hintovi=prvo_a.casovi, hintovi_b=prvo_b.casovi)

    assert "prethodni raspored je i dalje dopustiv" in capsys.readouterr().out
    assert drugo_a.pronadjen and drugo_b.pronadjen
    assert drugo_a.izvestaj is not None and drugo_a.izvestaj.ispravan
    assert drugo_b.izvestaj is not None and drugo_b.izvestaj.ispravan


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

    assert upareno == {jedinice[0].indeks: (2, 1), jedinice[1].indeks: (0, 1)}


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
