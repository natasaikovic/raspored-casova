"""CP-SAT rešavač rasporeda časova.

Rešavač proizvodi isti CSV koji čita :mod:`src.proveravac`. Model bira obe
nedelje zajedno. Srednja škola i stalne smene ostaju iste, dok naizmenične
smene osnovne škole u B koriste inverz smene iz A.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Sequence

from ortools.sat.python import cp_model

from .loader import ucitaj_nedostupnost, ucitaj_prostorije, ucitaj_vise
from .izuzeci import dozvoljen_peti_cas_solfedja, izuzet_od_ogranicenja_pauza
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
from .proveravac import Cas, Izvestaj, proveri, ucitaj_resenje


VERSKA = "Верска настава"
GRADJANSKO = "Грађанско васпитање"
INFORMATIKA = "Рачунарство и информатика"
REPERTOAR_KLASICNOG = "Репертоар класичног балета"
NARODNA_IGRA_GLAVNI = "Народна игра – главни предмет"
REPERTOAR_NARODNE = "Репертоар народне игре"
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
            if dozvoljen_peti_cas_solfedja(
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
) -> tuple[Prostorija, ...]:
    predmet = ulaz.predmeti[zahtev.predmet]
    tip = TipProstorije.SALA if predmet.trazi_salu else TipProstorije.UCIONICA
    if zahtev.predmet == INFORMATIKA:
        return tuple(p for p in prostorije if p.oznaka == "KM-уч1")
    if zahtev.predmet in {NARODNA_IGRA_GLAVNI, REPERTOAR_NARODNE}:
        return tuple(
            p
            for p in prostorije
            if p.tip is TipProstorije.SALA
            and p.lokacija == SPORTSKA_GIMNAZIJA
            and p.oznaka in SG_SALE
        )
    if zahtev.predmet == REPERTOAR_KLASICNOG and zahtev.odeljenja[0] in {
        "III1", "III2", "IV1", "IV2"
    }:
        return tuple(p for p in prostorije if p.tip is tip)
    return tuple(p for p in prostorije if p.tip is tip and p.oznaka != NP_SALA)


def _kazna_sala_narodne_igre(zahtev: Zahtev, oznaka: str) -> int:
    """SG-1 je standard; SG-2/SG-3 su izuzetak, prvenstveno za IV5."""

    if zahtev.predmet != NARODNA_IGRA_GLAVNI or oznaka == "SG-1":
        return 0
    if oznaka not in {"SG-2", "SG-3"}:
        return 100_000
    return 1_000 if zahtev.odeljenja == ("IV5",) else 10_000


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
    putni blok neposredno pre nastave u Narodnom pozoristu. Umesto posebnog
    intervala za svaku mogucu lokaciju biramo samo lokaciju pre i posle
    eventualnog putnog bloka.
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
                dozvoljeni_prelazi.append(
                    (pre_indeks, posle_indeks, 0, 0)
                )
            elif neposredan:
                dozvoljeni_prelazi.append(
                    (pre_indeks, posle_indeks, 1, 0)
                )
            elif put_ka_np:
                dozvoljeni_prelazi.append(
                    (pre_indeks, posle_indeks, 1, 1)
                )
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
    # slobodan blok je put ka nastavi u Narodnom pozorištu.
    model.add(
        kraj - prvi == zauzeto + ima_putni_blok
    ).only_enforce_if(ima_cas)
    kazne.append(300 * menja_lokaciju)


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
            if not izuzet_od_ogranicenja_pauza(osoba):
                model.add(duzina_pauze <= 2)
            dnevne_pauze.append(ima_pauzu)
            kazne.append(500 * ima_pauzu)
            kazne.append(100 * duzina_pauze)
        if not izuzet_od_ogranicenja_pauza(osoba):
            model.add(sum(dnevne_pauze) <= 1)


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

        moguce = _moguce_prostorije(zahtev, ulaz, prostorije)
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
                koristi = model.new_bool_var(
                    f"{prefiks}_lok_{broj_lokacije}"
                )
                lokacije[lokacija] = koristi
                intervali_kapaciteta[(lokacija, tip)].append(
                    model.new_optional_interval_var(
                        start,
                        jedinica.trajanje,
                        kraj,
                        koristi,
                        f"{prefiks}_lok_{broj_lokacije}_i",
                    )
                )
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
                        interval_b_lokacije = intervali_kapaciteta[
                            (lokacija, tip)
                        ][-1]
                    lokacije_b[lokacija] = koristi_b
                    intervali_kapaciteta_b[(lokacija, tip)].append(
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
            if prostorija.oznaka == NP_SALA:
                np_izbori[zahtev.odeljenja[0]].append(koristi)
                if jedinica.trajanje != 2:
                    model.add(koristi == 0)
                else:
                    model.add(blok == 10).only_enforce_if(koristi)
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

    # Učenici nemaju prazne časove. Jedini izuzetak je putni blok neposredno
    # pre nastave u Narodnom pozorištu.
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
    model.minimize(sum(troskovi))
    _dodaj_hintove(model, ulaz, jedinice_zahteva, promenljive, hintovi)
    return model, jedinice, promenljive


def _kanonizuj_hintove(ulaz: Ulaz, hintovi: Sequence[Cas]) -> tuple[Cas, ...]:
    """Poveži latinični radni raspored sa kanonskim vrednostima ulaza."""

    def mapa(vrednosti: Iterable[str]) -> dict[str, str]:
        return {kljuc_pisma(v): v for v in vrednosti}

    dani = mapa(DANI)
    predmeti = mapa(ulaz.predmeti)
    odeljenja = mapa(ulaz.odeljenja)
    nastavnici = mapa(ulaz.nastavnici)
    korepetitori = mapa(ulaz.korepetitori)

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
            prostorija=c.prostorija,
            red=c.red,
        )
        for c in hintovi
    )


def _dodaj_hintove(
    model: cp_model.CpModel,
    ulaz: Ulaz,
    jedinice_zahteva: dict[int, list[Jedinica]],
    promenljive: dict[int, PromenljiveJedinice],
    hintovi: Sequence[Cas],
) -> None:
    """Dodaj nepotpune CP-SAT hintove iz postojeće radne verzije."""

    if not hintovi:
        return
    hintovi = _kanonizuj_hintove(ulaz, hintovi)
    po_kljucu: dict[tuple[str, str, tuple[str, ...]], list[Cas]] = defaultdict(list)
    for cas in hintovi:
        po_kljucu[(cas.predmet, cas.nastavnik, tuple(cas.odeljenja))].append(cas)

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
                niz = []
                for pomeraj in range(jedinica.trajanje):
                    pogodak = next(
                        (
                            i for i in neiskorisceni
                            if redovi[i].dan == prvi.dan
                            and redovi[i].blok == prvi.blok + pomeraj
                            and redovi[i].prostorija == prvi.prostorija
                        ),
                        None,
                    )
                    if pogodak is None:
                        niz = []
                        break
                    niz.append(pogodak)
                if niz:
                    izabran = tuple(niz)
                    break
            if not izabran:
                continue
            neiskorisceni.difference_update(izabran)
            cas = redovi[izabran[0]]
            p = promenljive[jedinica.indeks]
            dan = DANI.index(cas.dan)
            start_hinta = dan * KORAK_DANA + cas.blok
            domen = tuple(p.start.proto.domain)
            if not any(
                donja <= start_hinta <= gornja
                for donja, gornja in zip(domen[::2], domen[1::2])
            ):
                continue
            model.add_hint(p.dan, dan)
            model.add_hint(p.blok, cas.blok)
            model.add_hint(p.start, start_hinta)
            kanonska_prostorija = next(
                (
                    oznaka for oznaka in p.prostorije
                    if kljuc_pisma(oznaka) == kljuc_pisma(cas.prostorija)
                ),
                None,
            )
            if kanonska_prostorija is not None:
                for oznaka, koristi in p.prostorije.items():
                    model.add_hint(koristi, int(oznaka == kanonska_prostorija))


def _status_tekst(status: cp_model.CpSolverStatus) -> str:
    return {
        cp_model.OPTIMAL: "optimalno",
        cp_model.FEASIBLE: "dopustivo",
        cp_model.INFEASIBLE: "nema rešenja",
        cp_model.MODEL_INVALID: "neispravan model",
        cp_model.UNKNOWN: "vremensko ograničenje",
    }.get(status, str(status))


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
            for prostorija in _moguce_prostorije(zahtev, ulaz, prostorije)
            if prostorija.lokacija == lokacija
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
            kazna = _kazna_sala_narodne_igre(zahtev, prostorija.oznaka)
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
        moguce = _moguce_prostorije(zahtev, ulaz, prostorije)
        moguce_a = [s for s in moguce if s.lokacija == lokacija_a]
        moguce_b = [s for s in moguce if s.lokacija == lokacija_b]
        if not moguce_a or not moguce_b:
            return None
        izbori_a[jedinica.indeks] = {}
        izbori_b[jedinica.indeks] = {}
        for soba in moguce_a:
            koristi = model.new_bool_var(f"j{jedinica.indeks}_{soba.oznaka}_a")
            izbori_a[jedinica.indeks][soba.oznaka] = koristi
            kazna = _kazna_sala_narodne_igre(zahtev, soba.oznaka)
            if kazna:
                kazne.append(kazna * koristi)
            intervali_a[soba.oznaka].append(model.new_optional_fixed_size_interval_var(
                start_a, jedinica.trajanje, koristi,
                f"j{jedinica.indeks}_{soba.oznaka}_i_a",
            ))
        model.add_exactly_one(izbori_a[jedinica.indeks].values())
        if zahtev.smena.menja_se:
            for soba in moguce_b:
                koristi = model.new_bool_var(f"j{jedinica.indeks}_{soba.oznaka}_b")
                izbori_b[jedinica.indeks][soba.oznaka] = koristi
                kazna = _kazna_sala_narodne_igre(zahtev, soba.oznaka)
                if kazna:
                    kazne.append(kazna * koristi)
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
) -> Rezultat:
    """Reši jednu nedelju i proveri dobijene časove nezavisnim proveravačem."""

    model, jedinice, promenljive = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        jutarnja_smena,
        hintovi,
        sa_nedeljom_b,
        samo_lokacije=True,
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    solver.parameters.num_search_workers = broj_radnika
    solver.parameters.random_seed = seme
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Rezultat(_status_tekst(status), (), None, None)

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
    return Rezultat(_status_tekst(status), casovi, izvestaj, solver.objective_value)


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
) -> tuple[Rezultat, Rezultat]:
    """Reši A i B zajedno, da izbor rasporeda A ne može blokirati B."""

    model, jedinice, promenljive = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        Smena.CRVENA,
        hintovi,
        sa_nedeljom_b=True,
        samo_lokacije=True,
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0, vremensko_ogranicenje)
    solver.parameters.num_search_workers = broj_radnika
    solver.parameters.random_seed = seme
    status = solver.solve(model)
    status_tekst = _status_tekst(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
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
    cilj = solver.objective_value
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
    return (
        ulaz,
        ucitaj_prostorije(direktorijum / "prostorije.csv"),
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
        "--bez-hintova",
        action="store_true",
        help="ne koristi postojeće radne verzije kao početne hintove",
    )
    argumenti = parser.parse_args(argv)

    ulaz, prostorije, nedostupnosti = ucitaj_standardne_ulaze(argumenti.ulazi)
    hintovi: tuple[Cas, ...] = ()
    putanja_hinta = Path("radne_verzije/2026-27/nedelja_a.csv")
    if not argumenti.bez_hintova and putanja_hinta.exists():
        hintovi = ucitaj_resenje(putanja_hinta)
    rezultat_a, rezultat_b = resi_obe_nedelje(
        ulaz,
        prostorije,
        nedostupnosti,
        vremensko_ogranicenje=argumenti.vremensko_ogranicenje,
        broj_radnika=argumenti.broj_radnika,
        seme=argumenti.seme,
        hintovi=hintovi,
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
    return izlazni_status


if __name__ == "__main__":
    raise SystemExit(main())
