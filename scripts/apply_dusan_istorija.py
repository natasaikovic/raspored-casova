from pathlib import Path


def zameni_jednom(putanja: str, staro: str, novo: str) -> None:
    p = Path(putanja)
    tekst = p.read_text(encoding="utf-8")
    if staro not in tekst:
        raise SystemExit(f"Nije pronađen očekivani obrazac u {putanja}: {staro[:100]!r}")
    p.write_text(tekst.replace(staro, novo, 1), encoding="utf-8")


# 1) Ulaz: IV3+IV5 istoriju sada drži Dušan Ilijin.
zameni_jednom(
    "ulazi/ostali_casovi.csv",
    'Историја,IV,"IV3,IV5",2,,наставник историје br.2,,цео дан',
    'Историја,IV,"IV3,IV5",2,,Душан Илијин,,цео дан',
)

# 2) Rešavač: konstanta za Dušana.
zameni_jednom(
    "src/resavac.py",
    'ALEKSANDAR_BOSKOVIC = "Александар Бошковић"\n',
    'ALEKSANDAR_BOSKOVIC = "Александар Бошковић"\nDUSAN_ILIJIN = "Душан Илијин"\n',
)

# 3) Rešavač: nijedna grupa ne sme imati dva časa istorije istog dana.
marker = '\n\ndef _angazovanja_po_osobi(\n'
funkcija = r'''

def _dodaj_istoriju_jedan_cas_dnevno(
    model: cp_model.CpModel,
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
) -> None:
    """Svaki zahtev istorije ima najviše jedan čas u istom danu."""

    po_zahtevu: dict[int, list[Jedinica]] = defaultdict(list)
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        if zahtev.predmet == ISTORIJA:
            po_zahtevu[jedinica.zahtev_indeks].append(jedinica)

    for stavke in po_zahtevu.values():
        for indeks_dana in range(len(DANI)):
            prisustva = [
                _promenljive_za_nedelju(
                    promenljive[jedinica.indeks], nedelja_b
                )[1][indeks_dana]
                for jedinica in stavke
            ]
            model.add(sum(prisustva) <= 1)
'''
zameni_jednom("src/resavac.py", marker, funkcija + marker)

# 4) Rešavač: Dušan može imati ukupno najviše dva prazna bloka u nedelji.
zameni_jednom(
    "src/resavac.py",
    '        dnevne_pauze: list[cp_model.BoolVar] = []\n        for indeks_dana in range(len(DANI)):\n',
    '        dnevne_pauze: list[cp_model.BoolVar] = []\n        duzine_pauza: list[cp_model.IntVar] = []\n        for indeks_dana in range(len(DANI)):\n',
)
zameni_jednom(
    "src/resavac.py",
    '            if not izuzet_od_ogranicenja_pauza(osoba):\n                model.add(duzina_pauze <= 2)\n            dnevne_pauze.append(ima_pauzu)\n',
    '            if not izuzet_od_ogranicenja_pauza(osoba) or osoba == DUSAN_ILIJIN:\n                model.add(duzina_pauze <= 2)\n            dnevne_pauze.append(ima_pauzu)\n            duzine_pauza.append(duzina_pauze)\n',
)
zameni_jednom(
    "src/resavac.py",
    '        if not izuzet_od_ogranicenja_pauza(osoba):\n            model.add(sum(dnevne_pauze) <= 1)\n\n\ndef _dodaj_jednakost_lokacije(',
    '        if not izuzet_od_ogranicenja_pauza(osoba):\n            model.add(sum(dnevne_pauze) <= 1)\n        if osoba == DUSAN_ILIJIN:\n            model.add(sum(duzine_pauza) <= 2)\n\n\ndef _dodaj_jednakost_lokacije(',
)

