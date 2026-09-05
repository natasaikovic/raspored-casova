"""CP-SAT rešavač rasporeda časova.

Rešavač proizvodi isti CSV koji čita :mod:`src.proveravac`. Model bira obe
nedelje zajedno. Srednja škola i stalne smene ostaju iste, dok naizmenične
smene osnovne škole u B koriste inverz smene iz A.
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Collection, Iterable, Sequence

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
    bezbedna_namena_km8,
    dozvoljena_prostorija,
    kanonska_prostorija,
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
KLASICAN_BALET = "Класичан балет"
TRADICIONALNO_PEVANJE = "Традиционално певање"
SALE_TRADICIONALNOG_PEVANJA = frozenset({"SG-2", "SG-3"})
SG_SALE = frozenset({"SG-1", "SG-2", "SG-3"})
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

# Lokalna promena do dvadeset jedinica i dalje može brzo da se popravi preko
# fiksiranog toplog starta. Veći broj znači da je prethodni raspored strukturno
# zastareo; tada pripremni pokušaji lako pojedu gotovo ceo budžet prave pretrage.
PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA = 20

# Hladni master bira samo termine i lokacije. Poslednji deo ukupnog budzeta
# cuva se za mali egzaktni model koji zatim zajedno bira konkretne sobe u A i
# B nedelji. Za kratke testne pozive koristi se polovina dostupnog budzeta.
REZERVA_ZA_DODELU_PROSTORIJA = 120.0
# Kada tacna dodela soba padne, isti termini se jos jednom resavaju punim
# modelom u kojem su i lokacije i sobe slobodne. To je daleko jeftinije
# od novog master solve-a, koji traje stotinama sekundi.
REZERVA_ZA_ISTE_TERMINE = 240.0
NAJVISE_HLADNIH_MASTER_POKUSAJA = 4
MINIMALNI_BUDZET_HLADNOG_POKUSAJA = 5.0

# Posle room UNSAT reza model već sadrži kompletan interni hint upravo
# pronađenog master rešenja. CP-SAT tada može da traži njegovu malu popravku
# pre prelaska na redovnu pretragu. Podrazumevanih 10 konflikata je premalo za
# ovaj master; 100k daje popravci realnu šansu, a ukupni zidni limit pokušaja i
# dalje čvrsto ograničava njeno trajanje.
LIMIT_KONFLIKATA_POPRAVKE_MASTER_HINTA = 100_000

# Model dodele soba sa funkcijom cilja ponekad vrati sve pretpostavke kao
# sufficient core. Jedan kratki dokaz bez cilja obicno vrati pravi mali Hall
# sukob, ali ne sme da uzme vreme narednom master pokusaju.
PRAG_VELIKOG_JEZGRA_SOBA = 64
MIN_BUDZET_PONOVNOG_DOKAZA_SOBA = 5.0
MAX_BUDZET_PONOVNOG_DOKAZA_SOBA = 10.0

# Subota je krajnje sredstvo, a ne ravnopravan šesti dan. Težina je iznad
# kazne za prekid nastavniku (500) i za salu van Sportske gimnazije (500),
# pa solver radije prihvata rupu u rasporedu nego čas subotom; ostaje ispod
# reda veličine tvrdih pravila, da subota i dalje bude moguća kad drugačije
# ne ide. Podizanje ove vrednosti gura subotu ka „samo ako mora“.
KAZNA_ZA_SUBOTU = 1500


class _TelemetrijaFaze2(cp_model.CpSolverSolutionCallback):
    """Ispiši svaki novi incumbent tokom optimizacije druge faze."""

    def __init__(self) -> None:
        super().__init__()
        self._najbolji_cilj: float | None = None
        self.broj_incumbenata = 0

    def on_solution_callback(self) -> None:
        cilj = self.objective_value
        if self._najbolji_cilj is not None and cilj >= self._najbolji_cilj:
            return
        self._najbolji_cilj = cilj
        self.broj_incumbenata += 1
        print(
            f"FAZA 2 — incumbent {self.broj_incumbenata}: "
            f"t={self.wall_time:.3f} s, objective={cilj:.0f}, "
            f"best_bound={self.best_objective_bound:.0f}"
        )


def _relativni_gap(cilj: float, granica: float) -> float:
    """Relativno odstupanje incumbenta od najbolje poznate granice."""

    return abs(cilj - granica) / max(1.0, abs(cilj), abs(granica))


def _ispisi_zavrsnu_telemetriju_faze_2(
    solver: cp_model.CpSolver,
    status: cp_model.CpSolverStatus,
) -> None:
    """Ispiši završne pokazatelje pretrage bez obzira na njen ishod."""

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        cilj = solver.objective_value
        granica = solver.best_objective_bound
        gap = _relativni_gap(cilj, granica)
        print(
            "FAZA 2 — završno: "
            f"objective={cilj:.0f}, best_bound={granica:.0f}, "
            f"relativni_gap={gap:.6%}, branches={solver.num_branches}, "
            f"conflicts={solver.num_conflicts}"
        )
    else:
        print(
            "FAZA 2 — završno: objective=n/a, best_bound=n/a, "
            f"relativni_gap=n/a, branches={solver.num_branches}, "
            f"conflicts={solver.num_conflicts}"
        )


@dataclass(frozen=True)
class Jedinica:
    """Jedna sesija koju solver raspoređuje, dužine jednog ili dva bloka."""

    indeks: int
    zahtev_indeks: int
    redni_broj: int
    trajanje: int
    korepeticija: tuple[int, ...]


@dataclass(frozen=True)
class SukobProstorije:
    """Jedna master dodela čije je prisustvo deo UNSAT jezgra soba."""

    jedinica_indeks: int
    nedelja_b: bool
    start: int
    lokacija: str


@dataclass
class PromenljiveJedinice:
    start: cp_model.IntVar
    dan: cp_model.IntVar
    blok: cp_model.IntVar
    interval: cp_model.IntervalVar
    start_b: cp_model.IntVar | None
    dan_b: cp_model.IntVar | None
    blok_b: cp_model.IntVar | None
    interval_b: cp_model.IntervalVar | None
    po_danu: tuple[cp_model.BoolVar, ...]
    po_danu_b: tuple[cp_model.BoolVar, ...] | None
    prostorije: dict[str, cp_model.BoolVar]
    prostorije_b: dict[str, cp_model.BoolVar] | None
    lokacije: dict[str, cp_model.BoolVar]
    lokacije_b: dict[str, cp_model.BoolVar] | None


KljucSkupaKandidata = tuple[str, TipProstorije, frozenset[str]]
KljucPomocnogSkupaKandidata = tuple[
    str, TipProstorije, frozenset[str], frozenset[str]
]


def _intervali_hall_podskupa(
    kljuc: KljucSkupaKandidata,
    intervali_skupova: dict[
        KljucSkupaKandidata, list[cp_model.IntervalVar]
    ],
    pomocni_intervali: dict[
        KljucPomocnogSkupaKandidata, list[cp_model.IntervalVar]
    ],
) -> list[cp_model.IntervalVar]:
    """Vrati intervale ciji je stvarni skup kandidata unutar datog skupa.

    Pomocni interval predstavlja granu jedinice koja bira obicnu salu umesto
    KM-8. Ukljucuje se samo kada njen izvorni interval nije vec ukljucen, da
    ista jedinica ne bi bila dvaput uracunata u jednom Hall ogranicenju.
    """

    lokacija, tip, podskup = kljuc
    rezultat = [
        interval
        for (druga_lokacija, drugi_tip, kandidati), stavke
        in intervali_skupova.items()
        if druga_lokacija == lokacija
        and drugi_tip is tip
        and kandidati <= podskup
        for interval in stavke
    ]
    rezultat.extend(
        interval
        for (
            druga_lokacija,
            drugi_tip,
            kandidati,
            izvorni_kandidati,
        ), stavke in pomocni_intervali.items()
        if druga_lokacija == lokacija
        and drugi_tip is tip
        and kandidati <= podskup
        and not izvorni_kandidati <= podskup
        for interval in stavke
    )
    return rezultat


def _blokiraj_nedostupne_prostorije(
    model: cp_model.CpModel,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    intervali_kapaciteta: dict[
        tuple[str, TipProstorije], list[cp_model.IntervalVar]
    ],
    intervali_skupova: dict[
        KljucSkupaKandidata, list[cp_model.IntervalVar]
    ],
) -> None:
    """Zauzmi kapacitet lokacije u terminima kada konkretna sala ne radi.

    Model lokacija ne bira sobu, pa bez ovoga vidi lokaciju kao da sve njene
    sale rade svaki dan. NP-2 radi samo sredom, pa bi master ostalim danima
    racunao dve sale umesto jedne i faza soba bi taj plan odbila.
    """

    for prostorija in prostorije:
        if not any(
            d.prostorija == prostorija.oznaka
            for d in ulaz.dostupnost_prostorija
        ):
            continue
        kljuc = (prostorija.lokacija, prostorija.tip)
        kljuc_skupa = (
            prostorija.lokacija,
            prostorija.tip,
            frozenset({prostorija.oznaka}),
        )
        for redni_dan, dan in enumerate(DANI):
            for blok in range(1, len(BLOKOVI) + 1):
                if prostorija_dostupna(
                    ulaz.dostupnost_prostorija, prostorija.oznaka, dan, (blok,)
                ):
                    continue
                interval = model.new_fixed_size_interval_var(
                    redni_dan * KORAK_DANA + blok,
                    1,
                    f"blokada_{prostorija.oznaka}_{redni_dan}_{blok}",
                )
                intervali_kapaciteta[kljuc].append(interval)
                intervali_skupova[kljuc_skupa].append(interval)


def _dodaj_hall_ogranicenja(
    model: cp_model.CpModel,
    kapaciteti: dict[tuple[str, TipProstorije], int],
    intervali_skupova: dict[
        KljucSkupaKandidata, list[cp_model.IntervalVar]
    ],
    pomocni_intervali: dict[
        KljucPomocnogSkupaKandidata, list[cp_model.IntervalVar]
    ],
) -> None:
    """Ogranicava svaki registrovani pravi podskup fizickih prostorija."""

    kljucevi = set(intervali_skupova)
    kljucevi.update(
        (lokacija, tip, kandidati)
        for lokacija, tip, kandidati, _ in pomocni_intervali
    )
    for kljuc in sorted(
        kljucevi,
        key=lambda x: (x[0], x[1].value, len(x[2]), sorted(x[2])),
    ):
        lokacija, tip, kandidati = kljuc
        if not kandidati or len(kandidati) >= kapaciteti[(lokacija, tip)]:
            # Puni fizicki skup vec pokriva globalni cumulative.
            continue
        intervali = _intervali_hall_podskupa(
            kljuc, intervali_skupova, pomocni_intervali
        )
        if len(kandidati) == 1:
            model.add_no_overlap(intervali)
        else:
            model.add_cumulative(intervali, [1] * len(intervali), len(kandidati))


@dataclass(frozen=True)
class KandidatTermina:
    """Termini jedne faze sa solverom koji čuva njihove vrednosti."""

    solver: cp_model.CpSolver
    jedinice: tuple[Jedinica, ...]
    promenljive: dict[int, PromenljiveJedinice]
    status: str
    optimizovan: bool = False


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
    # Filtriranje pre svih ranih povrataka važi i bez CSV pravila,
    # za master, puni model i obe naknadne dodele konkretnih sala.
    prostorije = tuple(
        p for p in prostorije
        if bezbedna_namena_km8(p.oznaka, zahtev.predmet)
    )
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
    dozvoli_salu_za_pevanje = zahtev.predmet == TRADICIONALNO_PEVANJE
    kandidati = tuple(
        p
        for p in prostorije
        if (
            p.tip is tip
            or (dozvoli_salu_za_pevanje and p.oznaka in SALE_TRADICIONALNOG_PEVANJA)
        )
        and p.lokacija != NARODNO_POZORISTE
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


def _dodaj_kaznu_za_subotu(
    kazne: list[cp_model.LinearExprT],
    prisutan_subotom: cp_model.BoolVar,
    tezina: int = KAZNA_ZA_SUBOTU,
) -> None:
    """Naplati svaku sesiju subotom, pa je solver uzima samo kad se isplati.

    Kazna se dodaje bez izuzetaka, i onima kojima je subota neizbežna. Glavni
    predmet sa fondom 12 ima šest dvočasa na šest različitih dana, pa mu tačno
    jedan uvek pada subotom — u svakom dopustivom rešenju. Takva kazna je
    konstantan pomeraj cilja i ne menja koje je rešenje najbolje, dok se za
    odseke sa fondom 10 (pet dvočasa, šest mogućih dana) subota stvarno plaća.
    """

    kazne.append(tezina * prisutan_subotom)


def _dodaj_subotnje_ogranicenje(
    model: cp_model.CpModel,
    kazne: list[cp_model.LinearExprT],
    blok: cp_model.IntVar,
    prisutan_subotom: cp_model.BoolVar,
    trajanje: int,
    token: str,
    sa_ciljem: bool = True,
) -> None:
    """Subotom zabrani rad posle 15:05 i snažno favorizuj kraj do 13:15."""

    kraj_bloka = blok + trajanje - 1
    model.add(kraj_bloka <= 8).only_enforce_if(prisutan_subotom)
    if not sa_ciljem:
        return
    kasno = model.new_bool_var(f"{token}_subota_posle_1315")
    model.add(kasno <= prisutan_subotom)
    # Polovična reifikacija: „kasno“ ulazi samo u kaznu sa pozitivnim
    # koeficijentom, pa je dovoljan smer koji ga podiže; minimizacija ga
    # sama spušta na nulu kad rad staje do 13,15.
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
        # Polovična reifikacija: promenljiva ulazi samo u kaznu sa pozitivnim
        # koeficijentom, pa je dovoljna implikacija naviše.
        model.add_bool_or([~prisutan_subotom, ~koristi, subotom_van_sg])
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
        model.add_bool_and([prisutan, menja_lokaciju]).only_enforce_if(posle)
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


def _dodaj_pravilo_lokacije_primenjene_gimnastike(
    model: cp_model.CpModel,
    ulaz: Ulaz,
    token: str,
    indeks_dana: int,
    stavke: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
) -> None:
    """Ako je Klasičan balet tog dana u SG, i PG mora biti u SG."""

    sufiks = "_b" if nedelja_b else ""
    primenjene = [
        jedinica for jedinica in stavke
        if ulaz.zahtevi[jedinica.zahtev_indeks].predmet == PRIMENJENA_GIMNASTIKA
    ]
    klasicni_u_sg: list[cp_model.BoolVar] = []
    for jedinica in stavke:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        if zahtev.predmet != KLASICAN_BALET:
            continue
        _, po_danu, lokacije = _promenljive_za_nedelju(
            promenljive[jedinica.indeks], nedelja_b
        )
        koristi_sg = lokacije.get(SPORTSKA_GIMNAZIJA)
        if koristi_sg is None:
            continue
        prisutan = model.new_bool_var(
            f"{token}_d{indeks_dana}_j{jedinica.indeks}_kb_sg{sufiks}"
        )
        model.add_bool_and(
            [po_danu[indeks_dana], koristi_sg]
        ).only_enforce_if(prisutan)
        model.add_bool_or(
            [~po_danu[indeks_dana], ~koristi_sg]
        ).only_enforce_if(~prisutan)
        klasicni_u_sg.append(prisutan)

    if not primenjene or not klasicni_u_sg:
        return
    ima_klasicni_u_sg = model.new_bool_var(
        f"{token}_d{indeks_dana}_ima_kb_sg{sufiks}"
    )
    model.add_max_equality(ima_klasicni_u_sg, klasicni_u_sg)
    for jedinica in primenjene:
        _, po_danu, lokacije = _promenljive_za_nedelju(
            promenljive[jedinica.indeks], nedelja_b
        )
        koristi_sg = lokacije.get(SPORTSKA_GIMNAZIJA)
        if koristi_sg is None:
            model.add(ima_klasicni_u_sg == 0).only_enforce_if(
                po_danu[indeks_dana]
            )
        else:
            model.add(koristi_sg == 1).only_enforce_if(
                [po_danu[indeks_dana], ima_klasicni_u_sg]
            )


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
    sa_ciljem: bool = True,
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
            zauzeto = sum(
                len(pomeraji)
                * _promenljive_za_nedelju(
                    promenljive[jedinica.indeks], nedelja_b
                )[1][indeks_dana]
                for jedinica, pomeraji in stavke
            )
            # Maksimum od šest angažovanih blokova je čvrsto pravilo i mora
            # ostati i u fazi izvodljivosti bez funkcije cilja.
            model.add(zauzeto <= 6)

            if sa_ciljem:
                preko_optimuma = model.new_int_var(
                    0, 2, f"o{broj_osobe}_d{indeks_dana}_preko_4{sufiks}"
                )
                # Donja granica je dovoljna: domen već daje >= 0, a kazna sa
                # pozitivnim koeficijentom spušta vrednost na
                # max(0, zauzeto - 4).
                model.add(preko_optimuma >= zauzeto - 4)
                kazne.append(250 * preko_optimuma)

            prati_pauze = (
                sa_ciljem
                or not izuzet_od_ogranicenja_pauza(osoba)
                or osoba == DUSAN_ILIJIN
            )
            if not prati_pauze:
                continue

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

            ima_pauzu: cp_model.BoolVar | None = None
            if sa_ciljem or not izuzet_od_ogranicenja_pauza(osoba):
                ima_pauzu = model.new_bool_var(
                    f"o{broj_osobe}_d{indeks_dana}_pauza{sufiks}"
                )
            duzina_pauze = model.new_int_var(
                0,
                len(BLOKOVI),
                f"o{broj_osobe}_d{indeks_dana}_duzina_pauze{sufiks}",
            )
            if ima_pauzu is not None:
                # Dovoljan je smer koji podiže indikator: duzina_pauze > 0
                # traži ima_pauzu = 1. Obrnuti smer bi bio suvišan jer
                # indikator ulazi samo u kaznu (pozitivnu) i u
                # sum(dnevne_pauze) <= 1, gde je nula uvek bar jednako dobra.
                model.add(duzina_pauze == 0).only_enforce_if(~ima_pauzu)
            model.add(duzina_pauze == poslednji - prvi + 1 - zauzeto)
            if not izuzet_od_ogranicenja_pauza(osoba) or osoba == DUSAN_ILIJIN:
                model.add(duzina_pauze <= 2)
            if ima_pauzu is not None:
                dnevne_pauze.append(ima_pauzu)
            duzine_pauza.append(duzina_pauze)
            if sa_ciljem:
                assert ima_pauzu is not None
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
    pomocni_intervali_skupova_kandidata: dict[
        KljucPomocnogSkupaKandidata, list[cp_model.IntervalVar]
    ] = defaultdict(list)
    pomocni_intervali_skupova_kandidata_b: dict[
        KljucPomocnogSkupaKandidata, list[cp_model.IntervalVar]
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
        dan = model.new_int_var(0, len(DANI) - 1, f"{prefiks}_dan")
        blok = model.new_int_var(1, len(BLOKOVI), f"{prefiks}_blok")
        model.add(start == dan * KORAK_DANA + blok)
        interval = model.new_fixed_size_interval_var(
            start, jedinica.trajanje, f"{prefiks}_i"
        )

        start_b: cp_model.IntVar | None = None
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
                dan_b = model.new_int_var(0, len(DANI) - 1, f"{prefiks}_dan_b")
                blok_b = model.new_int_var(1, len(BLOKOVI), f"{prefiks}_blok_b")
                model.add(start_b == dan_b * KORAK_DANA + blok_b)
                interval_b = model.new_fixed_size_interval_var(
                    start_b, jedinica.trajanje, f"{prefiks}_i_b"
                )
            else:
                start_b = start
                dan_b, blok_b = dan, blok
                interval_b = interval

        po_danu: list[cp_model.BoolVar] = [
            model.new_bool_var(f"{prefiks}_d{indeks_dana}")
            for indeks_dana in range(len(DANI))
        ]
        model.add_exactly_one(po_danu)
        model.add(
            dan == sum(indeks * prisutan for indeks, prisutan in enumerate(po_danu))
        )
        dozvoljena_subota = _subota_dozvoljena(zahtev, ulaz)
        if not dozvoljena_subota:
            model.add(po_danu[len(DANI) - 1] == 0)
        else:
            _dodaj_kaznu_za_subotu(kazne, po_danu[len(DANI) - 1])
            _dodaj_subotnje_ogranicenje(
                model,
                kazne,
                blok,
                po_danu[len(DANI) - 1],
                jedinica.trajanje,
                prefiks,
                sa_ciljem,
            )
        po_danu_b: tuple[cp_model.BoolVar, ...] | None = None
        if sa_nedeljom_b:
            if zahtev.smena.menja_se:
                assert dan_b is not None
                b_dani: list[cp_model.BoolVar] = [
                    model.new_bool_var(f"{prefiks}_d{indeks_dana}_b")
                    for indeks_dana in range(len(DANI))
                ]
                model.add_exactly_one(b_dani)
                model.add(
                    dan_b
                    == sum(
                        indeks * prisutan_b
                        for indeks, prisutan_b in enumerate(b_dani)
                    )
                )
                po_danu_b = tuple(b_dani)
                if not dozvoljena_subota:
                    model.add(b_dani[len(DANI) - 1] == 0)
                else:
                    # Nedelja B je zaseban termin, pa se i njena subota plaća.
                    _dodaj_kaznu_za_subotu(kazne, b_dani[len(DANI) - 1])
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
                interval_lokacije = model.new_optional_fixed_size_interval_var(
                    start,
                    jedinica.trajanje,
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
                if lokacija == "Народно позориште":
                    np_izbori[zahtev.odeljenja[0]].append(koristi)
                    if jedinica.trajanje != 2:
                        model.add(koristi == 0)
                    else:
                        model.add(blok == 10).only_enforce_if(koristi)
                if sa_nedeljom_b:
                    assert start_b is not None
                    assert lokacije_b is not None
                    if zahtev.smena.menja_se:
                        koristi_b = model.new_bool_var(
                            f"{prefiks}_lok_{broj_lokacije}_b"
                        )
                        interval_b_lokacije = (
                            model.new_optional_fixed_size_interval_var(
                                start_b,
                                jedinica.trajanje,
                                koristi_b,
                                f"{prefiks}_lok_{broj_lokacije}_i_b",
                            )
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
            if prostorija.lokacija == NARODNO_POZORISTE:
                np_izbori[zahtev.odeljenja[0]].append(koristi)
                if jedinica.trajanje != 2:
                    model.add(koristi == 0)
                else:
                    model.add(blok == 10).only_enforce_if(koristi)
            _ogranici_dostupnost_prostorije(
                model, koristi, start, dozvoljeni, ulaz,
                prostorija.oznaka, jedinica.trajanje,
            )
            opcion = model.new_optional_fixed_size_interval_var(
                start, jedinica.trajanje, koristi,
                f"{prefiks}_{prostorija.oznaka}_i",
            )
            intervali_prostorija[prostorija.oznaka].append(opcion)
            if sa_nedeljom_b:
                assert start_b is not None
                assert izbor_prostorije_b is not None
                if zahtev.smena.menja_se:
                    koristi_b = model.new_bool_var(
                        f"{prefiks}_{prostorija.oznaka}_b"
                    )
                    opcion_b = model.new_optional_fixed_size_interval_var(
                        start_b, jedinica.trajanje, koristi_b,
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

        if dozvoljena_subota and sa_ciljem:
            _dodaj_subotnji_prioritet_sg(
                model,
                kazne,
                po_danu[len(DANI) - 1],
                lokacije,
                prefiks,
            )

        promenljive[jedinica.indeks] = PromenljiveJedinice(
            start=start,
            dan=dan,
            blok=blok,
            interval=interval,
            start_b=start_b,
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
                intervali_korepetitora[resurs].append(
                    model.new_fixed_size_interval_var(
                        start + pomeraj, 1, f"{prefiks}_kor_{pomeraj}_i",
                    )
                )
                if sa_nedeljom_b:
                    assert start_b is not None
                    intervali_korepetitora_b[resurs].append(
                        model.new_fixed_size_interval_var(
                            start_b + pomeraj,
                            1,
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
    if samo_lokacije:
        _blokiraj_nedostupne_prostorije(
            model, ulaz, prostorije,
            intervali_kapaciteta, intervali_skupova_kandidata,
        )
        if sa_nedeljom_b:
            _blokiraj_nedostupne_prostorije(
                model, ulaz, prostorije,
                intervali_kapaciteta_b, intervali_skupova_kandidata_b,
            )
    for kljuc, intervali in intervali_kapaciteta.items():
        model.add_cumulative(intervali, [1] * len(intervali), kapaciteti[kljuc])
    _dodaj_hall_ogranicenja(
        model,
        kapaciteti,
        intervali_skupova_kandidata,
        pomocni_intervali_skupova_kandidata,
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
        _dodaj_hall_ogranicenja(
            model,
            kapaciteti,
            intervali_skupova_kandidata_b,
            pomocni_intervali_skupova_kandidata_b,
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
            _dodaj_pravilo_lokacije_primenjene_gimnastike(
                model, ulaz, token, indeks_dana, stavke, promenljive
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
                _dodaj_pravilo_lokacije_primenjene_gimnastike(
                    model,
                    ulaz,
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
        model, kazne, ulaz, jedinice, promenljive, sa_ciljem=sa_ciljem
    )
    if sa_nedeljom_b:
        _dodaj_kontinuitet_osoba(
            model,
            kazne,
            ulaz,
            jedinice,
            promenljive,
            nedelja_b=True,
            sa_ciljem=sa_ciljem,
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
            prostorija=kanonska_prostorija(
                nadji(c.prostorija, oznake_prostorija)
            ),
            red=c.red,
        )
        for c in hintovi
    )


def _upari_hintove(
    ulaz: Ulaz,
    jedinice_zahteva: dict[int, list[Jedinica]],
    hintovi: Sequence[Cas],
) -> dict[int, tuple[int, int, str]]:
    """Za svaku jedinicu nađi (dan, blok, prostoriju) prethodnog rasporeda.

    Redovi CSV-a se uparuju sa jedinicama istog zahteva tako da se poklope
    trajanje i obrazac korepeticije. Jedinice bez para se preskaču, pa se
    izmenjeni deo ulaza jednostavno ostavlja solveru.
    """

    po_kljucu: dict[tuple[str, str, tuple[str, ...]], list[Cas]] = defaultdict(list)
    for cas in hintovi:
        po_kljucu[(cas.predmet, cas.nastavnik, tuple(cas.odeljenja))].append(cas)

    rezultat: dict[int, tuple[int, int, str]] = {}
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
                            and kanonska_prostorija(redovi[i].prostorija)
                            == kanonska_prostorija(prvi.prostorija)
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
            rezultat[jedinica.indeks] = (
                DANI.index(cas.dan), cas.blok, cas.prostorija
            )
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
    if not hintovi and not hintovi_b:
        return {}
    for nedelja_b, casovi in ((False, hintovi), (True, hintovi_b)):
        if not casovi:
            continue
        # Dijagnostika mora videti izvorne sporne sobe, ali u model ne
        # unosimo ni njihove termine. Zato filtriramo tek na ovom ulazu.
        bezbedni = tuple(
            c for c in casovi
            if bezbedna_namena_km8(c.prostorija, c.predmet)
        )
        upareno = _upari_hintove(
            ulaz, jedinice_zahteva, _kanonizuj_hintove(ulaz, bezbedni, prostorije)
        )
        for indeks, (dan, blok, _prostorija) in upareno.items():
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
    pocetno_slobodne: Iterable[int] = (),
) -> list[set[int]]:
    """Skupovi jedinica koje se redom oslobađaju kad fiksirani hint ne prolazi.

    Nivo 0 oslobađa samo jedinice bez hinta (izmenjeni ili novi zahtevi,
    termini van domena). Svaki sledeći nivo dodaje sve jedinice koje sa već
    slobodnima dele nastavnika, korepetitora ili odeljenje.
    """

    slobodne = {j.indeks for j in jedinice if j.indeks not in hintovi_jedinica}
    slobodne.update(pocetno_slobodne)
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
    status_out: list[cp_model.CpSolverStatus] | None = None,
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
            if status_out is not None:
                status_out.append(cp_model.INFEASIBLE)
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
    if status_out is not None:
        status_out.append(status)
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


def _ponovo_dokazi_veliko_jezgro_soba(
    model: cp_model.CpModel,
    jezgro: Sequence[int],
    mapirani_literali: Collection[int],
    preostalo_vreme: float,
    broj_radnika: int,
) -> list[int]:
    """Bez cilja ponovo dokaži veliko jezgro i vrati ga samo ako je mapirano."""

    originalno = list(jezgro)
    if (
        len(originalno) <= PRAG_VELIKOG_JEZGRA_SOBA
        or preostalo_vreme < MIN_BUDZET_PONOVNOG_DOKAZA_SOBA
    ):
        return originalno

    model.clear_objective()
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = min(
        MAX_BUDZET_PONOVNOG_DOKAZA_SOBA, preostalo_vreme
    )
    solver.parameters.num_search_workers = broj_radnika
    status = solver.solve(model)
    if status != cp_model.INFEASIBLE:
        print(
            "ROOM CORE — objective-free re-proof nije dokazao INFEASIBLE "
            f"({_status_tekst(status)}); zadržavam originalno jezgro"
        )
        return originalno

    novo = list(solver.sufficient_assumptions_for_infeasibility())
    mapirani = set(mapirani_literali)
    if not novo or any(
        (literal if literal >= 0 else -literal - 1) not in mapirani
        for literal in novo
    ):
        print(
            "ROOM CORE — objective-free re-proof vratio je nepotpuno "
            "mapirano jezgro; zadržavam originalno jezgro"
        )
        return originalno
    print(f"ROOM CORE — objective-free re-proof: {len(originalno)} -> {len(novo)}")
    return novo


def _dodeli_prostorije_obe(
    solver_termina: cp_model.CpSolver,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    vremensko_ogranicenje: float = 60,
    broj_radnika: int = 8,
    status_out: list[cp_model.CpSolverStatus] | None = None,
    sukob_out: list[SukobProstorije] | None = None,
) -> tuple[dict[int, str], dict[int, str]] | None:
    """Zajedno dodeli prostorije za A i B uz iste sobe stalnih smena."""

    model = cp_model.CpModel()
    izbori_a: dict[int, dict[str, cp_model.BoolVar]] = {}
    izbori_b: dict[int, dict[str, cp_model.BoolVar]] = {}
    intervali_a: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    intervali_b: dict[str, list[cp_model.IntervalVar]] = defaultdict(list)
    kazne: list[cp_model.LinearExprT] = []
    pretpostavke: dict[int, SukobProstorije] = {}

    def obavezna_dodela(
        jedinica: Jedinica,
        nedelja_b: bool,
        start: int,
        lokacija: str,
        izbori: dict[str, cp_model.BoolVar],
    ) -> cp_model.BoolVar:
        oznaka_nedelje = "b" if nedelja_b else "a"
        aktivna = model.new_bool_var(
            f"j{jedinica.indeks}_aktivna_{oznaka_nedelje}"
        )
        # Gašenje pretpostavke zaista uklanja jedinicu iz room problema. To je
        # važno da jezgro bude dovoljan, a ne samo dijagnostički skup.
        model.add(sum(izbori.values()) == 1).only_enforce_if(aktivna)
        for koristi in izbori.values():
            model.add(koristi == 0).only_enforce_if(aktivna.negated())
        model.add_assumption(aktivna)
        pretpostavke[aktivna.index] = SukobProstorije(
            jedinica.indeks, nedelja_b, start, lokacija
        )
        return aktivna

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
            intervali_a[soba.oznaka].append(model.new_optional_fixed_size_interval_var(
                start_a, jedinica.trajanje, koristi,
                f"j{jedinica.indeks}_{soba.oznaka}_i_a",
            ))
        aktivna_a = obavezna_dodela(
            jedinica, False, start_a, lokacija_a, izbori_a[jedinica.indeks]
        )
        for soba in moguce_b:
            koristi = model.new_bool_var(f"j{jedinica.indeks}_{soba.oznaka}_b")
            izbori_b[jedinica.indeks][soba.oznaka] = koristi
            kazna = _kazna_strukturisanih_pravila(
                ulaz, zahtev, soba.oznaka, jedinica.trajanje
            )
            if kazna:
                kazne.append(kazna * koristi)
            intervali_b[soba.oznaka].append(model.new_optional_fixed_size_interval_var(
                start_b, jedinica.trajanje, koristi,
                f"j{jedinica.indeks}_{soba.oznaka}_i_b",
            ))
        aktivna_b = obavezna_dodela(
            jedinica, True, start_b, lokacija_b, izbori_b[jedinica.indeks]
        )
        if not zahtev.smena.menja_se:
            sve_sobe = set(izbori_a[jedinica.indeks]) | set(
                izbori_b[jedinica.indeks]
            )
            for oznaka in sve_sobe:
                model.add(
                    izbori_a[jedinica.indeks].get(oznaka, 0)
                    == izbori_b[jedinica.indeks].get(oznaka, 0)
                ).only_enforce_if((aktivna_a, aktivna_b))
    for stavke in intervali_a.values():
        model.add_no_overlap(stavke)
    for stavke in intervali_b.values():
        model.add_no_overlap(stavke)
    if kazne:
        model.minimize(sum(kazne))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    solver.parameters.num_search_workers = broj_radnika
    pocetak_resavanja = time.monotonic()
    status = solver.solve(model)
    if status_out is not None:
        status_out.append(status)
    if status == cp_model.INFEASIBLE and sukob_out is not None:
        jezgro = _ponovo_dokazi_veliko_jezgro_soba(
            model,
            solver.sufficient_assumptions_for_infeasibility(),
            pretpostavke,
            vremensko_ogranicenje - (time.monotonic() - pocetak_resavanja),
            broj_radnika,
        )
        for literal in jezgro:
            indeks = literal if literal >= 0 else -literal - 1
            if indeks in pretpostavke:
                sukob_out.append(pretpostavke[indeks])
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    def izvuci(izbori: dict[int, dict[str, cp_model.BoolVar]]) -> dict[int, str]:
        return {
            indeks: next(o for o, x in po_sobi.items() if solver.boolean_value(x))
            for indeks, po_sobi in izbori.items()
        }

    return izvuci(izbori_a), izvuci(izbori_b)


def _resi_sa_fiksiranim_terminima(
    solver_termina: cp_model.CpSolver,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    jutarnja_smena: Smena,
    promenljive_mastera: dict[int, PromenljiveJedinice],
    sa_nedeljom_b: bool,
    vremensko_ogranicenje: float,
    broj_radnika: int,
    seme: int,
    slobodne_jedinice: frozenset[int] = frozenset(),
) -> tuple[
    cp_model.CpSolver,
    tuple[Jedinica, ...],
    dict[int, PromenljiveJedinice],
    cp_model.CpSolverStatus,
]:
    """Zadrzi termine iz mastera, a pusti lokacije i sobe da se biraju ponovo.

    Master bira lokacije ne znajuci koja sala u njima moze da primi cas, pa
    tacna dodela soba ume da padne i kad su termini sasvim dobri. Pun model sa
    zakucanim terminima resava tu istu dodelu bez ogranicenja na lokaciju i uz
    sva pravila o kretanju izmedju zgrada.

    `slobodne_jedinice` ostaju bez zakucanog termina. Kada ni isti termini ne
    prolaze, pusta se samo sacica casova iz UNSAT jezgra soba; to je mnogo
    jeftinije od novog master solvea, a popravlja bas ono sto je zapelo.
    """

    model, jedinice, promenljive = napravi_model(
        ulaz, prostorije, nedostupnosti, jutarnja_smena,
        sa_nedeljom_b=sa_nedeljom_b, samo_lokacije=False, sa_ciljem=False,
    )
    for jedinica in jedinice:
        if jedinica.indeks in slobodne_jedinice:
            continue
        master = promenljive_mastera[jedinica.indeks]
        nova = promenljive[jedinica.indeks]
        model.add(nova.start == solver_termina.value(master.start))
        if nova.start_b is not None and master.start_b is not None:
            model.add(nova.start_b == solver_termina.value(master.start_b))
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = broj_radnika
    solver.parameters.random_seed = seme
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    return solver, jedinice, promenljive, solver.solve(model)


def _jedinice_oko_jezgra(
    solver_lokacija: cp_model.CpSolver,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    sukob: Sequence[SukobProstorije],
) -> frozenset[int]:
    """Sve jedinice koje master drzi na istoj lokaciji istog dana kao jezgro.

    Pustiti samo jezgro obicno nije dovoljno: casovi oko njega drze sale
    zauzete, pa se sudar samo pomeri. Ovaj skup je i dalje jedan dan jedne
    zgrade, dakle mali deo rasporeda.
    """

    dani_jezgra = {
        (stavka.lokacija, stavka.start // KORAK_DANA) for stavka in sukob
    }
    slobodne: set[int] = set()
    for jedinica in jedinice:
        p = promenljive[jedinica.indeks]
        parovi = [(p.start, p.lokacije)]
        if p.start_b is not None and p.lokacije_b is not None:
            parovi.append((p.start_b, p.lokacije_b))
        for start, lokacije in parovi:
            lokacija = next(
                (
                    naziv for naziv, koristi in lokacije.items()
                    if solver_lokacija.boolean_value(koristi)
                ),
                None,
            )
            if lokacija is None:
                continue
            if (lokacija, solver_lokacija.value(start) // KORAK_DANA) in dani_jezgra:
                slobodne.add(jedinica.indeks)
                break
    return frozenset(slobodne)


def _ispisi_sukob_soba(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice: Sequence[Jedinica],
    sukob: Sequence[SukobProstorije],
) -> None:
    """Ispisi sta cini room UNSAT jezgro, da se uzrok vidi iz loga."""

    po_indeksu = {j.indeks: j for j in jedinice}
    for stavka in sorted(
        sukob, key=lambda s: (s.lokacija, s.start, s.jedinica_indeks)
    ):
        jedinica = po_indeksu.get(stavka.jedinica_indeks)
        if jedinica is None:
            continue
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        kandidati = sorted(
            p.oznaka
            for p in _moguce_prostorije(
                zahtev, ulaz, prostorije, jedinica.trajanje
            )
            if p.lokacija == stavka.lokacija
        )
        dan = DANI[stavka.start // KORAK_DANA]
        blok = stavka.start % KORAK_DANA
        nedelja = "B" if stavka.nedelja_b else "A"
        print(
            f"  JEZGRO {nedelja} {dan} blok {blok} (x{jedinica.trajanje}) "
            f"{zahtev.predmet} [{','.join(zahtev.odeljenja)}] "
            f"-> {stavka.lokacija} medju {{{', '.join(kandidati)}}}"
        )


def _vrednosti_hladnog_mastera(
    solver: cp_model.CpSolver,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
) -> tuple[list[cp_model.IntVar], list[int]]:
    """Izvuci jednu kompletnu, deduplikovanu dodelu termina i lokacija A/B."""

    varijable: list[cp_model.IntVar] = []
    vrednosti: list[int] = []
    vidjene: set[int] = set()

    def dodaj(varijabla: cp_model.IntVar | None) -> None:
        if varijabla is None or varijabla.index in vidjene:
            return
        vidjene.add(varijabla.index)
        varijable.append(varijabla)
        vrednosti.append(solver.value(varijabla))

    for jedinica in jedinice:
        p = promenljive[jedinica.indeks]
        dodaj(p.start)
        for koristi in p.lokacije.values():
            dodaj(koristi)
        dodaj(p.start_b)
        for koristi in (p.lokacije_b or {}).values():
            dodaj(koristi)
    return varijable, vrednosti


def _zabrani_i_hintuj_master_dodelu(
    model: cp_model.CpModel,
    varijable: Sequence[cp_model.IntVar],
    vrednosti: Sequence[int],
) -> None:
    """Zabrani baš ovu kombinaciju, ali je iskoristi kao smernicu za susednu."""

    model.add_forbidden_assignments(varijable, [vrednosti])
    model.clear_hints()
    for varijabla, vrednost in zip(varijable, vrednosti, strict=True):
        model.add_hint(varijabla, vrednost)


def _zabrani_sukob_i_hintuj_master_dodelu(
    model: cp_model.CpModel,
    promenljive: dict[int, PromenljiveJedinice],
    sukob: Sequence[SukobProstorije],
    hint_varijable: Sequence[cp_model.IntVar],
    hint_vrednosti: Sequence[int],
) -> int:
    """Dodaj no-good samo za start+lokaciju iz room UNSAT jezgra."""

    varijable: list[cp_model.IntVar] = []
    vrednosti: list[int] = []
    vidjene: dict[int, int] = {}

    def dodaj(varijabla: cp_model.IntVar, vrednost: int) -> None:
        prethodna = vidjene.get(varijabla.index)
        if prethodna is not None:
            if prethodna != vrednost:
                raise ValueError("UNSAT jezgro sadrži protivrečne vrednosti master varijable")
            return
        vidjene[varijabla.index] = vrednost
        varijable.append(varijabla)
        vrednosti.append(vrednost)

    for stavka in sukob:
        p = promenljive[stavka.jedinica_indeks]
        start = p.start_b if stavka.nedelja_b else p.start
        lokacije = p.lokacije_b if stavka.nedelja_b else p.lokacije
        assert start is not None and lokacije is not None
        dodaj(start, stavka.start)
        dodaj(lokacije[stavka.lokacija], 1)

    if not varijable:
        return 0
    model.add_forbidden_assignments(varijable, [vrednosti])
    model.clear_hints()
    for varijabla, vrednost in zip(hint_varijable, hint_vrednosti, strict=True):
        model.add_hint(varijabla, vrednost)
    return len(varijable)


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


def _analiziraj_prostorije_hintova(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    jedinice_zahteva: dict[int, list[Jedinica]],
    hintovi: Sequence[Cas],
    hintovi_b: Sequence[Cas],
) -> tuple[set[int], int]:
    """Nađi jedinice čiji stari termin zahteva promenu lokacije.

    Promena konkretne sobe na istoj lokaciji ne oslobađa termin: strogi model
    će izabrati drugu hard-dozvoljenu i vremenski dostupnu sobu. Problem samo
    u jednoj nedelji oslobađa celu jedinicu, odnosno oba njena termina.
    """

    po_indeksu = {
        jedinica.indeks: jedinica
        for jedinice in jedinice_zahteva.values()
        for jedinica in jedinice
    }
    po_oznaci = {
        kanonska_prostorija(prostorija.oznaka): prostorija
        for prostorija in prostorije
    }
    slobodne: set[int] = set()
    transformisane_sobe: set[int] = set()
    for casovi in (hintovi, hintovi_b):
        if not casovi:
            continue
        upareno = _upari_hintove(
            ulaz,
            jedinice_zahteva,
            _kanonizuj_hintove(ulaz, casovi, prostorije),
        )
        for indeks, (dan, blok, stara_oznaka) in upareno.items():
            jedinica = po_indeksu[indeks]
            zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
            stara = po_oznaci.get(kanonska_prostorija(stara_oznaka))
            if stara is None:
                slobodne.add(indeks)
                continue
            dostupne = [
                kandidat
                for kandidat in _moguce_prostorije(
                    zahtev, ulaz, prostorije, jedinica.trajanje
                )
                if prostorija_dostupna(
                    ulaz.dostupnost_prostorija,
                    kandidat.oznaka,
                    DANI[dan],
                    range(blok, blok + jedinica.trajanje),
                )
            ]
            stara_kanonska = kanonska_prostorija(stara.oznaka)
            if any(
                kanonska_prostorija(kandidat.oznaka) == stara_kanonska
                for kandidat in dostupne
            ):
                continue
            if any(kandidat.lokacija == stara.lokacija for kandidat in dostupne):
                transformisane_sobe.add(indeks)
            else:
                slobodne.add(indeks)
    return slobodne, len(transformisane_sobe - slobodne)


def _broj_nevazecih_dodela_prostorija(
    analiza: tuple[set[int], int],
) -> int:
    """Saberi jedinice koje menjaju sobu ili celu lokaciju bez dupliranja."""

    promene_lokacije, promene_sobe = analiza
    return len(promene_lokacije) + promene_sobe


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
    oznaka_faze: str = "FAZA 1",
    analiza_prostorija: tuple[set[int], int] | None = None,
) -> cp_model.CpSolverStatus:
    """Pokušaj prethodni raspored kao fiksiran, sve labavije oko izmena."""

    jedinice_zahteva: dict[int, list[Jedinica]] = defaultdict(list)
    for jedinica in jedinice:
        jedinice_zahteva[jedinica.zahtev_indeks].append(jedinica)
    pripremljeni = _pripremi_hintove(
        ulaz, prostorije, jedinice_zahteva, promenljive, hintovi, hintovi_b
    )
    if not pripremljeni:
        print(
            f"{oznaka_faze} — hint se ne poklapa ni sa jednom jedinicom; "
            "tražim novo rešenje"
        )
        return cp_model.UNKNOWN

    if analiza_prostorija is None:
        analiza_prostorija = _analiziraj_prostorije_hintova(
            ulaz, prostorije, jedinice_zahteva, hintovi, hintovi_b
        )
        pocetno_slobodne, transformisane_sobe = analiza_prostorija
        print(
            f"HINT: {transformisane_sobe} неважећих соба мења се унутар исте "
            f"локације; {len(pocetno_slobodne)} јединица мора да промени "
            "локацију."
        )
    else:
        pocetno_slobodne, _ = analiza_prostorija

    model.clear_hints()
    cuvari: dict[int, cp_model.BoolVar] = {}
    for indeks, parovi in pripremljeni.items():
        cuvar = model.new_bool_var(f"hint_j{indeks}")
        cuvari[indeks] = cuvar
        vidjene_promenljive: set[int] = set()
        for promenljiva, vrednost in parovi:
            # Start jednoznačno određuje dan i blok; jedna reifikovana
            # jednakost po nedelji pravi znatno manji assumption model.
            if not promenljiva.name.endswith(("_start", "_start_b")):
                continue
            if promenljiva.index in vidjene_promenljive:
                continue
            model.add(promenljiva == vrednost).only_enforce_if(cuvar)
            vidjene_promenljive.add(promenljiva.index)

    slobodne = _nivoi_oslobadjanja(
        ulaz, jedinice, pripremljeni, najvise_nivoa=0,
        pocetno_slobodne=pocetno_slobodne,
    )[0]
    status = cp_model.UNKNOWN
    for pokusaj in range(3):
        aktivni = {
            indeks: cuvar for indeks, cuvar in cuvari.items()
            if indeks not in slobodne
        }
        if not aktivni:
            break
        model.clear_assumptions()
        model.add_assumptions(aktivni.values())
        preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
        if preostalo <= 0:
            break
        solver.parameters.max_time_in_seconds = min(LIMIT_FIKSIRANOG_HINTA, preostalo)
        korak = time.monotonic()
        status = solver.solve(model)
        trajanje = time.monotonic() - korak
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(
                f"{oznaka_faze} — prethodni raspored prolazi uz "
                f"{len(slobodne)} oslobođenih jedinica "
                f"(core покушај {pokusaj}, {trajanje:.3f} s)"
            )
            break
        if status != cp_model.INFEASIBLE:
            print(
                f"{oznaka_faze} — core покушај {pokusaj} "
                f"({len(aktivni)} fiksiranih) nije dao jezgro: "
                f"{_status_tekst(status)}, {trajanje:.3f} s"
            )
            break
        jezgro_literala = set(solver.sufficient_assumptions_for_infeasibility())
        po_literalu = {cuvar.index: indeks for indeks, cuvar in aktivni.items()}
        jezgro = {
            po_literalu[literal]
            for literal in jezgro_literala
            if literal in po_literalu
        }
        pre = len(slobodne)
        slobodne.update(jezgro)
        print(
            f"{oznaka_faze} — core покушај {pokusaj}: INFEASIBLE за "
            f"{trajanje:.3f} s; језгро {len(jezgro)}, "
            f"укупно слободних {len(slobodne)}."
        )
        if len(slobodne) == pre:
            break
    model.clear_assumptions()
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _primeni_hintove(model, pripremljeni)
        print(
            f"{oznaka_faze} — prethodni raspored nije upotrebljiv kao "
            "fiksirani hint; tražim novo rešenje"
        )
    return status


def _prenesi_resenje_kao_hint(
    model: cp_model.CpModel,
    solver: cp_model.CpSolver,
    jedinice: Sequence[Jedinica],
    prethodne: dict[int, PromenljiveJedinice],
    sledece: dict[int, PromenljiveJedinice],
) -> None:
    """Zameni postojeće hintove nedupliranim rešenjem prethodnog modela."""

    model.clear_hints()
    hintovani_indeksi: set[int] = set()

    def prenesi(prethodna: cp_model.IntVar, sledeca: cp_model.IntVar) -> None:
        if sledeca.index in hintovani_indeksi:
            return
        model.add_hint(sledeca, solver.value(prethodna))
        hintovani_indeksi.add(sledeca.index)

    for jedinica in jedinice:
        p1 = prethodne[jedinica.indeks]
        p2 = sledece[jedinica.indeks]
        for prethodna, sledeca in (
            (p1.start, p2.start), (p1.dan, p2.dan), (p1.blok, p2.blok),
        ):
            prenesi(prethodna, sledeca)
        for lokacija in set(p1.lokacije) & set(p2.lokacije):
            prenesi(p1.lokacije[lokacija], p2.lokacije[lokacija])
        for prostorija in set(p1.prostorije) & set(p2.prostorije):
            prenesi(p1.prostorije[prostorija], p2.prostorije[prostorija])
        if p1.start_b is not None and p2.start_b is not None:
            for prethodna, sledeca in (
                (p1.start_b, p2.start_b),
                (p1.dan_b, p2.dan_b),
                (p1.blok_b, p2.blok_b),
            ):
                assert prethodna is not None and sledeca is not None
                prenesi(prethodna, sledeca)
        if p1.lokacije_b is not None and p2.lokacije_b is not None:
            for lokacija in set(p1.lokacije_b) & set(p2.lokacije_b):
                prenesi(p1.lokacije_b[lokacija], p2.lokacije_b[lokacija])
        if p1.prostorije_b is not None and p2.prostorije_b is not None:
            for prostorija in set(p1.prostorije_b) & set(p2.prostorije_b):
                prenesi(
                    p1.prostorije_b[prostorija], p2.prostorije_b[prostorija]
                )


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
    dict[int, str] | None,
    dict[int, str] | None,
]:
    """Nađi lokacije, zatim konkretne sobe, pa optimizuj strogi model."""

    pocetak = time.monotonic()
    rok_sa_rezervom = max(60.0, vremensko_ogranicenje - 300.0)
    rok_pripreme = min(rok_sa_rezervom, vremensko_ogranicenje)

    # Odluka o hladnom startu donosi se pre gradnje i rešavanja pripremnog
    # modela. Tako masovno zastareo hint ne troši budžet stroge faze.
    analiza_hinta: tuple[set[int], int] | None = None
    koristi_pripremu = bool(hintovi or hintovi_b)
    if koristi_pripremu:
        jedinice_za_analizu = _jedinice(ulaz)
        jedinice_zahteva: dict[int, list[Jedinica]] = defaultdict(list)
        for jedinica in jedinice_za_analizu:
            jedinice_zahteva[jedinica.zahtev_indeks].append(jedinica)
        analiza_hinta = _analiziraj_prostorije_hintova(
            ulaz, prostorije, jedinice_zahteva, hintovi, hintovi_b
        )
        promene_lokacije, promene_sobe = analiza_hinta
        broj_nevazecih = _broj_nevazecih_dodela_prostorija(analiza_hinta)
        print(
            f"HINT: {promene_sobe} неважећих соба мења се унутар исте "
            f"локације; {len(promene_lokacije)} јединица мора да промени "
            "локацију."
        )
        if broj_nevazecih > PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA:
            koristi_pripremu = False
            print(
                f"HINT: {broj_nevazecih} неважећих додела прелази праг "
                f"{PRAG_HLADNOG_STARTA_NEVAZECIH_SOBA}; одбацујем hint и "
                "покрећем хладни локацијски master."
            )

    model_pripreme = None
    jedinice_pripreme: tuple[Jedinica, ...] = ()
    promenljive_pripreme: dict[int, PromenljiveJedinice] = {}
    if koristi_pripremu:
        model_pripreme, jedinice_pripreme, promenljive_pripreme = napravi_model(
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
    else:
        print("PRIPREMA — прескочена; хладни локацијски master добија буџет")
        # Bez upotrebljivog prethodnog rasporeda puni model konkretnih soba je
        # nepotrebno tezak. Jedan neprekinut master solve bira termine i
        # lokacije, a mali egzaktni model u rezervisanom vremenu bira sobe.
        model_lokacija, jedinice_lokacija, promenljive_lokacija = napravi_model(
            ulaz,
            prostorije,
            nedostupnosti,
            jutarnja_smena,
            sa_nedeljom_b=sa_nedeljom_b,
            samo_lokacije=True,
            sa_ciljem=False,
        )
        greska_modela = model_lokacija.validate()
        if greska_modela:
            raise RuntimeError(f"Неисправан модел локација: {greska_modela}")

        minimalni_budzet = min(
            MINIMALNI_BUDZET_HLADNOG_POKUSAJA,
            max(0.1, vremensko_ogranicenje / 10),
        )
        for pokusaj in range(1, NAJVISE_HLADNIH_MASTER_POKUSAJA + 1):
            preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
            rezerva = min(
                REZERVA_ZA_DODELU_PROSTORIJA + REZERVA_ZA_ISTE_TERMINE,
                max(0.0, preostalo / 2),
            )
            limit_lokacija = max(0.0, preostalo - rezerva)
            if limit_lokacija < minimalni_budzet:
                print(
                    f"HLADNI POKUŠAJ {pokusaj} — nema dovoljno vremena za "
                    "novi master i sobe"
                )
                break

            solver_lokacija = cp_model.CpSolver()
            solver_lokacija.parameters.num_search_workers = broj_radnika
            solver_lokacija.parameters.random_seed = seme
            # Isti nalaz kao u fazi 1, izmeren posebno na ovom modelu:
            # 4 radnika, pun master A+B, seme 1 — 875 s podrazumevano prema
            # 352 s sa nivoom 3; seme 2 — 576 s prema 256 s.
            solver_lokacija.parameters.symmetry_level = 3
            solver_lokacija.parameters.max_time_in_seconds = limit_lokacija
            if pokusaj > 1:
                solver_lokacija.parameters.repair_hint = True
                solver_lokacija.parameters.hint_conflict_limit = (
                    LIMIT_KONFLIKATA_POPRAVKE_MASTER_HINTA
                )
            pocetak_lokacija = time.monotonic()
            status_lokacija = solver_lokacija.solve(model_lokacija)
            trajanje_lokacija = time.monotonic() - pocetak_lokacija
            print(
                f"HLADNI POKUŠAJ {pokusaj} — master "
                f"{_status_tekst(status_lokacija)}, {trajanje_lokacija:.3f} s"
            )
            if status_lokacija not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                status = _status_tekst(status_lokacija)
                print(f"FAZA 1 — neuspeh/timeout: {status}")
                print("FAZA 2 — dodela konkretnih prostorija: 0.000 s")
                return (
                    None, jedinice_lokacija, promenljive_lokacija,
                    f"neuspeh/timeout (lokacijski master): {status}", None, None,
                )

            preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
            if preostalo <= 0:
                break
            limit_soba = min(REZERVA_ZA_DODELU_PROSTORIJA, preostalo)
            pocetak_soba = time.monotonic()
            statusi_soba: list[cp_model.CpSolverStatus] = []
            sukob_soba: list[SukobProstorije] = []
            if sa_nedeljom_b:
                dodela = _dodeli_prostorije_obe(
                    solver_lokacija, ulaz, prostorije, jedinice_lokacija,
                    promenljive_lokacija, vremensko_ogranicenje=limit_soba,
                    broj_radnika=broj_radnika, status_out=statusi_soba,
                    sukob_out=sukob_soba,
                )
            else:
                dodela_a = _dodeli_prostorije(
                    solver_lokacija, ulaz, prostorije, jedinice_lokacija,
                    promenljive_lokacija, vremensko_ogranicenje=limit_soba,
                    broj_radnika=broj_radnika, status_out=statusi_soba,
                )
                dodela = (dodela_a, None) if dodela_a is not None else None
            trajanje_soba = time.monotonic() - pocetak_soba
            status_soba = (
                statusi_soba[-1] if statusi_soba
                else cp_model.FEASIBLE if dodela is not None
                else cp_model.INFEASIBLE
            )
            print(
                f"HLADNI POKUŠAJ {pokusaj} — sobe "
                f"{_status_tekst(status_soba)}, {trajanje_soba:.3f} s"
            )
            if dodela is not None:
                dodela_a, dodela_b = dodela
                print("FAZA 2 — konkretne prostorije dodeljene")
                return (
                    solver_lokacija, jedinice_lokacija, promenljive_lokacija,
                    "dopustivo (hladni lokacijski master + faza 2 dodela soba); "
                    "objective n/d",
                    dodela_a, dodela_b,
                )
            nivoi_popravke = (
                ("ISTI TERMINI", frozenset()),
                (
                    "TERMINI OSIM JEZGRA",
                    frozenset(s.jedinica_indeks for s in sukob_soba),
                ),
                (
                    "TERMINI OSIM DANA JEZGRA",
                    _jedinice_oko_jezgra(
                        solver_lokacija, jedinice_lokacija,
                        promenljive_lokacija, sukob_soba,
                    ),
                ),
            )
            vec_probano: set[frozenset[int]] = set()
            for oznaka, slobodne in nivoi_popravke:
                if slobodne in vec_probano:
                    continue
                vec_probano.add(slobodne)
                preostalo = vremensko_ogranicenje - (
                    time.monotonic() - pocetak
                )
                limit_termina = min(
                    REZERVA_ZA_ISTE_TERMINE, max(0.0, preostalo)
                )
                if limit_termina < minimalni_budzet:
                    break
                pocetak_termina = time.monotonic()
                (
                    solver_termina, jedinice_termina, promenljive_termina,
                    status_termina,
                ) = _resi_sa_fiksiranim_terminima(
                    solver_lokacija, ulaz, prostorije, nedostupnosti,
                    jutarnja_smena, promenljive_lokacija, sa_nedeljom_b,
                    limit_termina, broj_radnika, seme,
                    slobodne_jedinice=slobodne,
                )
                print(
                    f"{oznaka} {pokusaj} — "
                    f"{_status_tekst(status_termina)}, "
                    f"{time.monotonic() - pocetak_termina:.3f} s"
                )
                if status_termina in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    print("FAZA 2 — konkretne prostorije dodeljene")
                    return (
                        solver_termina, jedinice_termina, promenljive_termina,
                        "dopustivo (hladni master + popravka termina uz "
                        "slobodne sobe); objective n/d",
                        None, None,
                    )
            if status_soba != cp_model.INFEASIBLE:
                print("FAZA 2 — pretraga soba nije dokazala neizvodljivost; prekidam")
                break
            if pokusaj == NAJVISE_HLADNIH_MASTER_POKUSAJA:
                break

            preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
            if preostalo < 2 * minimalni_budzet:
                print("FAZA 2 — nema dovoljno vremena za sledeći master i sobe")
                break
            varijabile, vrednosti = _vrednosti_hladnog_mastera(
                solver_lokacija, jedinice_lokacija, promenljive_lokacija
            )
            if sukob_soba:
                _ispisi_sukob_soba(
                    ulaz, prostorije, jedinice_lokacija, sukob_soba
                )
                velicina_reza = _zabrani_sukob_i_hintuj_master_dodelu(
                    model_lokacija, promenljive_lokacija, sukob_soba,
                    varijabile, vrednosti,
                )
                print(
                    f"HLADNI POKUŠAJ {pokusaj} — room UNSAT jezgro "
                    f"{len(sukob_soba)}, rez {velicina_reza}; pokušavam "
                    "susedno rešenje"
                )
            else:
                _zabrani_i_hintuj_master_dodelu(
                    model_lokacija, varijabile, vrednosti
                )
                print(
                    f"HLADNI POKUŠAJ {pokusaj} — room UNSAT jezgro nije "
                    "dostupno; zabranjena je cela master dodela"
                )

        print("FAZA 2 — konkretne prostorije nisu dodeljene")
        return (
            None, jedinice_lokacija, promenljive_lokacija,
            "neuspeh/timeout (dodela konkretnih prostorija)", None, None,
        )
    # Svi modeli koji će se rešavati grade se pre prvog solve poziva, tako da
    # i vreme konstrukcije ulazi u isti ukupni zidni budžet.
    model_1, jedinice_1, promenljive_1 = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        jutarnja_smena,
        sa_nedeljom_b=sa_nedeljom_b,
        samo_lokacije=False,
        sa_ciljem=False,
    )
    model_2, jedinice_2, promenljive_2 = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        jutarnja_smena,
        sa_nedeljom_b=sa_nedeljom_b,
        samo_lokacije=False,
        sa_ciljem=True,
    )
    solver_pripreme: cp_model.CpSolver | None = None
    status_pripreme = cp_model.UNKNOWN
    if koristi_pripremu:
        assert model_pripreme is not None
        assert analiza_hinta is not None
        solver_pripreme = cp_model.CpSolver()
        solver_pripreme.parameters.num_search_workers = broj_radnika
        solver_pripreme.parameters.random_seed = seme
        status_pripreme = _resi_fiksiranim_hintom(
            model_pripreme, solver_pripreme, ulaz, prostorije,
            jedinice_pripreme, promenljive_pripreme,
            hintovi, hintovi_b, rok_pripreme, pocetak,
            oznaka_faze="PRIPREMA",
            analiza_prostorija=analiza_hinta,
        )
    if koristi_pripremu and status_pripreme not in (
        cp_model.OPTIMAL, cp_model.FEASIBLE
    ):
        assert model_pripreme is not None
        assert solver_pripreme is not None
        proteklo = time.monotonic() - pocetak
        limit_pripreme = _preostali_limit_prve_faze(
            rok_sa_rezervom,
            vremensko_ogranicenje,
            proteklo,
        )
        if limit_pripreme > 0:
            solver_pripreme.parameters.max_time_in_seconds = limit_pripreme
            status_pripreme = solver_pripreme.solve(model_pripreme)
    trajanje_pripreme = time.monotonic() - pocetak
    if koristi_pripremu:
        print(f"PRIPREMA — trajanje: {trajanje_pripreme:.3f} s")
    else:
        print("PRIPREMA — прескочена; цео буџет остаје строгој фази")
    priprema_uspela = status_pripreme in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    if koristi_pripremu and not priprema_uspela:
        status = _status_tekst(status_pripreme)
        print(
            f"PRIPREMA — neuspeh/timeout: {status}; "
            "FAZA 1 nastavlja bez pripremnog hinta"
        )
    elif priprema_uspela:
        print("PRIPREMA — dopustivi termini i lokacije pronađeni")

    if vremensko_ogranicenje - (time.monotonic() - pocetak) <= 0:
        print("FAZA 1 — timeout pre rešavanja strogog modela")
        print("FAZA 1 — trajanje: 0.000 s")
        print("FAZA 2 — trajanje: 0.000 s")
        return (
            None, jedinice_1, promenljive_1,
            "neuspeh/timeout (faza 1): vremensko ograničenje",
            None, None,
        )

    pocetak_prve = time.monotonic()
    if priprema_uspela:
        assert solver_pripreme is not None
        _prenesi_resenje_kao_hint(
            model_1, solver_pripreme, jedinice_pripreme,
            promenljive_pripreme, promenljive_1,
        )
    greska_modela_1 = model_1.validate()
    if greska_modela_1:
        raise RuntimeError(f"Неисправан модел фазе 1: {greska_modela_1}")

    solver_1 = cp_model.CpSolver()
    solver_1.parameters.num_search_workers = broj_radnika
    solver_1.parameters.random_seed = seme
    # Model faze 1 je pun simetrija (razredi sa istim fondom časova, međusobno
    # zamenljive prostorije iste lokacije), pa podrazumevani `symmetry_level=2`
    # ne uspeva da ih iskoristi. Sa nivoom 3 CP-SAT dodatno lomi simetriju u
    # pretrazi. Mereno na 4 radnika, ograničenje 900 s, pun model A+B:
    # podrazumevano — nijedno dopustivo rešenje (seme 1, mereno jednom);
    # sa `symmetry_level=3` — rešenje za 428 s i 882 s (semena 2 i 1).
    # Varijansa je velika, pa te dve brojke treba čitati kao jedan nalaz
    # („nađe rešenje u okviru roka“), ne kao poređenje semena.
    # Namerno se menja samo faza 1 (tražena je gola dopustivost); faza 2 ima
    # svoj solver i ostaje na podrazumevanim parametrima jer za cilj nemamo
    # merenja.
    solver_1.parameters.symmetry_level = 3
    status_1 = cp_model.UNKNOWN
    if not koristi_pripremu:
        # Hladan start mora biti jedan neprekinut CP-SAT pokušaj. Prekid posle
        # 1500 s i ponovno pokretanje sa rezervom gubi celo dotadašnje stablo
        # pretrage baš kada strogi model mora da se pronađe ispočetka.
        preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
        if preostalo > 0:
            solver_1.parameters.max_time_in_seconds = preostalo
            status_1 = solver_1.solve(model_1)
    else:
        preostalo_do_rezerve = _preostali_limit_prve_faze(
            rok_sa_rezervom,
            vremensko_ogranicenje,
            time.monotonic() - pocetak,
        )
        if preostalo_do_rezerve > 0:
            solver_1.parameters.max_time_in_seconds = preostalo_do_rezerve
            status_1 = solver_1.solve(model_1)
        if status_1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
            if preostalo > 0:
                print(
                    "FAZA 1 — nema konkretnu dodelu do rezerve; "
                    "koristim rezervu za validan raspored "
                    f"({preostalo:.1f} s preostalo)"
                )
                solver_1.parameters.max_time_in_seconds = preostalo
                status_1 = solver_1.solve(model_1)
    trajanje_prve = time.monotonic() - pocetak_prve
    print(f"FAZA 1 — trajanje: {trajanje_prve:.3f} s")
    if status_1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = _status_tekst(status_1)
        print(f"FAZA 1 — neuspeh/timeout: {status}")
        print("FAZA 2 — trajanje: 0.000 s")
        return (
            None, jedinice_1, promenljive_1,
            f"neuspeh/timeout (faza 1): {status}",
            None, None,
        )
    print("FAZA 1 — dopustiv raspored sa konkretnim prostorijama pronađen")

    if vremensko_ogranicenje - (time.monotonic() - pocetak) <= 0:
        print("FAZA 2 — timeout pre početka optimizacije")
        return (
            solver_1, jedinice_1, promenljive_1,
            "dopustivo (faza 1); faza 2: timeout",
            None, None,
        )

    pocetak_druge = time.monotonic()
    _prenesi_resenje_kao_hint(
        model_2, solver_1, jedinice_1, promenljive_1, promenljive_2
    )
    greska_modela_2 = model_2.validate()
    if greska_modela_2:
        raise RuntimeError(f"Неисправан модел фазе 2: {greska_modela_2}")

    preostalo = vremensko_ogranicenje - (time.monotonic() - pocetak)
    if preostalo <= 0:
        print("FAZA 2 — timeout pre početka optimizacije")
        return (
            solver_1, jedinice_1, promenljive_1,
            "dopustivo (faza 1); faza 2: timeout",
            None, None,
        )
    solver_2 = cp_model.CpSolver()
    solver_2.parameters.max_time_in_seconds = preostalo
    solver_2.parameters.num_search_workers = broj_radnika
    solver_2.parameters.random_seed = seme
    status_2 = solver_2.solve(model_2)
    trajanje_druge = time.monotonic() - pocetak_druge
    print(f"FAZA 2 — trajanje: {max(0.0, trajanje_druge):.3f} s")
    _ispisi_zavrsnu_telemetriju_faze_2(solver_2, status_2)
    if status_2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = _status_tekst(status_2)
        print(f"FAZA 2 — optimizovano rešenje: {status}")
        return (
            solver_2, jedinice_2, promenljive_2,
            f"optimizovano (faza 2): {status}", None, None,
        )

    status = _status_tekst(status_2)
    print(f"FAZA 2 — neuspeh/timeout: {status}; koristi se dopustivo rešenje iz faze 1")
    return (
        kandidat_1,
        None,
        f"dopustivo (faza 1); faza 2 neuspeh/timeout: {status}",
        None,
        None,
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

    solver, jedinice, promenljive, status_tekst, sobe_a, _ = _resi_u_dve_faze(
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

    casovi = _izvuci_casove(
        solver, ulaz, jedinice, promenljive, dodeljene_prostorije=sobe_a
    )
    izvestaj = proveri(ulaz, prostorije, nedostupnosti, casovi, jutarnja_smena)
    if not izvestaj.ispravan:
        return Rezultat(
            f"{status_tekst}; hard validacija nije prošla", (), izvestaj, None
        )
    cilj = solver.objective_value if "faza 2" in status_tekst and "optimizovano" in status_tekst else None
    return Rezultat(status_tekst, casovi, izvestaj, cilj)


def replace_red(cas: Cas, red: int) -> Cas:
    """Napravi isti čas sa brojem reda koji će imati u izlaznom CSV-u."""

    return replace(cas, red=red)


KandidatPara = tuple[str, Rezultat, Rezultat]


def _validan_kandidat_para(kandidat: KandidatPara | None) -> bool:
    """Kandidat je prihvatljiv samo ako su obe nedelje potpune i bez grešaka."""

    if kandidat is None:
        return False
    _, rezultat_a, rezultat_b = kandidat
    return (
        rezultat_a.pronadjen
        and rezultat_b.pronadjen
        and rezultat_a.izvestaj is not None
        and rezultat_b.izvestaj is not None
        and rezultat_a.izvestaj.ispravan
        and rezultat_b.izvestaj.ispravan
    )


def _izaberi_najbolji_kandidat(
    kandidati: Sequence[KandidatPara],
) -> KandidatPara | None:
    """Izaberi najmanje upozorenja; pri istom zbiru prednost ima faza 2."""

    validni = [kandidat for kandidat in kandidati if _validan_kandidat_para(kandidat)]
    if not validni:
        return None

    def kljuc(kandidat: KandidatPara) -> tuple[int, int]:
        naziv, rezultat_a, rezultat_b = kandidat
        assert rezultat_a.izvestaj is not None and rezultat_b.izvestaj is not None
        broj_upozorenja = (
            len(rezultat_a.izvestaj.upozorenja)
            + len(rezultat_b.izvestaj.upozorenja)
        )
        return broj_upozorenja, 0 if naziv == "FAZA 2" else 1

    return min(validni, key=kljuc)


def _izaberi_sa_regresionom_granicom(
    kandidat_faze_2: KandidatPara | None,
    kandidat_hinta: KandidatPara | None,
    napravi_kandidata_faze_1: Callable[[], KandidatPara | None],
) -> KandidatPara | None:
    """Koristi validan hint kao granicu, inače obavezno evaluiraj fazu 1."""

    kandidati: list[KandidatPara] = []
    if _validan_kandidat_para(kandidat_hinta):
        assert kandidat_hinta is not None
        kandidati.append(kandidat_hinta)
    else:
        kandidat_faze_1 = napravi_kandidata_faze_1()
        if kandidat_faze_1 is not None:
            kandidati.append(kandidat_faze_1)
    if kandidat_faze_2 is not None:
        kandidati.append(kandidat_faze_2)
    return _izaberi_najbolji_kandidat(kandidati)


def _materijalizuj_kandidata_obe_nedelje(
    naziv: str,
    kandidat: KandidatTermina | None,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    broj_radnika: int,
    vremensko_ogranicenje_prostorija: float = 60,
) -> KandidatPara | None:
    """Dodeli sobe i nezavisno proveri obe nedelje jednog kandidata termina."""

    if kandidat is None:
        return None
    dodele = _dodeli_prostorije_obe(
        kandidat.solver,
        ulaz,
        prostorije,
        kandidat.jedinice,
        kandidat.promenljive,
        vremensko_ogranicenje=vremensko_ogranicenje_prostorija,
        broj_radnika=broj_radnika,
    )
    if dodele is None:
        print(
            f"ZAŠTITA KVALITETA — {naziv}: dodela prostorija nije uspela "
            f"za {vremensko_ogranicenje_prostorija:g} s"
        )
        return None
    dodela_a, dodela_b = dodele
    casovi_a = _izvuci_casove(
        kandidat.solver,
        ulaz,
        kandidat.jedinice,
        kandidat.promenljive,
        dodeljene_prostorije=dodela_a,
    )
    casovi_b = _izvuci_casove(
        kandidat.solver,
        ulaz,
        kandidat.jedinice,
        kandidat.promenljive,
        nedelja_b=True,
        dodeljene_prostorije=dodela_b,
    )
    cilj = kandidat.solver.objective_value if kandidat.optimizovan else None
    return (
        naziv,
        Rezultat(
            kandidat.status,
            casovi_a,
            proveri(ulaz, prostorije, nedostupnosti, casovi_a, Smena.CRVENA),
            cilj,
        ),
        Rezultat(
            kandidat.status,
            casovi_b,
            proveri(ulaz, prostorije, nedostupnosti, casovi_b, Smena.PLAVA),
            cilj,
        ),
    )


def _kandidat_originalnog_hinta(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    hintovi: Sequence[Cas],
    hintovi_b: Sequence[Cas],
) -> KandidatPara | None:
    """Materijalizuj kompletan A+B hint sa njegovim originalnim sobama."""

    if not hintovi or not hintovi_b:
        return None
    casovi_a = _kanonizuj_hintove(ulaz, hintovi, prostorije)
    casovi_b = _kanonizuj_hintove(ulaz, hintovi_b, prostorije)
    izvestaj_a = proveri(
        ulaz, prostorije, nedostupnosti, casovi_a, Smena.CRVENA
    )
    izvestaj_b = proveri(
        ulaz, prostorije, nedostupnosti, casovi_b, Smena.PLAVA
    )
    if (
        izvestaj_a.ispravan
        and izvestaj_b.ispravan
        and not _hint_postuje_medjunedeljne_invarijante(ulaz, casovi_a, casovi_b)
    ):
        izvestaj_a.greske.append(
            "стална и средња одељења морају имати исти термин и простор у обе недеље"
        )
    return (
        "HINT",
        Rezultat(
            "prethodni raspored (regresiona granica)",
            casovi_a,
            izvestaj_a,
            None,
        ),
        Rezultat(
            "prethodni raspored (regresiona granica)",
            casovi_b,
            izvestaj_b,
            None,
        ),
    )


def _hint_postuje_medjunedeljne_invarijante(
    ulaz: Ulaz,
    casovi_a: Sequence[Cas],
    casovi_b: Sequence[Cas],
) -> bool:
    """Proveri A=B za časove odeljenja čija se smena ne menja."""

    def stalni_casovi(casovi: Sequence[Cas]) -> Counter[tuple[object, ...]]:
        return Counter(
            (
                cas.dan,
                cas.blok,
                cas.predmet,
                tuple(sorted(cas.odeljenja)),
                cas.nastavnik,
                cas.korepetitor,
                cas.prostorija,
            )
            for cas in casovi
            if cas.odeljenja
            and all(
                not ulaz.odeljenja[oznaka].smena.menja_se
                for oznaka in cas.odeljenja
            )
        )

    return stalni_casovi(casovi_a) == stalni_casovi(casovi_b)


def _materijalizuj_kandidata_faze_1(
    kandidat: KandidatTermina,
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    broj_radnika: int,
) -> KandidatPara | None:
    """Materijalizuj F1 sa starim limitom dodele prostorija od 60 sekundi."""

    return _materijalizuj_kandidata_obe_nedelje(
        "FAZA 1",
        kandidat,
        ulaz,
        prostorije,
        nedostupnosti,
        broj_radnika,
        vremensko_ogranicenje_prostorija=60,
    )


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

    solver, jedinice, promenljive, status_tekst, sobe_a, sobe_b = _resi_u_dve_faze(
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
    casovi_a = _izvuci_casove(
        solver, ulaz, jedinice, promenljive,
        dodeljene_prostorije=sobe_a,
    )
    casovi_b = _izvuci_casove(
        solver, ulaz, jedinice, promenljive, nedelja_b=True,
        dodeljene_prostorije=sobe_b,
    )
    izvestaj_a = proveri(
        ulaz, prostorije, nedostupnosti, casovi_a, Smena.CRVENA
    )
    izvestaj_b = proveri(
        ulaz, prostorije, nedostupnosti, casovi_b, Smena.PLAVA
    )
    if not izvestaj_a.ispravan or not izvestaj_b.ispravan:
        status = f"{status_tekst}; hard validacija A/B nije prošla"
        return (
            Rezultat(status, (), izvestaj_a, None),
            Rezultat(status, (), izvestaj_b, None),
        )
    cilj = solver.objective_value if "optimizovano" in status_tekst else None
    return Rezultat(
        status_tekst,
        casovi_a,
        izvestaj_a,
        cilj,
    ), Rezultat(
        status_tekst,
        casovi_b,
        izvestaj_b,
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


def _sacuvaj_izlaze_atomski(
    direktorijum: Path,
    casovi_a: Sequence[Cas],
    casovi_b: Sequence[Cas],
) -> None:
    """Pripremi ceo A/B/HTML skup, pa ga zameni uz rollback pri grešci."""

    direktorijum.mkdir(parents=True, exist_ok=True)
    imena = ("nedelja_a.csv", "nedelja_b.csv", "raspored.html")
    with tempfile.TemporaryDirectory(
        prefix=".raspored-", dir=direktorijum
    ) as privremeni:
        priprema = Path(privremeni)
        sacuvaj_csv(priprema / imena[0], casovi_a)
        sacuvaj_csv(priprema / imena[1], casovi_b)
        napravi_html(
            priprema / imena[0], priprema / imena[1], priprema / imena[2]
        )
        if not all((priprema / ime).is_file() for ime in imena):
            raise RuntimeError("Није припремљен цео скуп излазних датотека")

        rezervne = priprema / "prethodni"
        rezervne.mkdir()
        sklonjeni: list[str] = []
        postavljeni: list[str] = []
        try:
            for ime in imena:
                cilj = direktorijum / ime
                if cilj.exists():
                    os.replace(cilj, rezervne / ime)
                    sklonjeni.append(ime)
            for ime in imena:
                os.replace(priprema / ime, direktorijum / ime)
                postavljeni.append(ime)
        except BaseException:
            for ime in postavljeni:
                cilj = direktorijum / ime
                if cilj.exists():
                    cilj.unlink()
            for ime in sklonjeni:
                rezerva = rezervne / ime
                if rezerva.exists():
                    os.replace(rezerva, direktorijum / ime)
            raise


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
        if rezultat.izvestaj is not None:
            print(rezultat.izvestaj.tekst(latinica=True))
        if not rezultat.pronadjen:
            izlazni_status = 1
            continue
        assert rezultat.izvestaj is not None
        if not rezultat.izvestaj.ispravan:
            izlazni_status = 1
    oba_validna = (
        izlazni_status == 0
        and rezultat_a.pronadjen
        and rezultat_b.pronadjen
        and rezultat_a.izvestaj is not None
        and rezultat_b.izvestaj is not None
        and rezultat_a.izvestaj.ispravan
        and rezultat_b.izvestaj.ispravan
    )
    if oba_validna:
        _sacuvaj_izlaze_atomski(
            argumenti.izlaz, rezultat_a.casovi, rezultat_b.casovi
        )
        print(f"HTML: {argumenti.izlaz / 'raspored.html'}")
    return izlazni_status


if __name__ == "__main__":
    raise SystemExit(main())
