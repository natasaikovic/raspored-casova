"""CP-SAT rešavač rasporeda časova.

Rešavač proizvodi isti CSV koji čita :mod:`src.proveravac`. Model bira obe
nedelje zajedno. Srednja škola i stalne smene ostaju iste, dok naizmenične
smene osnovne škole u B koriste inverz smene iz A.
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from ortools.sat.python import cp_model

from .loader import (
    UlazGreska,
    proveri_veze_pravila_prostorija,
    ucitaj_dostupnost_prostorija,
    ucitaj_nedostupnost,
    ucitaj_pravila_prostorija,
    ucitaj_prostorije,
    ucitaj_vise,
)
from .izuzeci import dozvoljen_peti_cas, izuzet_od_ogranicenja_pauza
from .model import (
    BLOKOVI,
    DANI,
    DRUGA_SMENA,
    PRVA_SMENA,
    Nedostupnost,
    Prostorija,
    Skola,
    Smena,
    TipProstorije,
    Ulaz,
    Zahtev,
)
from .pismo import kljuc_pisma, u_latinicu
from .pravila_prostorija import (
    dozvoljena_prostorija,
    kazna_prostorije,
    prostorija_dostupna,
)
from .proveravac import Cas, Izvestaj, proveri, ucitaj_resenje
from .vizualizacija import napravi_html


VERSKA = "Верска настава"
GRADJANSKO = "Грађанско васпитање"
ISTORIJA = "Историја"
ALEKSANDAR_BOSKOVIC = "Александар Бошковић"
DUSAN_ILIJIN = "Душан Илијин"
REPERTOAR_KLASICNOG = "Репертоар класичног балета"
REPERTOAR_NARODNE = "Репертоар народне игре"
PRIMENJENA_GIMNASTIKA = "Примењена гимнастика"
SG_SALE = frozenset({"SG-1", "SG-2", "SG-3"})
NP_SALA = "NP-сала"
KNEZ_MILETINA = "Кнез Милетина 8"
SPORTSKA_GIMNAZIJA = "Спортска гимназија"
NARODNO_POZORISTE = "Народно позориште"
KOREPETITOR_BR_1 = "корепетитор br.1"
NEPOZNATI_KOREPETITOR = "?"

OPSTI_PREDMETI = frozenset({
    "Српски језик и књижевност",
    "Француски језик",
    "Енглески језик",
    "Историја",
    "Рачунарство и информатика",
    "Математика",
    "Биологија",
    "Психологија",
    "Социологија",
    "Филозофија",
    "Верска настава",
    "Грађанско васпитање",
})

# Razmak između dana sprečava interval dužine dva da pređe u sledeći dan.
KORAK_DANA = 20

# Fiksirani hint iz prethodnog rasporeda rešava se za oko sekund; ovo je
# samo zaštita da neuspeo pokušaj ne pojede budžet prave pretrage.
LIMIT_FIKSIRANOG_HINTA = 60.0


@dataclass(frozen=True)
class Jedinica:
    """Jedna sesija koju solver raspoređuje, dužine jednog ili dva bloka."""

    indeks: int
    zahtev_indeks: int
    redni_broj: int
    trajanje: int
    korepeticija: tuple[int, ...]


@dataclass
class PromenljiveJedinice:
    start: cp_model.IntVar
    kraj: cp_model.IntVar
    dan: cp_model.IntVar
    blok: cp_model.IntVar
    interval: cp_model.IntervalVar
    start_b: cp_model.IntVar | None
    kraj_b: cp_model.IntVar | None
    dan_b: cp_model.IntVar | None
    blok_b: cp_model.IntVar | None
    interval_b: cp_model.IntervalVar | None
    po_danu: tuple[cp_model.BoolVar, ...]
    po_danu_b: tuple[cp_model.BoolVar, ...] | None
    prostorije: dict[str, cp_model.BoolVar]
    prostorije_b: dict[str, cp_model.BoolVar] | None
    lokacije: dict[str, cp_model.BoolVar]
    lokacije_b: dict[str, cp_model.BoolVar] | None


@dataclass(frozen=True)
class Rezultat:
    """Rezultat jedne nedelje, zajedno sa nezavisnom proverom."""

    status: str
    casovi: tuple[Cas, ...]
    izvestaj: Izvestaj | None
    cilj: float | None

    @property
    def pronadjen(self) -> bool:
        return bool(self.casovi)


def _jedinice(ulaz: Ulaz) -> tuple[Jedinica, ...]:
    rezultat: list[Jedinica] = []
    for zahtev_indeks, zahtev in enumerate(ulaz.zahtevi):
        predmet = ulaz.predmeti[zahtev.predmet]
        if zahtev.smena is Smena.POSEBNA:
            trajanja = [1] * zahtev.fond
        elif predmet.igracki:
            trajanja = [2] * (zahtev.fond // 2) + [1] * (zahtev.fond % 2)
        else:
            trajanja = [1] * zahtev.fond

        preostala_korepeticija = zahtev.fond_korepeticije
        for redni_broj, trajanje in enumerate(trajanja):
            broj = min(trajanje, preostala_korepeticija)
            korepeticija = tuple(range(broj))
            preostala_korepeticija -= broj
            rezultat.append(
                Jedinica(
                    indeks=len(rezultat),
                    zahtev_indeks=zahtev_indeks,
                    redni_broj=redni_broj,
                    trajanje=trajanje,
                    korepeticija=korepeticija,
                )
            )
    return tuple(rezultat)


def _dozvoljeni_poceci(
    zahtev: Zahtev,
    trajanje: int,
    jutarnja_smena: Smena,
    nedostupnosti: Sequence[Nedostupnost],
) -> tuple[tuple[int, int], ...]:
    if zahtev.smena in (Smena.CRVENA, Smena.PLAVA):
        if zahtev.smena is jutarnja_smena:
            blokovi = PRVA_SMENA
            if dozvoljen_peti_cas(
                zahtev.predmet, zahtev.nastavnik, zahtev.odeljenja
            ):
                blokovi = PRVA_SMENA + (5,)
        else:
            blokovi = DRUGA_SMENA
    elif zahtev.smena is Smena.STALNO_POPODNE:
        blokovi = DRUGA_SMENA
    elif zahtev.smena is Smena.CEO_DAN:
        blokovi = tuple(blok.broj for blok in BLOKOVI)
    else:
        poznati_opis = "стално од 18,30 часова понедељком средом петком"
        if zahtev.smena_opis != poznati_opis:
            return ()
        kandidati = tuple((dan, 13) for dan in (0, 2, 4) if trajanje == 1)
        return tuple(
            (dan, blok)
            for dan, blok in kandidati
            if not _nastavnik_nedostupan(
                zahtev.nastavnik, DANI[dan], range(blok, blok + trajanje),
                nedostupnosti,
            )
        )

    skup_blokova = set(blokovi)
    rezultat: list[tuple[int, int]] = []
    for dan, naziv_dana in enumerate(DANI):
        for blok in blokovi:
            zauzeti = range(blok, blok + trajanje)
            if any(b not in skup_blokova for b in zauzeti):
                continue
            if _nastavnik_nedostupan(
                zahtev.nastavnik, naziv_dana, zauzeti, nedostupnosti
            ):
                continue
            rezultat.append((dan, blok))
    return tuple(rezultat)


def _nastavnik_nedostupan(
    nastavnik: str,
    dan: str,
    blokovi: Iterable[int],
    nedostupnosti: Sequence[Nedostupnost],
) -> bool:
    blokovi = tuple(blokovi)
    return any(
        stavka.nastavnik == nastavnik
        and stavka.dan == dan
        and any(stavka.od_bloka <= blok <= stavka.do_bloka for blok in blokovi)
        for stavka in nedostupnosti
    )


def _moguce_prostorije(
    zahtev: Zahtev,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    trajanje: int = 2,
) -> tuple[Prostorija, ...]:
    predmet = ulaz.predmeti[zahtev.predmet]
    tip = TipProstorije.SALA if predmet.trazi_salu else TipProstorije.UCIONICA
    if zahtev.predmet == REPERTOAR_NARODNE:
        return tuple(
            p
            for p in prostorije
            if p.tip is TipProstorije.SALA
            and p.lokacija == SPORTSKA_GIMNAZIJA
            and p.oznaka in SG_SALE
        )
    if (
        not ulaz.pravila_prostorija
        and zahtev.predmet == REPERTOAR_KLASICNOG
        and zahtev.odeljenja[0] in {"III1", "III2", "IV1", "IV2"}
    ):
        return tuple(
            p for p in prostorije if p.tip is tip
        )
    kandidati = tuple(
        p
        for p in prostorije
        if p.tip is tip and p.oznaka != NP_SALA
    ) if zahtev.predmet != REPERTOAR_KLASICNOG else tuple(
        p for p in prostorije if p.tip is tip
    )
    if not ulaz.pravila_prostorija:
        return kandidati
    return tuple(
        p for p in kandidati
        if dozvoljena_prostorija(
            ulaz.pravila_prostorija, zahtev, p.oznaka, trajanje
        )
    )


def _kazna_sale_km8(zahtev: Zahtev, oznaka: str) -> int:
    """KM-8 čuvamo za Primenjenu gimnastiku osim kada nema drugog rešenja."""

    if oznaka == "KM-8" and zahtev.predmet != PRIMENJENA_GIMNASTIKA:
        return 100_000
    return 0


def _kazna_strukturisanih_pravila(
    ulaz: Ulaz, zahtev: Zahtev, oznaka: str, trajanje: int
) -> int:
    if ulaz.pravila_prostorija:
        return kazna_prostorije(
            ulaz.pravila_prostorija, zahtev, oznaka, trajanje
        )
    return 0


def _ogranici_dostupnost_prostorije(
    model: cp_model.CpModel,
    koristi: cp_model.BoolVar,
    start: cp_model.IntVar,
    dozvoljeni: Sequence[tuple[int, int]],
    ulaz: Ulaz,
    oznaka: str,
    trajanje: int,
) -> None:
    for dan, blok in dozvoljeni:
        if not prostorija_dostupna(
            ulaz.dostupnost_prostorija,
            oznaka,
            DANI[dan],
            range(blok, blok + trajanje),
        ):
            model.add(start != dan * KORAK_DANA + blok).only_enforce_if(koristi)


def _ogranici_dostupnost_lokacije(
    model: cp_model.CpModel,
    koristi: cp_model.BoolVar,
    start: cp_model.IntVar,
    dozvoljeni: Sequence[tuple[int, int]],
    ulaz: Ulaz,
    oznake: Iterable[str],
    trajanje: int,
) -> None:
    oznake = tuple(oznake)
    for dan, blok in dozvoljeni:
        if not any(
            prostorija_dostupna(
                ulaz.dostupnost_prostorija,
                oznaka,
                DANI[dan],
                range(blok, blok + trajanje),
            )
            for oznaka in oznake
        ):
            model.add(start != dan * KORAK_DANA + blok).only_enforce_if(koristi)


def _subota_dozvoljena(zahtev: Zahtev, ulaz: Ulaz) -> bool:
    """Subotom nastavu imaju samo igracki predmeti SBŠ odseka KB i SI."""

    predmet = ulaz.predmeti[zahtev.predmet]
    odeljenja = [ulaz.odeljenja[o] for o in zahtev.odeljenja]
    return (
        bool(odeljenja)
        and all(o.skola is Skola.SREDNJA for o in odeljenja)
        and predmet.igracki
        and all(o.oznaka.rstrip("АБ")[-1] in "1234" for o in odeljenja)
    )


def _dodaj_subotnje_ogranicenje(
    model: cp_model.CpModel,
    kazne: list[cp_model.LinearExprT],
    blok: cp_model.IntVar,
    prisutan_subotom: cp_model.BoolVar,
    trajanje: int,
    token: str,
) -> None:
    """Subotom zabrani rad posle 15:05 i snažno favorizuj kraj do 13:15."""

    kraj_bloka = blok + trajanje - 1
    model.add(kraj_bloka <= 8).only_enforce_if(prisutan_subotom)
    kasno = model.new_bool_var(f"{token}_subota_posle_1315")
    model.add(kasno <= prisutan_subotom)
    model.add(kraj_bloka >= 7).only_enforce_if(kasno)
    model.add(kraj_bloka <= 6).only_enforce_if([prisutan_subotom, ~kasno])
    kazne.append(2000 * kasno)


def _dodaj_subotnji_prioritet_sg(
    model: cp_model.CpModel,
    kazne: list[cp_model.LinearExprT],
    prisutan_subotom: cp_model.BoolVar,
    lokacije: dict[str, cp_model.BoolVar],
    token: str,
) -> None:
    """Subotom snažno favorizuj raspoložive sale Sportske gimnazije."""

    for broj, (lokacija, koristi) in enumerate(sorted(lokacije.items())):
        if lokacija == "Спортска гимназија":
            continue
        subotom_van_sg = model.new_bool_var(f"{token}_subota_van_sg_{broj}")
        model.add_bool_and([prisutan_subotom, koristi]).only_enforce_if(
            subotom_van_sg
        )
        model.add_bool_or([~prisutan_subotom, ~koristi]).only_enforce_if(
            ~subotom_van_sg
        )
        kazne.append(500 * subotom_van_sg)


def _resurs_korepetitora(ime: str) -> str:
    if ime in (KOREPETITOR_BR_1, NEPOZNATI_KOREPETITOR):
        return "будући корепетитор"
    return ime


def _tokeni_odeljenja(ulaz: Ulaz, oznake: Iterable[str]) -> frozenset[str]:
    polugrupe: dict[str, list[str]] = defaultdict(list)
    for odeljenje in ulaz.odeljenja.values():
        if odeljenje.roditelj:
            polugrupe[odeljenje.roditelj].append(odeljenje.oznaka)
    rezultat: set[str] = set()
    for oznaka in oznake:
        rezultat.update(polugrupe.get(oznaka, [oznaka]))
    return frozenset(rezultat)


def _promenljive_za_nedelju(
    promenljive: PromenljiveJedinice,
    nedelja_b: bool,
) -> tuple[
    cp_model.IntVar,
    tuple[cp_model.BoolVar, ...],
    dict[str, cp_model.BoolVar],
]:
    if not nedelja_b:
        return promenljive.blok, promenljive.po_danu, promenljive.lokacije
    assert promenljive.blok_b is not None
    assert promenljive.po_danu_b is not None
    assert promenljive.lokacije_b is not None
    return (
        promenljive.blok_b,
        promenljive.po_danu_b,
        promenljive.lokacije_b,
    )


def _dodaj_dnevno_pravilo_lokacije(
    model: cp_model.CpModel,
    kazne: list[cp_model.LinearExprT],
    token: str,
    indeks_dana: int,
    stavke: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
) -> None:
    """Zabrani praznine kompaktnim dnevnim obrascem.

    Dan je jedan neprekinut raspon nastavnih blokova. Jedini izuzetak je
    prazan blok 9 neposredno pre nastave u Narodnom pozoristu u bloku 10.
    Umesto posebnog intervala za svaku mogucu lokaciju biramo samo lokaciju
    pre i posle eventualnog putnog bloka.
    """

    sufiks = "_b" if nedelja_b else ""
    prisutnosti: list[cp_model.BoolVar] = []
    for jedinica in stavke:
        _, po_danu, _ = _promenljive_za_nedelju(
            promenljive[jedinica.indeks], nedelja_b
        )
        prisutnosti.append(po_danu[indeks_dana])

    ima_cas = model.new_bool_var(f"{token}_d{indeks_dana}_ima{sufiks}")
    model.add_max_equality(ima_cas, prisutnosti)
    zauzeto = sum(
        jedinica.trajanje
        * _promenljive_za_nedelju(
            promenljive[jedinica.indeks], nedelja_b
        )[1][indeks_dana]
        for jedinica in stavke
    )

    sve_lokacije = sorted(
        {
            lokacija
            for jedinica in stavke
            for lokacija in _promenljive_za_nedelju(
                promenljive[jedinica.indeks], nedelja_b
            )[2]
        }
    )
    if not sve_lokacije:
        raise ValueError(f"{token}: нема могуће локације")
    indeks_lokacije = {naziv: indeks for indeks, naziv in enumerate(sve_lokacije)}
    lokacija_pre = model.new_int_var(
        0, len(sve_lokacije) - 1,
        f"{token}_d{indeks_dana}_lokacija_pre{sufiks}",
    )
    lokacija_posle = model.new_int_var(
        0, len(sve_lokacije) - 1,
        f"{token}_d{indeks_dana}_lokacija_posle{sufiks}",
    )
    menja_lokaciju = model.new_bool_var(
        f"{token}_d{indeks_dana}_promena_lokacije{sufiks}"
    )
    ima_putni_blok = model.new_bool_var(
        f"{token}_d{indeks_dana}_putni_blok_postoji{sufiks}"
    )
    model.add(menja_lokaciju <= ima_cas)
    dozvoljeni_prelazi = []
    for pre_naziv, pre_indeks in indeks_lokacije.items():
        for posle_naziv, posle_indeks in indeks_lokacije.items():
            menja = int(pre_indeks != posle_indeks)
            neposredan = {pre_naziv, posle_naziv} == {
                KNEZ_MILETINA, SPORTSKA_GIMNAZIJA
            }
            put_ka_np = (
                posle_naziv == NARODNO_POZORISTE
                and pre_naziv in {KNEZ_MILETINA, SPORTSKA_GIMNAZIJA}
            )
            if not menja:
                dozvoljeni_prelazi.append((pre_indeks, posle_indeks, 0, 0))
            elif neposredan:
                dozvoljeni_prelazi.append((pre_indeks, posle_indeks, 1, 0))
            elif put_ka_np:
                dozvoljeni_prelazi.append((pre_indeks, posle_indeks, 1, 1))
    model.add_allowed_assignments(
        [lokacija_pre, lokacija_posle, menja_lokaciju, ima_putni_blok],
        dozvoljeni_prelazi,
    )

    prvi = model.new_int_var(
        1, len(BLOKOVI) + 1, f"{token}_d{indeks_dana}_prvi{sufiks}"
    )
    kraj = model.new_int_var(
        0, len(BLOKOVI) + 1, f"{token}_d{indeks_dana}_kraj{sufiks}"
    )
    prvi_kandidati: list[cp_model.IntVar] = []
    poslednji_kandidati: list[cp_model.IntVar] = []
    posle_puta: list[cp_model.BoolVar] = []
    granica_prelaza = model.new_int_var(
        1, len(BLOKOVI), f"{token}_d{indeks_dana}_granica_prelaza{sufiks}"
    )
    model.add(granica_prelaza == 1).only_enforce_if(~menja_lokaciju)
    model.add(granica_prelaza == 9).only_enforce_if(ima_putni_blok)

    for jedinica in stavke:
        blok, po_danu, lokacije = _promenljive_za_nedelju(
            promenljive[jedinica.indeks], nedelja_b
        )
        prisutan = po_danu[indeks_dana]
        kandidat_prvog = model.new_int_var(
            1, len(BLOKOVI) + 1,
            f"{token}_d{indeks_dana}_j{jedinica.indeks}_prvi{sufiks}",
        )
        model.add(kandidat_prvog == blok).only_enforce_if(prisutan)
        model.add(kandidat_prvog == len(BLOKOVI) + 1).only_enforce_if(~prisutan)
        prvi_kandidati.append(kandidat_prvog)

        kandidat_kraja = model.new_int_var(
            0, len(BLOKOVI) + 1,
            f"{token}_d{indeks_dana}_j{jedinica.indeks}_kraj{sufiks}",
        )
        model.add(kandidat_kraja == blok + jedinica.trajanje).only_enforce_if(
            prisutan
        )
        model.add(kandidat_kraja == 0).only_enforce_if(~prisutan)
        poslednji_kandidati.append(kandidat_kraja)

        posle = model.new_bool_var(
            f"{token}_d{indeks_dana}_j{jedinica.indeks}_posle_puta{sufiks}"
        )
        model.add(posle <= prisutan)
        model.add(posle <= menja_lokaciju)
        model.add(blok >= granica_prelaza + ima_putni_blok).only_enforce_if(posle)
        model.add(blok + jedinica.trajanje <= granica_prelaza).only_enforce_if(
            [prisutan, ~posle, menja_lokaciju]
        )
        posle_puta.append(posle)

        lokacija_jedinice = sum(
            indeks_lokacije[lokacija] * koristi
            for lokacija, koristi in lokacije.items()
        )
        model.add(lokacija_jedinice == lokacija_posle).only_enforce_if(posle)
        model.add(lokacija_jedinice == lokacija_pre).only_enforce_if(
            [prisutan, ~posle]
        )

    model.add_min_equality(prvi, prvi_kandidati)
    model.add_max_equality(kraj, poslednji_kandidati)
    model.add(sum(posle_puta) >= menja_lokaciju)
    model.add(sum(prisutnosti) - sum(posle_puta) >= menja_lokaciju)
    # Ukupan dnevni raspon sadrži samo nastavne blokove. Jedini dozvoljeni
    # slobodan blok je blok 9, neposredno pre nastave u Narodnom pozorištu.
    model.add(
        kraj - prvi == zauzeto + ima_putni_blok
    ).only_enforce_if(ima_cas)
    kazne.append(300 * menja_lokaciju)


def _dodaj_pravilo_aleksandra_boskovica(
    model: cp_model.CpModel,
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
) -> None:
    """Rasporedi Aleksandrovih šest časova u dva kompaktna dana po tri."""

    stavke = [
        jedinica
        for jedinica in jedinice
        if ulaz.zahtevi[jedinica.zahtev_indeks].predmet == ISTORIJA
        and ulaz.zahtevi[jedinica.zahtev_indeks].nastavnik == ALEKSANDAR_BOSKOVIC
    ]
    if not stavke:
        return
    if len(stavke) != 6:
        raise ValueError(
            f"{ALEKSANDAR_BOSKOVIC}: očekuje se tačno 6 časova istorije"
        )

    po_zahtevu: dict[int, list[Jedinica]] = defaultdict(list)
    for jedinica in stavke:
        po_zahtevu[jedinica.zahtev_indeks].append(jedinica)
    if len(po_zahtevu) != 3 or any(len(grupa) != 2 for grupa in po_zahtevu.values()):
        raise ValueError(
            f"{ALEKSANDAR_BOSKOVIC}: očekuju se tri grupe sa po 2 časa"
        )

    aktivni_dani: list[cp_model.BoolVar] = []
    sufiks = "_b" if nedelja_b else ""
    for indeks_dana in range(5):
        aktivan = model.new_bool_var(f"aleksandar_d{indeks_dana}{sufiks}")
        aktivni_dani.append(aktivan)
        sva_prisustva = []
        for grupa in po_zahtevu.values():
            prisustva_grupe = []
            for jedinica in grupa:
                _, po_danu, _ = _promenljive_za_nedelju(
                    promenljive[jedinica.indeks], nedelja_b
                )
                prisustva_grupe.append(po_danu[indeks_dana])
                sva_prisustva.append(po_danu[indeks_dana])
            model.add(sum(prisustva_grupe) == aktivan)
        model.add(sum(sva_prisustva) == 3 * aktivan)

        prvi_kandidati = []
        poslednji_kandidati = []
        for jedinica in stavke:
            blok, po_danu, _ = _promenljive_za_nedelju(
                promenljive[jedinica.indeks], nedelja_b
            )
            prisutan = po_danu[indeks_dana]
            prvi = model.new_int_var(
                1, len(BLOKOVI) + 1,
                f"aleksandar_j{jedinica.indeks}_d{indeks_dana}_prvi{sufiks}",
            )
            poslednji = model.new_int_var(
                0, len(BLOKOVI),
                f"aleksandar_j{jedinica.indeks}_d{indeks_dana}_poslednji{sufiks}",
            )
            model.add(prvi == blok).only_enforce_if(prisutan)
            model.add(prvi == len(BLOKOVI) + 1).only_enforce_if(~prisutan)
            model.add(poslednji == blok).only_enforce_if(prisutan)
            model.add(poslednji == 0).only_enforce_if(~prisutan)
            prvi_kandidati.append(prvi)
            poslednji_kandidati.append(poslednji)
        prvi_blok = model.new_int_var(
            1, len(BLOKOVI) + 1, f"aleksandar_d{indeks_dana}_min{sufiks}"
        )
        poslednji_blok = model.new_int_var(
            0, len(BLOKOVI), f"aleksandar_d{indeks_dana}_max{sufiks}"
        )
        model.add_min_equality(prvi_blok, prvi_kandidati)
        model.add_max_equality(poslednji_blok, poslednji_kandidati)
        model.add(poslednji_blok - prvi_blok == 2).only_enforce_if(aktivan)

    model.add(sum(aktivni_dani) == 2)
    for jedinica in stavke:
        blok, po_danu, _ = _promenljive_za_nedelju(
            promenljive[jedinica.indeks], nedelja_b
        )
        model.add(blok >= 7)
        model.add(po_danu[5] == 0)


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


def _angazovanja_po_osobi(
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
) -> dict[str, list[tuple[Jedinica, tuple[int, ...]]]]:
    angazovanja: dict[str, dict[int, set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    po_indeksu = {jedinica.indeks: jedinica for jedinica in jedinice}
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        angazovanja[_resurs_korepetitora(zahtev.nastavnik)][jedinica.indeks].update(
            range(jedinica.trajanje)
        )
        if zahtev.korepetitor and jedinica.korepeticija:
            angazovanja[_resurs_korepetitora(zahtev.korepetitor)][
                jedinica.indeks
            ].update(jedinica.korepeticija)
    return {
        osoba: [
            (po_indeksu[indeks], tuple(sorted(pomeraji)))
            for indeks, pomeraji in sorted(stavke.items())
        ]
        for osoba, stavke in angazovanja.items()
    }


def _dodaj_kontinuitet_osoba(
    model: cp_model.CpModel,
    kazne: list[cp_model.LinearExprT],
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
) -> None:
    """Ograniči pauze osoba i dodatno ih smanji kroz funkciju cilja."""

    sufiks = "_b" if nedelja_b else ""
    for broj_osobe, (osoba, stavke) in enumerate(
        sorted(_angazovanja_po_osobi(ulaz, jedinice).items())
    ):
        dnevne_pauze: list[cp_model.BoolVar] = []
        duzine_pauza: list[cp_model.IntVar] = []
        for indeks_dana in range(len(DANI)):
            prisutnosti = [
                _promenljive_za_nedelju(
                    promenljive[jedinica.indeks], nedelja_b
                )[1][indeks_dana]
                for jedinica, _ in stavke
            ]
            ima_cas = model.new_bool_var(
                f"o{broj_osobe}_d{indeks_dana}_ima{sufiks}"
            )
            model.add_max_equality(ima_cas, prisutnosti)
            prvi = model.new_int_var(
                1, len(BLOKOVI), f"o{broj_osobe}_d{indeks_dana}_prvi{sufiks}"
            )
            poslednji = model.new_int_var(
                0, len(BLOKOVI), f"o{broj_osobe}_d{indeks_dana}_poslednji{sufiks}"
            )
            model.add(prvi == 1).only_enforce_if(~ima_cas)
            model.add(poslednji == 0).only_enforce_if(~ima_cas)
            for jedinica, pomeraji in stavke:
                blok, po_danu, _ = _promenljive_za_nedelju(
                    promenljive[jedinica.indeks], nedelja_b
                )
                prisutan = po_danu[indeks_dana]
                model.add(prvi <= blok + min(pomeraji)).only_enforce_if(prisutan)
                model.add(poslednji >= blok + max(pomeraji)).only_enforce_if(prisutan)
            zauzeto = sum(
                len(pomeraji)
                * _promenljive_za_nedelju(
                    promenljive[jedinica.indeks], nedelja_b
                )[1][indeks_dana]
                for jedinica, pomeraji in stavke
            )
            model.add(zauzeto <= 6)
            preko_optimuma = model.new_int_var(
                0, 2, f"o{broj_osobe}_d{indeks_dana}_preko_4{sufiks}"
            )
            model.add_max_equality(preko_optimuma, [0, zauzeto - 4])
            kazne.append(250 * preko_optimuma)

            ima_pauzu = model.new_bool_var(
                f"o{broj_osobe}_d{indeks_dana}_pauza{sufiks}"
            )
            duzina_pauze = model.new_int_var(
                0,
                len(BLOKOVI),
                f"o{broj_osobe}_d{indeks_dana}_duzina_pauze{sufiks}",
            )
            model.add(duzina_pauze == 0).only_enforce_if(~ima_pauzu)
            model.add(duzina_pauze >= 1).only_enforce_if(ima_pauzu)
            model.add(duzina_pauze == poslednji - prvi + 1 - zauzeto)
            if not izuzet_od_ogranicenja_pauza(osoba) or osoba == DUSAN_ILIJIN:
                model.add(duzina_pauze <= 2)
            dnevne_pauze.append(ima_pauzu)
            duzine_pauza.append(duzina_pauze)
            kazne.append(500 * ima_pauzu)
            kazne.append(100 * duzina_pauze)
        if not izuzet_od_ogranicenja_pauza(osoba):
            model.add(sum(dnevne_pauze) <= 1)
        if osoba == DUSAN_ILIJIN:
            model.add(sum(duzine_pauza) <= 2)


def _dodaj_jednakost_lokacije(
    model: cp_model.CpModel,
    prva: PromenljiveJedinice,
    druga: PromenljiveJedinice,
) -> None:
    for lokacija in sorted(set(prva.lokacije) | set(druga.lokacije)):
        a = prva.lokacije.get(lokacija)
        b = druga.lokacije.get(lokacija)
        if a is None:
            model.add(b == 0)
        elif b is None:
            model.add(a == 0)
        else:
            model.add(a == b)


def napravi_model(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    jutarnja_smena: Smena,
    hintovi: Sequence[Cas] = (),
    sa_nedeljom_b: bool = False,
    samo_lokacije: bool = False,
    sa_ciljem: bool = True,
    hintovi_b: Sequence[Cas] = (),
) -> tuple[
    cp_model.CpModel,
    tuple[Jedinica, ...],
    dict[int, PromenljiveJedinice],
]:
    """Napravi model za A; opciono uključi povezanu nedelju B."""

    if jutarnja_smena not in (Smena.CRVENA, Smena.PLAVA):
        raise ValueError("Јутарња смена мора бити црвена или плава")

    model = cp_model.CpModel()
    kazne: list[cp_model.LinearExprT] = []
    jedinice = _jedinice(ulaz)
    promenljive: dict[int, PromenljiveJedinice] = {}
    intervali_nastavnika: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_korepetitora: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_prostorija: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_nastavnika_b: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_korepetitora_b: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_prostorija_b: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_kapaciteta: dict[
        tuple[str, TipProstorije], list[cp_model.IntervalVar]
    ] = defaultdict(list)
    intervali_kapaciteta_b: dict[
        tuple[str, TipProstorije], list[cp_model.IntervalVar]
    ] = defaultdict(list)
    intervali_skupova_kandidata: dict[
        tuple[str, TipProstorije, frozenset[str]], list[cp_model.IntervalVar]
    ] = defaultdict(list)
    intervali_skupova_kandidata_b: dict[
        tuple[str, TipProstorije, frozenset[str]], list[cp_model.IntervalVar]
    ] = defaultdict(list)
    jedinice_zahteva: dict[int, list[Jedinica]] = defaultdict(list)
    np_izbori: dict[str, list[cp_model.BoolVar]] = defaultdict(list)
    ima_np_program = all(
        any(
            z.predmet == REPERTOAR_KLASICNOG and oznaka in z.odeljenja
            for z in ulaz.zahtevi
        )
        for oznaka in ("IV1", "IV2")
    )

    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        dozvoljeni = _dozvoljeni_poceci(
            zahtev,
            jedinica.trajanje,
            jutarnja_smena,
            nedostupnosti,
        )
        if zahtev.korepetitor and jedinica.korepeticija:
            dozvoljeni = tuple(
                (dan_i, blok_i)
                for dan_i, blok_i in dozvoljeni
                if not _nastavnik_nedostupan(
                    zahtev.korepetitor, DANI[dan_i],
                    tuple(blok_i + p for p in jedinica.korepeticija),
                    nedostupnosti,
                )
            )
        if not dozvoljeni:
            raise ValueError(
                f"{zahtev.gde}: нема дозвољеног почетка за „{zahtev.predmet}“"
            )
        vrednosti_starta = [dan * KORAK_DANA + blok for dan, blok in dozvoljeni]
        prefiks = f"j{jedinica.indeks}"
        start = model.new_int_var_from_domain(
            cp_model.Domain.from_values(vrednosti_starta), f"{prefiks}_start"
        )
        kraj = model.new_int_var(1, (len(DANI) - 1) * KORAK_DANA + 15, f"{prefiks}_kraj")
        model.add(kraj == start + jedinica.trajanje)
        dan = model.new_int_var(0, len(DANI) - 1, f"{prefiks}_dan")
        blok = model.new_int_var(1, len(BLOKOVI), f"{prefiks}_blok")
        model.add(start == dan * KORAK_DANA + blok)
        interval = model.new_interval_var(start, jedinica.trajanje, kraj, f"{prefiks}_i")

        start_b: cp_model.IntVar | None = None
        kraj_b: cp_model.IntVar | None = None
        dan_b: cp_model.IntVar | None = None
        blok_b: cp_model.IntVar | None = None
        interval_b: cp_model.IntervalVar | None = None
        dozvoljeni_b = dozvoljeni
        if sa_nedeljom_b:
            if zahtev.smena.menja_se:
                jutarnja_b = (
                    Smena.PLAVA if jutarnja_smena is Smena.CRVENA else Smena.CRVENA
                )
                dozvoljeni_b = _dozvoljeni_poceci(
                    zahtev,
                    jedinica.trajanje,
                    jutarnja_b,
                    nedostupnosti,
                )
                if zahtev.korepetitor and jedinica.korepeticija:
                    dozvoljeni_b = tuple(
                        (dan_i, blok_i)
                        for dan_i, blok_i in dozvoljeni_b
                        if not _nastavnik_nedostupan(
                            zahtev.korepetitor, DANI[dan_i],
                            tuple(blok_i + p for p in jedinica.korepeticija),
                            nedostupnosti,
                        )
                    )
                if not dozvoljeni_b:
                    raise ValueError(
                        f"{zahtev.gde}: нема дозвољеног почетка у недељи B "
                        f"за „{zahtev.predmet}“"
                    )
                vrednosti_starta_b = [
                    dan_i * KORAK_DANA + blok_i
                    for dan_i, blok_i in dozvoljeni_b
                ]
                start_b = model.new_int_var_from_domain(
                    cp_model.Domain.from_values(vrednosti_starta_b),
                    f"{prefiks}_start_b",
                )
                kraj_b = model.new_int_var(
                    1, (len(DANI) - 1) * KORAK_DANA + 15,
                    f"{prefiks}_kraj_b",
                )
                model.add(kraj_b == start_b + jedinica.trajanje)
                dan_b = model.new_int_var(0, len(DANI) - 1, f"{prefiks}_dan_b")
                blok_b = model.new_int_var(1, len(BLOKOVI), f"{prefiks}_blok_b")
                model.add(start_b == dan_b * KORAK_DANA + blok_b)
                interval_b = model.new_interval_var(
                    start_b, jedinica.trajanje, kraj_b, f"{prefiks}_i_b"
                )
            else:
                start_b, kraj_b = start, kraj
                dan_b, blok_b = dan, blok
                interval_b = interval

        po_danu: list[cp_model.BoolVar] = []
        for indeks_dana in range(len(DANI)):
            prisutan = model.new_bool_var(f"{prefiks}_d{indeks_dana}")
            model.add(dan == indeks_dana).only_enforce_if(prisutan)
            model.add(dan != indeks_dana).only_enforce_if(~prisutan)
            po_danu.append(prisutan)
        model.add_exactly_one(po_danu)
        dozvoljena_subota = _subota_dozvoljena(zahtev, ulaz)
        if not dozvoljena_subota:
            model.add(po_danu[len(DANI) - 1] == 0)
        else:
            _dodaj_subotnje_ogranicenje(
                model,
                kazne,
                blok,
                po_danu[len(DANI) - 1],
                jedinica.trajanje,
                prefiks,
            )
        po_danu_b: tuple[cp_model.BoolVar, ...] | None = None
        if sa_nedeljom_b:
            if zahtev.smena.menja_se:
                assert dan_b is not None
                b_dani: list[cp_model.BoolVar] = []
                for indeks_dana in range(len(DANI)):
                    prisutan_b = model.new_bool_var(f"{prefiks}_d{indeks_dana}_b")
                    model.add(dan_b == indeks_dana).only_enforce_if(prisutan_b)
                    model.add(dan_b != indeks_dana).only_enforce_if(~prisutan_b)
                    b_dani.append(prisutan_b)
                model.add_exactly_one(b_dani)
                po_danu_b = tuple(b_dani)
                if not dozvoljena_subota:
                    model.add(b_dani[len(DANI) - 1] == 0)
            else:
                po_danu_b = tuple(po_danu)

        moguce = _moguce_prostorije(
            zahtev, ulaz, prostorije, jedinica.trajanje
        )
        if not moguce:
            raise ValueError(f"{zahtev.gde}: нема одговарајуће просторије")
        izbor_prostorije: dict[str, cp_model.BoolVar] = {}
        izbor_prostorije_b: dict[str, cp_model.BoolVar] | None = (
            {} if sa_nedeljom_b else None
        )
        po_lokaciji: dict[str, list[cp_model.BoolVar]] = defaultdict(list)
        po_lokaciji_b: dict[str, list[cp_model.BoolVar]] = defaultdict(list)
        if samo_lokacije:
            predmet = ulaz.predmeti[zahtev.predmet]
            tip = (
                TipProstorije.SALA
                if predmet.trazi_salu
                else TipProstorije.UCIONICA
            )
            lokacije_mogucih = sorted({p.lokacija for p in moguce})
            lokacije = {}
            lokacije_b: dict[str, cp_model.BoolVar] | None = (
                {} if sa_nedeljom_b else None
            )
            for broj_lokacije, lokacija in enumerate(lokacije_mogucih):
                kandidati_na_lokaciji = frozenset(
                    p.oznaka for p in moguce if p.lokacija == lokacija
                )
                kljuc_kandidata = (lokacija, tip, kandidati_na_lokaciji)
                koristi = model.new_bool_var(
                    f"{prefiks}_lok_{broj_lokacije}"
                )
                lokacije[lokacija] = koristi
                interval_lokacije = model.new_optional_interval_var(
                    start,
                    jedinica.trajanje,
                    kraj,
                    koristi,
                    f"{prefiks}_lok_{broj_lokacije}_i",
                )
                intervali_kapaciteta[(lokacija, tip)].append(interval_lokacije)
                intervali_skupova_kandidata[kljuc_kandidata].append(
                    interval_lokacije
                )
                _ogranici_dostupnost_lokacije(
                    model, koristi, start, dozvoljeni, ulaz,
                    kandidati_na_lokaciji, jedinica.trajanje,
                )
                if kandidati_na_lokaciji == frozenset({"KM-8"}):
                    intervali_prostorija["KM-8"].append(interval_lokacije)
                elif (
                    "KM-8" in kandidati_na_lokaciji
                    and (kazna_km8 := _kazna_sale_km8(zahtev, "KM-8"))
                ):
                    koristi_km8 = model.new_bool_var(
                        f"{prefiks}_lok_{broj_lokacije}_km8"
                    )
                    koristi_obicnu = model.new_bool_var(
                        f"{prefiks}_lok_{broj_lokacije}_obicna"
                    )
                    model.add(koristi_km8 + koristi_obicnu == koristi)
                    intervali_prostorija["KM-8"].append(
                        model.new_optional_interval_var(
                            start,
                            jedinica.trajanje,
                            kraj,
                            koristi_km8,
                            f"{prefiks}_lok_{broj_lokacije}_km8_i",
                        )
                    )
                    obicne = kandidati_na_lokaciji - {"KM-8"}
                    intervali_skupova_kandidata[(lokacija, tip, obicne)].append(
                        model.new_optional_interval_var(
                            start,
                            jedinica.trajanje,
                            kraj,
                            koristi_obicnu,
                            f"{prefiks}_lok_{broj_lokacije}_obicna_i",
                        )
                    )
                    kazne.append(kazna_km8 * koristi_km8)
                if lokacija == "Народно позориште":
                    np_izbori[zahtev.odeljenja[0]].append(koristi)
                    if jedinica.trajanje != 2:
                        model.add(koristi == 0)
                    else:
                        model.add(blok == 10).only_enforce_if(koristi)
                if sa_nedeljom_b:
                    assert start_b is not None and kraj_b is not None
                    assert lokacije_b is not None
                    if zahtev.smena.menja_se:
                        koristi_b = model.new_bool_var(
                            f"{prefiks}_lok_{broj_lokacije}_b"
                        )
                        interval_b_lokacije = model.new_optional_interval_var(
                            start_b,
                            jedinica.trajanje,
                            kraj_b,
                            koristi_b,
                            f"{prefiks}_lok_{broj_lokacije}_i_b",
                        )
                    else:
                        koristi_b = koristi
                        interval_b_lokacije = interval_lokacije
                    lokacije_b[lokacija] = koristi_b
                    intervali_kapaciteta_b[(lokacija, tip)].append(
                        interval_b_lokacije
                    )
                    intervali_skupova_kandidata_b[kljuc_kandidata].append(
                        interval_b_lokacije
                    )
                    _ogranici_dostupnost_lokacije(
                        model, koristi_b, start_b, dozvoljeni_b, ulaz,
                        kandidati_na_lokaciji, jedinica.trajanje,
                    )
                    if kandidati_na_lokaciji == frozenset({"KM-8"}):
                        intervali_prostorija_b["KM-8"].append(
                            interval_b_lokacije
                        )
                    elif (
                        "KM-8" in kandidati_na_lokaciji
                        and (kazna_km8 := _kazna_sale_km8(zahtev, "KM-8"))
                    ):
                        if zahtev.smena.menja_se:
                            koristi_km8_b = model.new_bool_var(
                                f"{prefiks}_lok_{broj_lokacije}_km8_b"
                            )
                            koristi_obicnu_b = model.new_bool_var(
                                f"{prefiks}_lok_{broj_lokacije}_obicna_b"
                            )
                            model.add(
                                koristi_km8_b + koristi_obicnu_b == koristi_b
                            )
                        else:
                            koristi_km8_b = koristi_km8
                            koristi_obicnu_b = koristi_obicnu
                        intervali_prostorija_b["KM-8"].append(
                            model.new_optional_interval_var(
                                start_b,
                                jedinica.trajanje,
                                kraj_b,
                                koristi_km8_b,
                                f"{prefiks}_lok_{broj_lokacije}_km8_i_b",
                            )
                        )
                        obicne = kandidati_na_lokaciji - {"KM-8"}
                        intervali_skupova_kandidata_b[
                            (lokacija, tip, obicne)
                        ].append(
                            model.new_optional_interval_var(
                                start_b,
                                jedinica.trajanje,
                                kraj_b,
                                koristi_obicnu_b,
                                f"{prefiks}_lok_{broj_lokacije}_obicna_i_b",
                            )
                        )
                        if zahtev.smena.menja_se:
                            kazne.append(kazna_km8 * koristi_km8_b)
            model.add_exactly_one(lokacije.values())
            if sa_nedeljom_b and zahtev.smena.menja_se:
                assert lokacije_b is not None
                model.add_exactly_one(lokacije_b.values())
        else:
            lokacije = {}
            lokacije_b = None
        for prostorija in (() if samo_lokacije else moguce):
            koristi = model.new_bool_var(f"{prefiks}_{prostorija.oznaka}")
            izbor_prostorije[prostorija.oznaka] = koristi
            po_lokaciji[prostorija.lokacija].append(koristi)
            kazna_pravila = _kazna_strukturisanih_pravila(
                ulaz, zahtev, prostorija.oznaka, jedinica.trajanje
            )
            if kazna_pravila:
                kazne.append(kazna_pravila * koristi)
            kazna_km8 = _kazna_sale_km8(zahtev, prostorija.oznaka)
            if kazna_km8:
                kazne.append(kazna_km8 * koristi)
            if prostorija.oznaka == NP_SALA:
                np_izbori[zahtev.odeljenja[0]].append(koristi)
                if jedinica.trajanje != 2:
                    model.add(koristi == 0)
                else:
                    model.add(blok == 10).only_enforce_if(koristi)
            _ogranici_dostupnost_prostorije(
                model, koristi, start, dozvoljeni, ulaz,
                prostorija.oznaka, jedinica.trajanje,
            )
            opcion = model.new_optional_interval_var(
                start, jedinica.trajanje, kraj, koristi,
                f"{prefiks}_{prostorija.oznaka}_i",
            )
            intervali_prostorija[prostorija.oznaka].append(opcion)
            if sa_nedeljom_b:
                assert start_b is not None and kraj_b is not None
                assert izbor_prostorije_b is not None
                if zahtev.smena.menja_se:
                    koristi_b = model.new_bool_var(
                        f"{prefiks}_{prostorija.oznaka}_b"
                    )
                    opcion_b = model.new_optional_interval_var(
                        start_b, jedinica.trajanje, kraj_b, koristi_b,
                        f"{prefiks}_{prostorija.oznaka}_i_b",
                    )
                else:
                    koristi_b = koristi
                    opcion_b = opcion
                izbor_prostorije_b[prostorija.oznaka] = koristi_b
                po_lokaciji_b[prostorija.lokacija].append(koristi_b)
                intervali_prostorija_b[prostorija.oznaka].append(opcion_b)
                _ogranici_dostupnost_prostorije(
                    model, koristi_b, start_b, dozvoljeni_b, ulaz,
                    prostorija.oznaka, jedinica.trajanje,
                )
                if zahtev.smena.menja_se and kazna_pravila:
                    kazne.append(kazna_pravila * koristi_b)
                if zahtev.smena.menja_se and kazna_km8:
                    kazne.append(kazna_km8 * koristi_b)
        if not samo_lokacije:
            model.add_exactly_one(izbor_prostorije.values())
        if not samo_lokacije and sa_nedeljom_b and zahtev.smena.menja_se:
            assert izbor_prostorije_b is not None
            model.add_exactly_one(izbor_prostorije_b.values())
        if not samo_lokacije:
            lokacije = {}
            for lokacija, izbori in po_lokaciji.items():
                koristi_lokaciju = model.new_bool_var(f"{prefiks}_lok_{len(lokacije)}")
                model.add(koristi_lokaciju == sum(izbori))
                lokacije[lokacija] = koristi_lokaciju
            lokacije_b = None
        if not samo_lokacije and sa_nedeljom_b:
            if zahtev.smena.menja_se:
                lokacije_b = {}
                for lokacija, izbori in po_lokaciji_b.items():
                    koristi_lokaciju_b = model.new_bool_var(
                        f"{prefiks}_lok_{len(lokacije_b)}_b"
                    )
                    model.add(koristi_lokaciju_b == sum(izbori))
                    lokacije_b[lokacija] = koristi_lokaciju_b
            else:
                lokacije_b = lokacije

        if dozvoljena_subota:
            _dodaj_subotnji_prioritet_sg(
                model,
                kazne,
                po_danu[len(DANI) - 1],
                lokacije,
                prefiks,
            )

        promenljive[jedinica.indeks] = PromenljiveJedinice(
            start=start,
            kraj=kraj,
            dan=dan,
            blok=blok,
            interval=interval,
            start_b=start_b,
            kraj_b=kraj_b,
            dan_b=dan_b,
            blok_b=blok_b,
            interval_b=interval_b,
            po_danu=tuple(po_danu),
            po_danu_b=po_danu_b,
            prostorije=izbor_prostorije,
            prostorije_b=izbor_prostorije_b,
            lokacije=lokacije,
            lokacije_b=lokacije_b,
        )
        intervali_nastavnika[zahtev.nastavnik].append(interval)
        if interval_b is not None:
            intervali_nastavnika_b[zahtev.nastavnik].append(interval_b)
        if zahtev.korepetitor:
            resurs = _resurs_korepetitora(zahtev.korepetitor)
            for pomeraj in jedinica.korepeticija:
                pocetak_korepeticije = model.new_int_var(
                    1, (len(DANI) - 1) * KORAK_DANA + 14,
                    f"{prefiks}_kor_{pomeraj}_start",
                )
                model.add(pocetak_korepeticije == start + pomeraj)
                kraj_korepeticije = model.new_int_var(
                    2, (len(DANI) - 1) * KORAK_DANA + 15,
                    f"{prefiks}_kor_{pomeraj}_kraj",
                )
                model.add(kraj_korepeticije == pocetak_korepeticije + 1)
                intervali_korepetitora[resurs].append(
                    model.new_interval_var(
                        pocetak_korepeticije, 1, kraj_korepeticije,
                        f"{prefiks}_kor_{pomeraj}_i",
                    )
                )
                if sa_nedeljom_b:
                    assert start_b is not None
                    pocetak_korepeticije_b = model.new_int_var(
                        1, (len(DANI) - 1) * KORAK_DANA + 14,
                        f"{prefiks}_kor_{pomeraj}_start_b",
                    )
                    model.add(pocetak_korepeticije_b == start_b + pomeraj)
                    kraj_korepeticije_b = model.new_int_var(
                        2, (len(DANI) - 1) * KORAK_DANA + 15,
                        f"{prefiks}_kor_{pomeraj}_kraj_b",
                    )
                    model.add(kraj_korepeticije_b == pocetak_korepeticije_b + 1)
                    intervali_korepetitora_b[resurs].append(
                        model.new_interval_var(
                            pocetak_korepeticije_b,
                            1,
                            kraj_korepeticije_b,
                            f"{prefiks}_kor_{pomeraj}_i_b",
                        )
                    )
        jedinice_zahteva[jedinica.zahtev_indeks].append(jedinica)

    if ima_np_program:
        model.add(sum(np_izbori["IV1"]) == 2)
        model.add(sum(np_izbori["IV2"]) == 2)
        model.add(sum(np_izbori["III1"]) + sum(np_izbori["III2"]) == 1)

    # Ista fizicka osoba je jedan resurs bez obzira na ulogu nastavnika
    # ili korepetitora.
    for osoba in sorted(set(intervali_nastavnika) | set(intervali_korepetitora)):
        model.add_no_overlap(
            intervali_nastavnika.get(osoba, [])
            + intervali_korepetitora.get(osoba, [])
        )
    for intervali in intervali_prostorija.values():
        model.add_no_overlap(intervali)
    kapaciteti = defaultdict(int)
    for prostorija in prostorije:
        kapaciteti[(prostorija.lokacija, prostorija.tip)] += 1
    for kljuc, intervali in intervali_kapaciteta.items():
        model.add_cumulative(intervali, [1] * len(intervali), kapaciteti[kljuc])
    for (_, _, kandidati), intervali in intervali_skupova_kandidata.items():
        model.add_cumulative(
            intervali, [1] * len(intervali), len(kandidati)
        )
    if sa_nedeljom_b:
        for osoba in sorted(set(intervali_nastavnika_b) | set(intervali_korepetitora_b)):
            model.add_no_overlap(
                intervali_nastavnika_b.get(osoba, [])
                + intervali_korepetitora_b.get(osoba, [])
            )
        for intervali in intervali_prostorija_b.values():
            model.add_no_overlap(intervali)
        for kljuc, intervali in intervali_kapaciteta_b.items():
            model.add_cumulative(
                intervali, [1] * len(intervali), kapaciteti[kljuc]
            )
        for (_, _, kandidati), intervali in intervali_skupova_kandidata_b.items():
            model.add_cumulative(
                intervali, [1] * len(intervali), len(kandidati)
            )

    # Identične jedinice istog zahteva uređujemo hronološki da uklonimo
    # veliki broj simetričnih rešenja.
    for stavke in jedinice_zahteva.values():
        po_obrascu: dict[tuple[int, tuple[int, ...]], list[Jedinica]] = defaultdict(list)
        for jedinica in stavke:
            po_obrascu[(jedinica.trajanje, jedinica.korepeticija)].append(jedinica)
        for grupa in po_obrascu.values():
            for prethodna, sledeca in zip(grupa, grupa[1:]):
                model.add(
                    promenljive[prethodna.indeks].start
                    < promenljive[sledeca.indeks].start
                )
                zahtev = ulaz.zahtevi[prethodna.zahtev_indeks]
                if sa_nedeljom_b and zahtev.smena.menja_se:
                    start_pre = promenljive[prethodna.indeks].start_b
                    start_posle = promenljive[sledeca.indeks].start_b
                    assert start_pre is not None and start_posle is not None
                    model.add(start_pre < start_posle)

    # Igrački predmeti srednje škole raspoređuju svaku sesiju drugog dana.
    # Time se dva zasebna dvočasa ne mogu slučajno spojiti u niz od četiri;
    # za glavni predmet ovo ujedno znači tačno jedan dvočas dnevno.
    for zahtev_indeks, stavke in jedinice_zahteva.items():
        zahtev = ulaz.zahtevi[zahtev_indeks]
        odeljenje = ulaz.odeljenja[zahtev.odeljenja[0]]
        if (
            odeljenje.skola is Skola.SREDNJA
            and ulaz.predmeti[zahtev.predmet].igracki
        ):
            model.add_all_different([promenljive[j.indeks].dan for j in stavke])

        # Klasičan balet u osnovnoj sa fondom 10 mora imati po jedan dvočas
        # svakog radnog dana. Pet različitih dana ograničenih na pon–pet
        # znači da nijedan dan ne može biti preskočen niti zamenjen subotom.
        osnovni_klasicni = (
            odeljenje.skola is Skola.OSNOVNA
            and zahtev.predmet == "Класичан балет"
            and zahtev.fond == 10
        )
        if osnovni_klasicni:
            dani = [promenljive[j.indeks].dan for j in stavke]
            model.add_all_different(dani)
            for dan in dani:
                model.add(dan <= 4)
            if sa_nedeljom_b and zahtev.smena.menja_se:
                dani_b = [promenljive[j.indeks].dan_b for j in stavke]
                assert all(dan is not None for dan in dani_b)
                model.add_all_different(dani_b)
                for dan in dani_b:
                    assert dan is not None
                    model.add(dan <= 4)

    # Verska i Građansko istog razreda dele termin i lokaciju.
    alternativni: dict[tuple[str, str], Jedinica] = {}
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        if zahtev.predmet in (VERSKA, GRADJANSKO):
            alternativni[(zahtev.predmet, zahtev.razred)] = jedinica
    preskoci_u_odeljenju: set[int] = set()
    for razred in sorted({z.razred for z in ulaz.zahtevi}):
        verska = alternativni.get((VERSKA, razred))
        gradjansko = alternativni.get((GRADJANSKO, razred))
        if not verska or not gradjansko:
            continue
        pv = promenljive[verska.indeks]
        pg = promenljive[gradjansko.indeks]
        model.add(pv.start == pg.start)
        _dodaj_jednakost_lokacije(model, pv, pg)
        # Za učenike je ovaj par jedno zauzeće; resursi nastavnika i dve
        # prostorije ostaju odvojeni.
        preskoci_u_odeljenju.add(gradjansko.indeks)

    # Ista deca iz celog odeljenja i polugrupa dele jedan NoOverlap resurs.
    po_ucenickom_tokenu: dict[str, list[Jedinica]] = defaultdict(list)
    for jedinica in jedinice:
        if jedinica.indeks in preskoci_u_odeljenju:
            continue
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        for token in _tokeni_odeljenja(ulaz, zahtev.odeljenja):
            po_ucenickom_tokenu[token].append(jedinica)

    for token, stavke in po_ucenickom_tokenu.items():
        # Grupisani zahtev može sadržati više oznaka koje se svode na isti
        # token; uklanjanje duplikata sprečava da isti interval dodamo dvaput.
        jedinstvene = {j.indeks: j for j in stavke}
        po_ucenickom_tokenu[token] = list(jedinstvene.values())
        model.add_no_overlap(
            [promenljive[j.indeks].interval for j in jedinstvene.values()]
        )
        if sa_nedeljom_b:
            intervali_b = [
                promenljive[j.indeks].interval_b for j in jedinstvene.values()
            ]
            assert all(interval is not None for interval in intervali_b)
            model.add_no_overlap(intervali_b)

    # Učenici nemaju prazne časove. Jedini izuzetak je tačno jedan putni blok
    # pri jedinoj dozvoljenoj promeni lokacije u toku dana.
    for token, stavke in po_ucenickom_tokenu.items():
        odeljenje = ulaz.odeljenja[token]
        for indeks_dana in range(len(DANI)):
            _dodaj_dnevno_pravilo_lokacije(
                model,
                kazne,
                token,
                indeks_dana,
                stavke,
                promenljive,
            )
            if odeljenje.skola is Skola.OSNOVNA:
                ukupno = [
                    jedinica.trajanje
                    * promenljive[jedinica.indeks].po_danu[indeks_dana]
                    for jedinica in stavke
                ]
                model.add(sum(ukupno) <= 4)
            elif odeljenje.skola is Skola.SREDNJA:
                igracki = []
                opsti = []
                ukupno = []
                for jedinica in stavke:
                    zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
                    prisustvo = (
                        jedinica.trajanje
                        * promenljive[jedinica.indeks].po_danu[indeks_dana]
                    )
                    ukupno.append(prisustvo)
                    if ulaz.predmeti[zahtev.predmet].igracki:
                        igracki.append(prisustvo)
                    elif zahtev.predmet in OPSTI_PREDMETI:
                        opsti.append(prisustvo)
                model.add(sum(igracki) <= 4)
                model.add(sum(opsti) <= 4)
                model.add(sum(ukupno) <= 8)

    # Naizmenična odeljenja imaju zaseban raspored u B, pa ista čvrsta pravila
    # primenjujemo i na njihove B promenljive.
    if sa_nedeljom_b:
        for token, stavke in po_ucenickom_tokenu.items():
            odeljenje = ulaz.odeljenja[token]
            if not odeljenje.smena.menja_se:
                continue
            for indeks_dana in range(len(DANI)):
                _dodaj_dnevno_pravilo_lokacije(
                    model,
                    kazne,
                    token,
                    indeks_dana,
                    stavke,
                    promenljive,
                    nedelja_b=True,
                )
                if odeljenje.skola is Skola.OSNOVNA:
                    ukupno = []
                    for jedinica in stavke:
                        po_danu_b = promenljive[jedinica.indeks].po_danu_b
                        assert po_danu_b is not None
                        ukupno.append(jedinica.trajanje * po_danu_b[indeks_dana])
                    model.add(sum(ukupno) <= 4)

    # Istorija: nijedna grupa ne sme imati dva časa istog dana.
    _dodaj_istoriju_jedan_cas_dnevno(model, ulaz, jedinice, promenljive)
    if sa_nedeljom_b:
        _dodaj_istoriju_jedan_cas_dnevno(
            model, ulaz, jedinice, promenljive, nedelja_b=True
        )

    # Aleksandar Bošković: II razred, dva dana po tri uzastopna časa od 7. bloka.
    _dodaj_pravilo_aleksandra_boskovica(
        model, ulaz, jedinice, promenljive
    )
    if sa_nedeljom_b:
        _dodaj_pravilo_aleksandra_boskovica(
            model, ulaz, jedinice, promenljive, nedelja_b=True
        )

    # Nastavnik ili korepetitor sme imati najviše jednu nedeljnu pauzu, dugu
    # najviše dva bloka. U dozvoljenom okviru cilj i dalje favorizuje potpuni
    # kontinuitet.
    _dodaj_kontinuitet_osoba(
        model, kazne, ulaz, jedinice, promenljive
    )
    if sa_nedeljom_b:
        _dodaj_kontinuitet_osoba(
            model, kazne, ulaz, jedinice, promenljive, nedelja_b=True
        )

    # Blaga funkcija kvaliteta: prednost imaju Knez Miletina i raniji blokovi.
    # Ispravnost ne zavisi od cilja; sva pravila iznad su čvrsta.
    troskovi: list[cp_model.LinearExprT] = list(kazne)
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        troskovi.append(p.blok)
        for lokacija, koristi in p.lokacije.items():
            if lokacija != "Кнез Милетина 8":
                troskovi.append(3 * koristi)
        if sa_nedeljom_b and zahtev.smena.menja_se:
            assert p.blok_b is not None and p.prostorije_b is not None
            troskovi.append(p.blok_b)
            assert p.lokacije_b is not None
            for lokacija, koristi in p.lokacije_b.items():
                if lokacija != "Кнез Милетина 8":
                    troskovi.append(3 * koristi)
    if sa_ciljem:
        model.minimize(sum(troskovi))
    _dodaj_hintove(
        model, ulaz, prostorije, jedinice_zahteva, promenljive, hintovi, hintovi_b
    )
    return model, jedinice, promenljive

def _kanonizuj_hintove(
    ulaz: Ulaz,
    hintovi: Sequence[Cas],
    prostorije: Sequence[Prostorija] = (),
) -> tuple[Cas, ...]:
    """Poveži latinični prethodni raspored sa kanonskim vrednostima ulaza."""

    def mapa(vrednosti: Iterable[str]) -> dict[str, str]:
        return {kljuc_pisma(v): v for v in vrednosti}

    dani = mapa(DANI)
    predmeti = mapa(ulaz.predmeti)
    odeljenja = mapa(ulaz.odeljenja)
    nastavnici = mapa(ulaz.nastavnici)
    korepetitori = mapa(ulaz.korepetitori)
    oznake_prostorija = mapa(p.oznaka for p in prostorije)

    def nadji(vrednost: str, vrednosti: dict[str, str]) -> str:
        return vrednosti.get(kljuc_pisma(vrednost), vrednost)

    return tuple(
        Cas(
            dan=nadji(c.dan, dani),
            blok=c.blok,
            predmet=nadji(c.predmet, predmeti),
            odeljenja=tuple(nadji(o, odeljenja) for o in c.odeljenja),
            nastavnik=nadji(c.nastavnik, nastavnici),
            korepetitor=(nadji(c.korepetitor, korepetitori) if c.korepetitor else None),
            prostorija=nadji(c.prostorija, oznake_prostorija),
            red=c.red,
        )
        for c in hintovi
    )


def _upari_hintove(
    ulaz: Ulaz,
    jedinice_zahteva: dict[int, list[Jedinica]],
    hintovi: Sequence[Cas],
) -> dict[int, tuple[int, int]]:
    """Za svaku jedinicu nađi (dan, blok) u prethodnom rasporedu.

    Redovi CSV-a se uparuju sa jedinicama istog zahteva tako da se poklope
    trajanje i obrazac korepeticije. Jedinice bez para se preskaču, pa se
    izmenjeni deo ulaza jednostavno ostavlja solveru.
    """

    po_kljucu: dict[tuple[str, str, tuple[str, ...]], list[Cas]] = defaultdict(list)
    for cas in hintovi:
        po_kljucu[(cas.predmet, cas.nastavnik, tuple(cas.odeljenja))].append(cas)

    rezultat: dict[int, tuple[int, int]] = {}
    for zahtev_indeks, jedinice in jedinice_zahteva.items():
        zahtev = ulaz.zahtevi[zahtev_indeks]
        redovi = po_kljucu.get(
            (zahtev.predmet, zahtev.nastavnik, tuple(zahtev.odeljenja)), []
        )
        if not redovi:
            continue
        redovi.sort(key=lambda c: (DANI.index(c.dan), c.blok, c.prostorija))
        neiskorisceni = set(range(len(redovi)))
        for jedinica in sorted(jedinice, key=lambda j: (-j.trajanje, j.redni_broj)):
            izabran: tuple[int, ...] | None = None
            for indeks in sorted(neiskorisceni):
                prvi = redovi[indeks]
                niz: list[int] = []
                for pomeraj in range(jedinica.trajanje):
                    pogodak = next(
                        (
                            i for i in neiskorisceni
                            if redovi[i].dan == prvi.dan
                            and redovi[i].blok == prvi.blok + pomeraj
                        ),
                        None,
                    )
                    if pogodak is None:
                        niz = []
                        break
                    niz.append(pogodak)
                if not niz:
                    continue
                korepeticija = tuple(
                    pomeraj for pomeraj, i in enumerate(niz) if redovi[i].korepetitor
                )
                if korepeticija != jedinica.korepeticija:
                    continue
                izabran = tuple(niz)
                break
            if not izabran:
                continue
            neiskorisceni.difference_update(izabran)
            cas = redovi[izabran[0]]
            rezultat[jedinica.indeks] = (DANI.index(cas.dan), cas.blok)
    return rezultat


def _u_domenu(promenljiva: cp_model.IntVar, vrednost: int) -> bool:
    domen = tuple(promenljiva.proto.domain)
    return any(
        donja <= vrednost <= gornja
        for donja, gornja in zip(domen[::2], domen[1::2])
    )


HintoviJedinica = dict[int, list[tuple[cp_model.IntVar, int]]]


def _pripremi_hintove(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice_zahteva: dict[int, list[Jedinica]],
    promenljive: dict[int, PromenljiveJedinice],
    hintovi: Sequence[Cas],
    hintovi_b: Sequence[Cas] = (),
) -> HintoviJedinica:
    """Za svaku jedinicu pripremi parove (promenljiva, vrednost) iz hinta.

    Hintuju se samo termini (dan, blok, start) obe nedelje; hint koji ne
    upada u domen promenljive se izostavlja, pa jedinica ostaje slobodna.
    """

    rezultat: HintoviJedinica = defaultdict(list)
    if not hintovi:
        return {}
    for nedelja_b, casovi in ((False, hintovi), (True, hintovi_b)):
        if not casovi:
            continue
        upareno = _upari_hintove(
            ulaz, jedinice_zahteva, _kanonizuj_hintove(ulaz, casovi, prostorije)
        )
        for indeks, (dan, blok) in upareno.items():
            p = promenljive[indeks]
            if nedelja_b:
                if p.start_b is None or p.start_b is p.start:
                    continue
                start_var, dan_var, blok_var = p.start_b, p.dan_b, p.blok_b
            else:
                start_var, dan_var, blok_var = p.start, p.dan, p.blok
            assert dan_var is not None and blok_var is not None
            start_hinta = dan * KORAK_DANA + blok
            if not _u_domenu(start_var, start_hinta):
                continue
            rezultat[indeks].extend(
                [(dan_var, dan), (blok_var, blok), (start_var, start_hinta)]
            )
    return dict(rezultat)


def _primeni_hintove(
    model: cp_model.CpModel,
    hintovi_jedinica: HintoviJedinica,
    slobodne: Iterable[int] = (),
) -> int:
    """Postavi hintove u model, preskačući jedinice koje treba ostaviti slobodne."""

    model.clear_hints()
    slobodne = set(slobodne)
    broj = 0
    for indeks, parovi in hintovi_jedinica.items():
        if indeks in slobodne:
            continue
        for promenljiva, vrednost in parovi:
            model.add_hint(promenljiva, vrednost)
        broj += 1
    return broj


def _dodaj_hintove(
    model: cp_model.CpModel,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice_zahteva: dict[int, list[Jedinica]],
    promenljive: dict[int, PromenljiveJedinice],
    hintovi: Sequence[Cas],
    hintovi_b: Sequence[Cas] = (),
) -> HintoviJedinica:
    """Dodaj CP-SAT hintove termina iz prethodnog rasporeda za obe nedelje.

    Hintovi su nepotpuni (samo termini), pa ih CP-SAT sam po sebi slabo
    prati; zato ih :func:`_resi_u_dve_faze` prvo pokušava kao fiksirane.
    """

    pripremljeni = _pripremi_hintove(
        ulaz, prostorije, jedinice_zahteva, promenljive, hintovi, hintovi_b
    )
    if pripremljeni:
        _primeni_hintove(model, pripremljeni)
    return pripremljeni


def _susedi_jedinica(
    ulaz: Ulaz, jedinice: Sequence[Jedinica]
) -> dict[int, set[int]]:
    """Jedinice koje dele nastavnika, korepetitora ili odeljenje (polugrupu)."""

    po_resursu: dict[object, set[int]] = defaultdict(set)
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        po_resursu[("osoba", _resurs_korepetitora(zahtev.nastavnik))].add(jedinica.indeks)
        if zahtev.korepetitor and jedinica.korepeticija:
            po_resursu[("osoba", _resurs_korepetitora(zahtev.korepetitor))].add(
                jedinica.indeks
            )
        for token in _tokeni_odeljenja(ulaz, zahtev.odeljenja):
            po_resursu[("odeljenje", token)].add(jedinica.indeks)
    susedi: dict[int, set[int]] = defaultdict(set)
    for clanovi in po_resursu.values():
        for indeks in clanovi:
            susedi[indeks].update(clanovi)
    return susedi


def _nivoi_oslobadjanja(
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
    hintovi_jedinica: HintoviJedinica,
    najvise_nivoa: int = 2,
) -> list[set[int]]:
    """Skupovi jedinica koje se redom oslobađaju kad fiksirani hint ne prolazi.

    Nivo 0 oslobađa samo jedinice bez hinta (izmenjeni ili novi zahtevi,
    termini van domena). Svaki sledeći nivo dodaje sve jedinice koje sa već
    slobodnima dele nastavnika, korepetitora ili odeljenje.
    """

    slobodne = {j.indeks for j in jedinice if j.indeks not in hintovi_jedinica}
    nivoi = [set(slobodne)]
    susedi = _susedi_jedinica(ulaz, jedinice)
    for _ in range(najvise_nivoa):
        prosireno = set(slobodne)
        for indeks in slobodne:
            prosireno.update(susedi.get(indeks, ()))
        if prosireno == slobodne:
            break
        slobodne = prosireno
        nivoi.append(set(slobodne))
    return nivoi


def _status_tekst(status: cp_model.CpSolverStatus) -> str:
    return {
        cp_model.OPTIMAL: "optimalno",
        cp_model.FEASIBLE: "dopustivo",
        cp_model.INFEASIBLE: "nema rešenja",
        cp_model.MODEL_INVALID: "neispravan model",
        cp_model.UNKNOWN: "vremensko ograničenje",
    }.get(status, str(status))


def _preostali_limit_prve_faze(
    limit_prve: float,
    vremensko_ogranicenje: float,
    proteklo: float,
) -> float:
    """Vrati neiskorišćeni deo budžeta prve i ukupne faze."""

    return max(
        0.0,
        min(limit_prve - proteklo, vremensko_ogranicenje - proteklo),
    )


def _dodeli_prostorije(
    solver_termina: cp_model.CpSolver,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
    fiksne: dict[int, str] | None = None,
    vremensko_ogranicenje: float = 60,
    broj_radnika: int = 8,
) -> dict[int, str] | None:
    """Dodeli konkretne prostorije pošto su termini i lokacije već poznati."""

    model = cp_model.CpModel()
    izbori: dict[int, dict[str, cp_model.BoolVar]] = {}
    intervali: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    kazne: list[cp_model.LinearExprT] = []
    fiksne = fiksne or {}
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        start_var = p.start_b if nedelja_b else p.start
        lokacije = p.lokacije_b if nedelja_b else p.lokacije
        assert start_var is not None and lokacije is not None
        start = solver_termina.value(start_var)
        lokacija = next(
            naziv
            for naziv, koristi in lokacije.items()
            if solver_termina.boolean_value(koristi)
        )
        moguce = [
            prostorija
            for prostorija in _moguce_prostorije(
                zahtev, ulaz, prostorije, jedinica.trajanje
            )
            if prostorija.lokacija == lokacija
            and prostorija_dostupna(
                ulaz.dostupnost_prostorija,
                prostorija.oznaka,
                DANI[start // KORAK_DANA],
                range(start % KORAK_DANA, start % KORAK_DANA + jedinica.trajanje),
            )
        ]
        if jedinica.indeks in fiksne:
            moguce = [p for p in moguce if p.oznaka == fiksne[jedinica.indeks]]
        if not moguce:
            return None
        izbori[jedinica.indeks] = {}
        for prostorija in moguce:
            koristi = model.new_bool_var(
                f"j{jedinica.indeks}_{prostorija.oznaka}"
            )
            izbori[jedinica.indeks][prostorija.oznaka] = koristi
            kazna = _kazna_strukturisanih_pravila(
                ulaz, zahtev, prostorija.oznaka, jedinica.trajanje
            )
            if kazna:
                kazne.append(kazna * koristi)
            kazna_km8 = _kazna_sale_km8(zahtev, prostorija.oznaka)
            if kazna_km8:
                kazne.append(kazna_km8 * koristi)
            intervali[prostorija.oznaka].append(
                model.new_optional_fixed_size_interval_var(
                    start,
                    jedinica.trajanje,
                    koristi,
                    f"j{jedinica.indeks}_{prostorija.oznaka}_i",
                )
            )
        model.add_exactly_one(izbori[jedinica.indeks].values())
    for stavke in intervali.values():
        model.add_no_overlap(stavke)
    if kazne:
        model.minimize(sum(kazne))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    solver.parameters.num_search_workers = broj_radnika
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {
        indeks: next(
            oznaka
            for oznaka, koristi in po_prostoriji.items()
            if solver.boolean_value(koristi)
        )
        for indeks, po_prostoriji in izbori.items()
    }


def _dodeli_prostorije_obe(
    solver_termina: cp_model.CpSolver,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    vremensko_ogranicenje: float = 60,
    broj_radnika: int = 8,
) -> tuple[dict[int, str], dict[int, str]] | None:
    """Zajedno dodeli prostorije za A i B uz iste sobe stalnih smena."""

    model = cp_model.CpModel()
    izbori_a: dict[int, dict[str, cp_model.BoolVar]] = {}
    izbori_b: dict[int, dict[str, cp_model.BoolVar]] = {}
    intervali_a: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_b: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    kazne: list[cp_model.LinearExprT] = []
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        assert p.start_b is not None and p.lokacije_b is not None
        start_a = solver_termina.value(p.start)
        start_b = solver_termina.value(p.start_b)
        lokacija_a = next(n for n, x in p.lokacije.items() if solver_termina.boolean_value(x))
        lokacija_b = next(n for n, x in p.lokacije_b.items() if solver_termina.boolean_value(x))
        moguce = _moguce_prostorije(
            zahtev, ulaz, prostorije, jedinica.trajanje
        )
        moguce_a = [
            s for s in moguce
            if s.lokacija == lokacija_a
            and prostorija_dostupna(
                ulaz.dostupnost_prostorija, s.oznaka,
                DANI[start_a // KORAK_DANA],
                range(start_a % KORAK_DANA, start_a % KORAK_DANA + jedinica.trajanje),
            )
        ]
        moguce_b = [
            s for s in moguce
            if s.lokacija == lokacija_b
            and prostorija_dostupna(
                ulaz.dostupnost_prostorija, s.oznaka,
                DANI[start_b // KORAK_DANA],
                range(start_b % KORAK_DANA, start_b % KORAK_DANA + jedinica.trajanje),
            )
        ]
        if not moguce_a or not moguce_b:
            return None
        izbori_a[jedinica.indeks] = {}
        izbori_b[jedinica.indeks] = {}
        for soba in moguce_a:
            koristi = model.new_bool_var(f"j{jedinica.indeks}_{soba.oznaka}_a")
            izbori_a[jedinica.indeks][soba.oznaka] = koristi
            kazna = _kazna_strukturisanih_pravila(
                ulaz, zahtev, soba.oznaka, jedinica.trajanje
            )
            if kazna:
                kazne.append(kazna * koristi)
            kazna_km8 = _kazna_sale_km8(zahtev, soba.oznaka)
            if kazna_km8:
                kazne.append(kazna_km8 * koristi)
            intervali_a[soba.oznaka].append(model.new_optional_fixed_size_interval_var(
                start_a, jedinica.trajanje, koristi,
                f"j{jedinica.indeks}_{soba.oznaka}_i_a",
            ))
        model.add_exactly_one(izbori_a[jedinica.indeks].values())
        if zahtev.smena.menja_se:
            for soba in moguce_b:
                koristi = model.new_bool_var(f"j{jedinica.indeks}_{soba.oznaka}_b")
                izbori_b[jedinica.indeks][soba.oznaka] = koristi
                kazna = _kazna_strukturisanih_pravila(
                    ulaz, zahtev, soba.oznaka, jedinica.trajanje
                )
                if kazna:
                    kazne.append(kazna * koristi)
                kazna_km8 = _kazna_sale_km8(zahtev, soba.oznaka)
                if kazna_km8:
                    kazne.append(kazna_km8 * koristi)
                intervali_b[soba.oznaka].append(model.new_optional_fixed_size_interval_var(
                    start_b, jedinica.trajanje, koristi,
                    f"j{jedinica.indeks}_{soba.oznaka}_i_b",
                ))
            model.add_exactly_one(izbori_b[jedinica.indeks].values())
        else:
            izbori_b[jedinica.indeks] = izbori_a[jedinica.indeks]
            for soba in moguce_a:
                intervali_b[soba.oznaka].append(model.new_optional_fixed_size_interval_var(
                    start_b, jedinica.trajanje,
                    izbori_a[jedinica.indeks][soba.oznaka],
                    f"j{jedinica.indeks}_{soba.oznaka}_i_b",
                ))
    for stavke in intervali_a.values():
        model.add_no_overlap(stavke)
    for stavke in intervali_b.values():
        model.add_no_overlap(stavke)
    if kazne:
        model.minimize(sum(kazne))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    solver.parameters.num_search_workers = broj_radnika
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    def izvuci(izbori: dict[int, dict[str, cp_model.BoolVar]]) -> dict[int, str]:
        return {
            indeks: next(o for o, x in po_sobi.items() if solver.boolean_value(x))
            for indeks, po_sobi in izbori.items()
        }

    return izvuci(izbori_a), izvuci(izbori_b)


def _izvuci_casove(
    solver: cp_model.CpSolver,
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
    dodeljene_prostorije: dict[int, str] | None = None,
) -> tuple[Cas, ...]:
    redovi: list[Cas] = []
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        dan_var = p.dan_b if nedelja_b else p.dan
        blok_var = p.blok_b if nedelja_b else p.blok
        assert dan_var is not None and blok_var is not None
        dan = solver.value(dan_var)
        blok = solver.value(blok_var)
        if dodeljene_prostorije is not None:
            prostorija = dodeljene_prostorije[jedinica.indeks]
        else:
            prostorije_var = p.prostorije_b if nedelja_b else p.prostorije
            assert prostorije_var is not None
            prostorija = next(
                oznaka for oznaka, koristi in prostorije_var.items()
                if solver.boolean_value(koristi)
            )
        for pomeraj in range(jedinica.trajanje):
            redovi.append(
                Cas(
                    dan=DANI[dan],
                    blok=blok + pomeraj,
                    predmet=zahtev.predmet,
                    odeljenja=zahtev.odeljenja,
                    nastavnik=zahtev.nastavnik,
                    korepetitor=(
                        zahtev.korepetitor if pomeraj in jedinica.korepeticija else None
                    ),
                    prostorija=prostorija,
                    red=0,
                )
            )
    redovi.sort(key=lambda c: (DANI.index(c.dan), c.blok, c.prostorija, c.predmet))
    return tuple(replace_red(cas, indeks + 2) for indeks, cas in enumerate(redovi))


def _resi_fiksiranim_hintom(
    model: cp_model.CpModel,
    solver: cp_model.CpSolver,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    hintovi: Sequence[Cas],
    hintovi_b: Sequence[Cas],
    vremensko_ogranicenje: float,
    pocetak: float,
) -> cp_model.CpSolverStatus:
    """Pokušaj prethodni raspored kao fiksiran, sve labavije oko izmena."""

    jedinice_zahteva: dict[int, list[Jedinica]] = defaultdict(list)
    for jedinica in jedinice:
        jedinice_zahteva[jedinica.zahtev_indeks].append(jedinica)
    pripremljeni = _pripremi_hintove(
        ulaz, prostorije, jedinice_zahteva, promenljive, hintovi, hintovi_b
    )
    if not pripremljeni:
        print("FAZA 1 — hint se ne poklapa ni sa jednom jedinicom; tražim novo rešenje")
        return cp_model.UNKNOWN

    status = cp_model.UNKNOWN
    solver.parameters.fix_variables_to_their_hinted_value = True
    for nivo, slobodne in enumerate(
        _nivoi_oslobadjanja(ulaz, jedinice, pripremljeni)
    ):
        fiksirane = _primeni_hintove(model, pripremljeni, slobodne)
        if fiksirane == 0:
            break
        preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
        if preostalo <= 0:
            break
        solver.parameters.max_time_in_seconds = min(LIMIT_FIKSIRANOG_HINTA, preostalo)
        korak = time.monotonic()
        status = solver.solve(model)
        trajanje = time.monotonic() - korak
        opis = (
            "prethodni raspored je i dalje dopustiv"
            if nivo == 0
            else f"prethodni raspored prolazi uz {len(slobodne)} oslobođenih jedinica"
        )
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"FAZA 1 — {opis} (fiksirani hint, nivo {nivo}, {trajanje:.3f} s)")
            break
        print(
            f"FAZA 1 — fiksirani hint nivo {nivo} ({fiksirane} jedinica) ne prolazi: "
            f"{_status_tekst(status)}, {trajanje:.3f} s"
        )
    solver.parameters.fix_variables_to_their_hinted_value = False
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _primeni_hintove(model, pripremljeni)
        print("FAZA 1 — prethodni raspored nije upotrebljiv kao fiksirani hint; tražim novo rešenje")
    return status


def _resi_u_dve_faze(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    jutarnja_smena: Smena,
    vremensko_ogranicenje: float,
    broj_radnika: int,
    seme: int,
    hintovi: Sequence[Cas] = (),
    sa_nedeljom_b: bool = False,
    hintovi_b: Sequence[Cas] = (),
) -> tuple[
    cp_model.CpSolver | None,
    tuple[Jedinica, ...],
    dict[int, PromenljiveJedinice],
    str,
]:
    """Prvo nađi dopustivo rešenje, zatim ga koristi kao hint optimizaciji."""

    pocetak = time.monotonic()
    limit_prve = max(60.0, vremensko_ogranicenje - 300.0)
    model_1, jedinice_1, promenljive_1 = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        jutarnja_smena,
        sa_nedeljom_b=sa_nedeljom_b,
        samo_lokacije=True,
        sa_ciljem=False,
        hintovi=hintovi,
        hintovi_b=hintovi_b,
    )
    solver_1 = cp_model.CpSolver()
    solver_1.parameters.num_search_workers = broj_radnika
    solver_1.parameters.random_seed = seme
    status_1 = cp_model.UNKNOWN
    if hintovi:
        # Prethodni raspored je obično i dalje dopustiv. Nepotpun hint CP-SAT
        # ne uspeva da dopuni pretragom, ali fiksiranje hintovanih termina
        # daje rešenje za sekundu. Ako ulaz više ne dozvoljava stari
        # raspored, odgovor je INFEASIBLE za deo sekunde; tada se redom
        # oslobađaju jedinice oko izmene, pa tek onda ide obična pretraga.
        status_1 = _resi_fiksiranim_hintom(
            model_1, solver_1, ulaz, prostorije, jedinice_1, promenljive_1,
            hintovi, hintovi_b, vremensko_ogranicenje, pocetak,
        )
    if status_1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        proteklo = time.monotonic() - pocetak
        solver_1.parameters.max_time_in_seconds = _preostali_limit_prve_faze(
            limit_prve,
            vremensko_ogranicenje,
            proteklo,
        )
        status_1 = solver_1.solve(model_1)
    trajanje_prve = time.monotonic() - pocetak
    if status_1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        preostalo = vremensko_ogranicenje - trajanje_prve
        if preostalo > 0:
            print(
                "FAZA 1 — prvi rok je istekao; nastavljam do ukupnog "
                f"ograničenja ({preostalo:.1f} s preostalo)"
            )
            solver_1.parameters.max_time_in_seconds = preostalo
            status_1 = solver_1.solve(model_1)
            trajanje_prve = time.monotonic() - pocetak
    print(f"FAZA 1 — trajanje: {trajanje_prve:.3f} s")
    if status_1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = _status_tekst(status_1)
        print(f"FAZA 1 — neuspeh/timeout: {status}")
        print("FAZA 2 — trajanje: 0.000 s")
        return None, jedinice_1, promenljive_1, f"neuspeh/timeout (faza 1): {status}"
    print("FAZA 1 — dopustivo rešenje pronađeno")

    model_2, jedinice_2, promenljive_2 = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        jutarnja_smena,
        sa_nedeljom_b=sa_nedeljom_b,
        samo_lokacije=False,
        sa_ciljem=True,
    )
    for jedinica in jedinice_1:
        p1 = promenljive_1[jedinica.indeks]
        p2 = promenljive_2[jedinica.indeks]
        for prethodna, sledeca in (
            (p1.start, p2.start), (p1.dan, p2.dan), (p1.blok, p2.blok),
        ):
            model_2.add_hint(sledeca, solver_1.value(prethodna))
        for lokacija in set(p1.lokacije) & set(p2.lokacije):
            model_2.add_hint(
                p2.lokacije[lokacija], solver_1.value(p1.lokacije[lokacija])
            )
        if p1.start_b is not None and p2.start_b is not None:
            for prethodna, sledeca in (
                (p1.start_b, p2.start_b),
                (p1.dan_b, p2.dan_b),
                (p1.blok_b, p2.blok_b),
            ):
                assert prethodna is not None and sledeca is not None
                if prethodna is not p1.start and sledeca is not p2.start:
                    model_2.add_hint(sledeca, solver_1.value(prethodna))
        if p1.lokacije_b is not None and p2.lokacije_b is not None:
            for lokacija in set(p1.lokacije_b) & set(p2.lokacije_b):
                prethodna = p1.lokacije_b[lokacija]
                sledeca = p2.lokacije_b[lokacija]
                if prethodna is not p1.lokacije.get(lokacija):
                    model_2.add_hint(sledeca, solver_1.value(prethodna))

    preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
    if preostalo <= 0:
        print("FAZA 2 — timeout pre početka optimizacije")
        return (
            solver_1,
            jedinice_1,
            promenljive_1,
            "dopustivo (faza 1); faza 2: timeout",
        )

    solver_2 = cp_model.CpSolver()
    solver_2.parameters.max_time_in_seconds = preostalo
    solver_2.parameters.num_search_workers = broj_radnika
    solver_2.parameters.random_seed = seme
    status_2 = solver_2.solve(model_2)
    trajanje_druge = time.monotonic() - pocetak - trajanje_prve
    print(f"FAZA 2 — trajanje: {max(0.0, trajanje_druge):.3f} s")
    if status_2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = _status_tekst(status_2)
        print(f"FAZA 2 — optimizovano rešenje: {status}")
        return solver_2, jedinice_2, promenljive_2, f"optimizovano (faza 2): {status}"

    status = _status_tekst(status_2)
    print(f"FAZA 2 — neuspeh/timeout: {status}; koristi se dopustivo rešenje iz faze 1")
    return (
        solver_1,
        jedinice_1,
        promenljive_1,
        f"dopustivo (faza 1); faza 2 neuspeh/timeout: {status}",
    )


def resi_nedelju(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    jutarnja_smena: Smena,
    vremensko_ogranicenje: float = 300,
    broj_radnika: int = 8,
    seme: int = 1,
    hintovi: Sequence[Cas] = (),
    sa_nedeljom_b: bool = False,
    hintovi_b: Sequence[Cas] = (),
) -> Rezultat:
    """Reši jednu nedelju i proveri dobijene časove nezavisnim proveravačem."""

    solver, jedinice, promenljive, status_tekst = _resi_u_dve_faze(
        ulaz,
        prostorije,
        nedostupnosti,
        jutarnja_smena,
        vremensko_ogranicenje,
        broj_radnika,
        seme,
        hintovi,
        sa_nedeljom_b,
        hintovi_b,
    )
    if solver is None:
        return Rezultat(status_tekst, (), None, None)

    dodela = _dodeli_prostorije(
        solver, ulaz, prostorije, jedinice, promenljive,
        broj_radnika=broj_radnika,
    )
    if dodela is None:
        return Rezultat("НЕМА ДОДЕЛЕ ПРОСТОРИЈА", (), None, None)
    casovi = _izvuci_casove(
        solver, ulaz, jedinice, promenljive,
        dodeljene_prostorije=dodela,
    )
    izvestaj = proveri(ulaz, prostorije, nedostupnosti, casovi, jutarnja_smena)
    cilj = solver.objective_value if "faza 2" in status_tekst and "optimizovano" in status_tekst else None
    return Rezultat(status_tekst, casovi, izvestaj, cilj)


def replace_red(cas: Cas, red: int) -> Cas:
    """Napravi isti čas sa brojem reda koji će imati u izlaznom CSV-u."""

    return replace(cas, red=red)


def resi_obe_nedelje(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    vremensko_ogranicenje: float = 300,
    broj_radnika: int = 8,
    seme: int = 1,
    hintovi: Sequence[Cas] = (),
    hintovi_b: Sequence[Cas] = (),
) -> tuple[Rezultat, Rezultat]:
    """Reši A i B zajedno, da izbor rasporeda A ne može blokirati B."""

    solver, jedinice, promenljive, status_tekst = _resi_u_dve_faze(
        ulaz,
        prostorije,
        nedostupnosti,
        Smena.CRVENA,
        vremensko_ogranicenje,
        broj_radnika,
        seme,
        hintovi,
        True,
        hintovi_b,
    )
    if solver is None:
        prazan = Rezultat(status_tekst, (), None, None)
        return prazan, prazan
    dodele = _dodeli_prostorije_obe(
        solver, ulaz, prostorije, jedinice, promenljive,
        broj_radnika=broj_radnika,
    )
    if dodele is None:
        prazan = Rezultat("НЕМА ДОДЕЛЕ ПРОСТОРИЈА", (), None, None)
        return prazan, prazan
    dodela_a, dodela_b = dodele
    casovi_a = _izvuci_casove(
        solver, ulaz, jedinice, promenljive,
        dodeljene_prostorije=dodela_a,
    )
    casovi_b = _izvuci_casove(
        solver, ulaz, jedinice, promenljive, nedelja_b=True,
        dodeljene_prostorije=dodela_b,
    )
    cilj = solver.objective_value if "optimizovano" in status_tekst else None
    return Rezultat(
        status_tekst,
        casovi_a,
        proveri(ulaz, prostorije, nedostupnosti, casovi_a, Smena.CRVENA),
        cilj,
    ), Rezultat(
        status_tekst,
        casovi_b,
        proveri(ulaz, prostorije, nedostupnosti, casovi_b, Smena.PLAVA),
        cilj,
    )


def sacuvaj_csv(putanja: str | Path, casovi: Sequence[Cas]) -> None:
    """Sačuvaj rešenje na latinici, u formatu nezavisnog proveravača."""

    putanja = Path(putanja)
    putanja.parent.mkdir(parents=True, exist_ok=True)
    with putanja.open("w", encoding="utf-8", newline="") as datoteka:
        pisac = csv.writer(datoteka)
        pisac.writerow(
            ("dan", "blok", "predmet", "odeljenja", "nastavnik", "korepetitor", "prostorija")
        )
        for cas in casovi:
            pisac.writerow(
                (
                    u_latinicu(cas.dan),
                    cas.blok,
                    u_latinicu(cas.predmet),
                    ";".join(u_latinicu(o) for o in cas.odeljenja),
                    u_latinicu(cas.nastavnik),
                    u_latinicu(cas.korepetitor or ""),
                    u_latinicu(cas.prostorija),
                )
            )


def ucitaj_standardne_ulaze(
    direktorijum: str | Path,
) -> tuple[Ulaz, tuple[Prostorija, ...], tuple[Nedostupnost, ...]]:
    direktorijum = Path(direktorijum)
    ulaz = ucitaj_vise(
        [
            direktorijum / "osnovna_baletska_skola.csv",
            direktorijum / "srednja_baletska_skola.csv",
            direktorijum / "ostali_casovi.csv",
        ]
    )
    try:
        pravila = ucitaj_pravila_prostorija(
            direktorijum / "pravila_prostorija.csv"
        )
        dostupnost = ucitaj_dostupnost_prostorija(
            direktorijum / "dostupnost_prostorija.csv"
        )
    except FileNotFoundError as greska:
        raise UlazGreska(
            [f"недостаје обавезна датотека „{Path(greska.filename).name}“"]
        ) from greska
    prostorije = ucitaj_prostorije(direktorijum / "prostorije.csv")
    proveri_veze_pravila_prostorija(ulaz, prostorije, pravila, dostupnost)
    return (
        replace(
            ulaz,
            pravila_prostorija=pravila,
            dostupnost_prostorija=dostupnost,
        ),
        prostorije,
        ucitaj_nedostupnost(direktorijum / "nedostupnost.csv"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Napravi dve CSV nedelje rasporeda")
    parser.add_argument("--ulazi", type=Path, default=Path("ulazi"))
    parser.add_argument("--izlaz", type=Path, required=True, help="direktorijum za dve CSV datoteke")
    parser.add_argument("--vremensko-ogranicenje", type=float, default=300)
    parser.add_argument("--broj-radnika", type=int, default=8)
    parser.add_argument("--seme", type=int, default=1)
    parser.add_argument(
        "--hintovi", type=Path, default=None,
        help="CSV prethodne nedelje A koji se koristi kao CP-SAT hint",
    )
    parser.add_argument(
        "--hintovi-b", type=Path, default=None,
        help="CSV prethodne nedelje B (naizmenična odeljenja imaju svoje termine)",
    )
    argumenti = parser.parse_args(argv)

    ulaz, prostorije, nedostupnosti = ucitaj_standardne_ulaze(argumenti.ulazi)
    hintovi: tuple[Cas, ...] = ()
    hintovi_b: tuple[Cas, ...] = ()
    if argumenti.hintovi is not None and argumenti.hintovi.exists():
        hintovi = ucitaj_resenje(argumenti.hintovi)
        print(f"HINT: učitan je {argumenti.hintovi}; hint ide u fazu 1.")
        if argumenti.hintovi_b is not None and argumenti.hintovi_b.exists():
            hintovi_b = ucitaj_resenje(argumenti.hintovi_b)
            print(f"HINT: učitan je i {argumenti.hintovi_b} za nedelju B.")
        else:
            print("HINT: nedelja B nije prosleđena; naizmenična odeljenja u B nemaju hint.")
    elif argumenti.hintovi is not None:
        print(f"HINT: {argumenti.hintovi} ne postoji; rešavač radi bez hintova.")
    else:
        print("HINT: nije prosleđen fajl; rešavač radi bez hintova.")
    rezultat_a, rezultat_b = resi_obe_nedelje(
        ulaz,
        prostorije,
        nedostupnosti,
        vremensko_ogranicenje=argumenti.vremensko_ogranicenje,
        broj_radnika=argumenti.broj_radnika,
        seme=argumenti.seme,
        hintovi=hintovi,
        hintovi_b=hintovi_b,
    )
    izlazni_status = 0
    for ime, rezultat in (
        ("nedelja_a.csv", rezultat_a),
        ("nedelja_b.csv", rezultat_b),
    ):
        print(f"{ime}: {rezultat.status}")
        if not rezultat.pronadjen:
            izlazni_status = 1
            continue
        putanja = argumenti.izlaz / ime
        sacuvaj_csv(putanja, rezultat.casovi)
        assert rezultat.izvestaj is not None
        print(rezultat.izvestaj.tekst(latinica=True))
        if not rezultat.izvestaj.ispravan:
            izlazni_status = 1
    if rezultat_a.pronadjen and rezultat_b.pronadjen:
        napravi_html(
            argumenti.izlaz / "nedelja_a.csv",
            argumenti.izlaz / "nedelja_b.csv",
            argumenti.izlaz / "raspored.html",
        )
        print(f"HTML: {argumenti.izlaz / 'raspored.html'}")
    return izlazni_status


if __name__ == "__main__":
    raise SystemExit(main())