# 5) Rešavač: uključi pravilo jednog časa istorije dnevno za obe nedelje.
zameni_jednom(
    "src/resavac.py",
    '    # Aleksandar Bošković: II razred, dva dana po tri uzastopna časa od 7. bloka.\n',
    '    # Istorija: nijedna grupa ne sme imati dva časa istog dana.\n'
    '    _dodaj_istoriju_jedan_cas_dnevno(model, ulaz, jedinice, promenljive)\n'
    '    if sa_nedeljom_b:\n'
    '        _dodaj_istoriju_jedan_cas_dnevno(\n'
    '            model, ulaz, jedinice, promenljive, nedelja_b=True\n'
    '        )\n\n'
    '    # Aleksandar Bošković: II razred, dva dana po tri uzastopna časa od 7. bloka.\n',
)

# 6) Proveravač: konstanta za Dušana.
zameni_jednom(
    "src/proveravac.py",
    'ALEKSANDAR_BOSKOVIC = "Александар Бошковић"\n',
    'ALEKSANDAR_BOSKOVIC = "Александар Бошковић"\nDUSAN_ILIJIN = "Душан Илијин"\n',
)

# 7) Proveravač: pozivi novih provera.
zameni_jednom(
    "src/proveravac.py",
    '    _proveri_narodno_pozoriste(ulaz, casovi, izvestaj)\n    _proveri_aleksandra_boskovica(casovi, izvestaj, ulaz)\n',
    '    _proveri_narodno_pozoriste(ulaz, casovi, izvestaj)\n'
    '    _proveri_istoriju_jedan_cas_dnevno(casovi, izvestaj)\n'
    '    _proveri_dusan_ilijin(casovi, izvestaj, ulaz)\n'
    '    _proveri_aleksandra_boskovica(casovi, izvestaj, ulaz)\n',
)

# 8) Proveravač: čvrsta pravila istorije i Dušana.
marker = '\n\ndef _proveri_aleksandra_boskovica(\n'
funkcije = r'''

def _proveri_istoriju_jedan_cas_dnevno(
    casovi: Sequence[Cas], izvestaj: Izvestaj
) -> None:
    """Nijedno odeljenje/grupa ne sme imati dva časa istorije istog dana."""

    brojaci: Counter[tuple[str, str]] = Counter()
    for cas in casovi:
        if cas.predmet != ISTORIJA:
            continue
        for oznaka in cas.odeljenja:
            brojaci[(oznaka, cas.dan)] += 1
    for (oznaka, dan), broj in sorted(brojaci.items()):
        if broj > 1:
            izvestaj.greske.append(
                f"историја за {oznaka}: у дану {dan} има {broj} часа; максимум је један"
            )


def _proveri_dusan_ilijin(
    casovi: Sequence[Cas],
    izvestaj: Izvestaj,
    ulaz: Ulaz | None = None,
) -> None:
    """Dušan radi ponedeljkom, četvrtkom i petkom, uz najviše 2 bloka pauze."""

    if ulaz is not None and not any(
        zahtev.predmet == ISTORIJA and zahtev.nastavnik == DUSAN_ILIJIN
        for zahtev in ulaz.zahtevi
    ):
        return

    stavke = [
        cas
        for cas in casovi
        if cas.predmet == ISTORIJA and cas.nastavnik == DUSAN_ILIJIN
    ]
    dozvoljeni_dani = {"понедељак", "четвртак", "петак"}
    for cas in stavke:
        if cas.dan not in dozvoljeni_dani:
            izvestaj.greske.append(
                f"{DUSAN_ILIJIN} može držati istoriju samo ponedeljkom, četvrtkom i petkom; "
                f"pronađen je čas u danu {cas.dan}"
            )

    ukupno_pauze = 0
    po_danu: dict[str, set[int]] = defaultdict(set)
    for cas in stavke:
        po_danu[cas.dan].add(cas.blok)
    for blokovi in po_danu.values():
        if not blokovi:
            continue
        ukupno_pauze += max(blokovi) - min(blokovi) + 1 - len(blokovi)
    if ukupno_pauze > 2:
        izvestaj.greske.append(
            f"{DUSAN_ILIJIN} ima ukupno {ukupno_pauze} blokova pauze u nedelji; maksimum su 2"
        )
'''
zameni_jednom("src/proveravac.py", marker, funkcije + marker)

# 9) Dokumentacija.
p = Path("docs/pravila-rasporeda.md")
tekst = p.read_text(encoding="utf-8")
dodatak = r'''

### Istorija — Dušan Ilijin

- Dušan Ilijin predaje istoriju i spojenoj grupi IV3,IV5 (ranije označeno kao „nastavnik istorije br.2“).
- U školi je isključivo ponedeljkom, četvrtkom i petkom; utorkom i sredom radi u drugoj školi.
- Nijedna grupa ne sme imati dva časa istorije u istom danu; ovo je čvrsto pravilo za istoriju.
- Dušan Ilijin sme imati ukupno najviše dva prazna bloka između svojih časova u toku cele nedelje.
'''
if "### Istorija — Dušan Ilijin" not in tekst:
    p.write_text(tekst.rstrip() + dodatak + "\n", encoding="utf-8")

# 10) Regresioni testovi.
Path("tests/test_dusan_ilijin.py").write_text(r'''from pathlib import Path

from src.loader import ucitaj_nedostupnost, ucitaj_vise
from src.proveravac import (
    Cas,
    Izvestaj,
    _proveri_dusan_ilijin,
    _proveri_istoriju_jedan_cas_dnevno,
)


def _cas(dan: str, blok: int, odeljenja: tuple[str, ...], nastavnik: str = "Душан Илијин") -> Cas:
    return Cas(
        dan=dan,
        blok=blok,
        predmet="Историја",
        odeljenja=odeljenja,
        nastavnik=nastavnik,
        korepetitor=None,
        prostorija="KM-уч2",
        red=2,
    )


def test_dusan_preuzima_iv3_iv5() -> None:
    ulaz = ucitaj_vise([
        Path("ulazi/osnovna_baletska_skola.csv"),
        Path("ulazi/srednja_baletska_skola.csv"),
        Path("ulazi/ostali_casovi.csv"),
    ])
    zahtev = next(
        z for z in ulaz.zahtevi
        if z.predmet == "Историја" and z.odeljenja == ("IV3", "IV5")
    )
    assert zahtev.nastavnik == "Душан Илијин"
    assert zahtev.fond == 2


def test_dusan_je_nedostupan_utorkom_i_sredom() -> None:
    stavke = ucitaj_nedostupnost(Path("ulazi/nedostupnost.csv"))
    nedostupni = {
        n.dan for n in stavke
        if n.nastavnik == "Душан Илијин" and n.od_bloka == 1 and n.do_bloka == 14
    }
    assert {"уторак", "среда", "субота"} <= nedostupni


def test_istorija_ne_sme_dvaput_istog_dana() -> None:
    izvestaj = Izvestaj()
    _proveri_istoriju_jedan_cas_dnevno(
        (
            _cas("понедељак", 3, ("IV3", "IV5")),
            _cas("понедељак", 5, ("IV3", "IV5")),
        ),
        izvestaj,
    )
    assert izvestaj.greske
    assert any("максимум је један" in g for g in izvestaj.greske)


def test_dusan_sme_najvise_dva_bloka_pauze() -> None:
    izvestaj = Izvestaj()
    _proveri_dusan_ilijin(
        (
            _cas("понедељак", 2, ("I1", "I2", "I3")),
            _cas("понедељак", 5, ("I4", "I5")),  # dva prazna bloka
            _cas("четвртак", 3, ("III1", "III3")),
            _cas("четвртак", 5, ("III2", "III4")),  # još jedan: ukupno 3
        ),
        izvestaj,
    )
    assert any("максимум су 2" in g for g in izvestaj.greske)


def test_dusan_ne_sme_utorkom_ni_sredom() -> None:
    izvestaj = Izvestaj()
    _proveri_dusan_ilijin((_cas("уторак", 4, ("IV3", "IV5")),), izvestaj)
    assert any("ponedeljkom, četvrtkom i petkom" in g for g in izvestaj.greske)
''', encoding="utf-8")
