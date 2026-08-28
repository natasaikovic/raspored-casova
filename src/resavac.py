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
NP_SALA = "NP-сала"
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
        if zahtev.smena is Smena.POSEBNA and zahtev.fond % 2:
            raise ValueError(
                f"{zahtev.gde}: посебна смена „{zahtev.smena_opis}“ "
                "захтева паран фонд часова"
            )
        if predmet.igracki:
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
        blokovi = PRVA_SMENA if zahtev.smena is jutarnja_smena else DRUGA_SMENA
    elif zahtev.smena is Smena.STALNO_POPODNE:
        blokovi = DRUGA_SMENA
    elif zahtev.smena is Smena.CEO_DAN:
        blokovi = tuple(blok.broj for blok in BLOKOVI)
    else:
        poznati_opis = "стално од 18,30 часова понедељком средом петком"
        if zahtev.smena_opis != poznati_opis:
            return ()
        kandidati = tuple((dan, 13) for dan in (0, 2, 4) if trajanje == 2)
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
    if zahtev.predmet == REPERTOAR_KLASICNOG and zahtev.odeljenja[0] in {
        "III1", "III2", "IV1", "IV2"
    }:
        return tuple(p for p in prostorije if p.tip is tip)
    return tuple(p for p in prostorije if p.tip is tip and p.oznaka != NP_SALA)


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
        for prostorija in moguce:
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
        model.add_exactly_one(izbor_prostorije.values())
        if sa_nedeljom_b and zahtev.smena.menja_se:
            assert izbor_prostorije_b is not None
            model.add_exactly_one(izbor_prostorije_b.values())
        lokacije: dict[str, cp_model.BoolVar] = {}
        for lokacija, izbori in po_lokaciji.items():
            koristi_lokaciju = model.new_bool_var(f"{prefiks}_lok_{len(lokacije)}")
            model.add(koristi_lokaciju == sum(izbori))
            lokacije[lokacija] = koristi_lokaciju
        lokacije_b: dict[str, cp_model.BoolVar] | None = None
        if sa_nedeljom_b:
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

    for intervali in intervali_nastavnika.values():
        model.add_no_overlap(intervali)
    for intervali in intervali_korepetitora.values():
        model.add_no_overlap(intervali)
    for intervali in intervali_prostorija.values():
        model.add_no_overlap(intervali)
    if sa_nedeljom_b:
        for intervali in intervali_nastavnika_b.values():
            model.add_no_overlap(intervali)
        for intervali in intervali_korepetitora_b.values():
            model.add_no_overlap(intervali)
        for intervali in intervali_prostorija_b.values():
            model.add_no_overlap(intervali)

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

    # Prazni časovi i više lokacija u danu ulaze u cilj. Čvrsto nametanje oba
    # svojstva čini prvi raspored nepotrebno teškim za nalaženje; nezavisni
    # proveravač ih i dalje prijavljuje kao greške, pa kandidat ne može biti
    # pogrešno predstavljen kao konačan.
    for token, stavke in po_ucenickom_tokenu.items():
        odeljenje = ulaz.odeljenja[token]
        for indeks_dana in range(len(DANI)):
            prisutnosti = [promenljive[j.indeks].po_danu[indeks_dana] for j in stavke]
            ima_cas = model.new_bool_var(f"{token}_d{indeks_dana}_ima")
            model.add_max_equality(ima_cas, prisutnosti)
            prvi = model.new_int_var(1, len(BLOKOVI), f"{token}_d{indeks_dana}_prvi")
            poslednji = model.new_int_var(0, len(BLOKOVI), f"{token}_d{indeks_dana}_poslednji")
            model.add(prvi == 1).only_enforce_if(~ima_cas)
            model.add(poslednji == 0).only_enforce_if(~ima_cas)
            for jedinica in stavke:
                p = promenljive[jedinica.indeks]
                model.add(prvi <= p.blok).only_enforce_if(p.po_danu[indeks_dana])
                model.add(
                    poslednji >= p.blok + jedinica.trajanje - 1
                ).only_enforce_if(p.po_danu[indeks_dana])
            zauzeto = sum(
                jedinica.trajanje * promenljive[jedinica.indeks].po_danu[indeks_dana]
                for jedinica in stavke
            )
            prazni = model.new_int_var(0, len(BLOKOVI), f"{token}_d{indeks_dana}_prazni")
            model.add(prazni >= poslednji - prvi + 1 - zauzeto)
            kazne.append(1000 * prazni)

            koristi_lokaciju: list[cp_model.BoolVar] = []
            sve_lokacije = sorted(
                {lokacija for j in stavke for lokacija in promenljive[j.indeks].lokacije}
            )
            for broj_lokacije, lokacija in enumerate(sve_lokacije):
                preseci: list[cp_model.BoolVar] = []
                for jedinica in stavke:
                    p = promenljive[jedinica.indeks]
                    na_lokaciji = p.lokacije.get(lokacija)
                    if na_lokaciji is None:
                        continue
                    oba = model.new_bool_var(
                        f"{token}_d{indeks_dana}_l{broj_lokacije}_j{jedinica.indeks}"
                    )
                    model.add(oba <= p.po_danu[indeks_dana])
                    model.add(oba <= na_lokaciji)
                    model.add(oba >= p.po_danu[indeks_dana] + na_lokaciji - 1)
                    preseci.append(oba)
                koristi = model.new_bool_var(
                    f"{token}_d{indeks_dana}_l{broj_lokacije}"
                )
                if preseci:
                    model.add_max_equality(koristi, preseci)
                else:
                    model.add(koristi == 0)
                koristi_lokaciju.append(koristi)
            visak_lokacija = model.new_int_var(
                0, max(0, len(koristi_lokaciju) - 1),
                f"{token}_d{indeks_dana}_visak_lokacija",
            )
            model.add(visak_lokacija >= sum(koristi_lokaciju) - 1)
            model.add(sum(koristi_lokaciju) <= 2)
            dve_lokacije = model.new_bool_var(f"{token}_d{indeks_dana}_dve_lokacije")
            model.add(sum(koristi_lokaciju) == 2).only_enforce_if(dve_lokacije)
            model.add(sum(koristi_lokaciju) <= 1).only_enforce_if(~dve_lokacije)
            model.add(prazni == 0).only_enforce_if(~dve_lokacije)
            kazne.append(300 * visak_lokacija)

            if odeljenje.skola is Skola.SREDNJA:
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

    # Naizmenična odeljenja imaju zaseban raspored u B, pa isti približni cilj
    # kvaliteta primenjujemo i na njihove B promenljive.
    if sa_nedeljom_b:
        for token, stavke in po_ucenickom_tokenu.items():
            if not ulaz.odeljenja[token].smena.menja_se:
                continue
            for indeks_dana in range(len(DANI)):
                prisutnosti_b = []
                for jedinica in stavke:
                    po_danu_b = promenljive[jedinica.indeks].po_danu_b
                    assert po_danu_b is not None
                    prisutnosti_b.append(po_danu_b[indeks_dana])
                ima_cas_b = model.new_bool_var(f"{token}_d{indeks_dana}_ima_b")
                model.add_max_equality(ima_cas_b, prisutnosti_b)
                prvi_b = model.new_int_var(
                    1, len(BLOKOVI), f"{token}_d{indeks_dana}_prvi_b"
                )
                poslednji_b = model.new_int_var(
                    0, len(BLOKOVI), f"{token}_d{indeks_dana}_poslednji_b"
                )
                model.add(prvi_b == 1).only_enforce_if(~ima_cas_b)
                model.add(poslednji_b == 0).only_enforce_if(~ima_cas_b)
                for jedinica in stavke:
                    p = promenljive[jedinica.indeks]
                    assert p.blok_b is not None and p.po_danu_b is not None
                    model.add(prvi_b <= p.blok_b).only_enforce_if(
                        p.po_danu_b[indeks_dana]
                    )
                    model.add(
                        poslednji_b >= p.blok_b + jedinica.trajanje - 1
                    ).only_enforce_if(p.po_danu_b[indeks_dana])
                zauzeto_b = sum(
                    jedinica.trajanje
                    * promenljive[jedinica.indeks].po_danu_b[indeks_dana]
                    for jedinica in stavke
                )
                prazni_b = model.new_int_var(
                    0, len(BLOKOVI), f"{token}_d{indeks_dana}_prazni_b"
                )
                model.add(prazni_b >= poslednji_b - prvi_b + 1 - zauzeto_b)
                kazne.append(1000 * prazni_b)

                sve_lokacije_b = sorted(
                    {
                        lokacija
                        for jedinica in stavke
                        for lokacija in promenljive[jedinica.indeks].lokacije_b
                    }
                )
                koristi_lokaciju_b: list[cp_model.BoolVar] = []
                for broj_lokacije, lokacija in enumerate(sve_lokacije_b):
                    preseci_b: list[cp_model.BoolVar] = []
                    for jedinica in stavke:
                        p = promenljive[jedinica.indeks]
                        assert p.po_danu_b is not None and p.lokacije_b is not None
                        na_lokaciji_b = p.lokacije_b.get(lokacija)
                        if na_lokaciji_b is None:
                            continue
                        oba_b = model.new_bool_var(
                            f"{token}_d{indeks_dana}_l{broj_lokacije}"
                            f"_j{jedinica.indeks}_b"
                        )
                        model.add(oba_b <= p.po_danu_b[indeks_dana])
                        model.add(oba_b <= na_lokaciji_b)
                        model.add(
                            oba_b >= p.po_danu_b[indeks_dana] + na_lokaciji_b - 1
                        )
                        preseci_b.append(oba_b)
                    koristi_b = model.new_bool_var(
                        f"{token}_d{indeks_dana}_l{broj_lokacije}_b"
                    )
                    model.add_max_equality(koristi_b, preseci_b)
                    koristi_lokaciju_b.append(koristi_b)
                visak_lokacija_b = model.new_int_var(
                    0,
                    max(0, len(koristi_lokaciju_b) - 1),
                    f"{token}_d{indeks_dana}_visak_lokacija_b",
                )
                model.add(visak_lokacija_b >= sum(koristi_lokaciju_b) - 1)
                model.add(sum(koristi_lokaciju_b) <= 2)
                dve_lokacije_b = model.new_bool_var(f"{token}_d{indeks_dana}_dve_lokacije_b")
                model.add(sum(koristi_lokaciju_b) == 2).only_enforce_if(dve_lokacije_b)
                model.add(sum(koristi_lokaciju_b) <= 1).only_enforce_if(~dve_lokacije_b)
                model.add(prazni_b == 0).only_enforce_if(~dve_lokacije_b)
                kazne.append(300 * visak_lokacija_b)

    # Blaga funkcija kvaliteta: prednost imaju Knez Miletina i raniji blokovi.
    # Ispravnost ne zavisi od cilja; sva pravila iznad su čvrsta.
    troskovi: list[cp_model.LinearExprT] = list(kazne)
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        troskovi.append(p.blok)
        for oznaka, koristi in p.prostorije.items():
            prostorija = next(x for x in prostorije if x.oznaka == oznaka)
            if prostorija.lokacija != "Кнез Милетина 8":
                troskovi.append(3 * koristi)
        if sa_nedeljom_b and zahtev.smena.menja_se:
            assert p.blok_b is not None and p.prostorije_b is not None
            troskovi.append(p.blok_b)
            for oznaka, koristi in p.prostorije_b.items():
                prostorija = next(x for x in prostorije if x.oznaka == oznaka)
                if prostorija.lokacija != "Кнез Милетина 8":
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


def _izvuci_casove(
    solver: cp_model.CpSolver,
    ulaz: Ulaz,
    jedinice: Sequence[Jedinica],
    promenljive: dict[int, PromenljiveJedinice],
    nedelja_b: bool = False,
) -> tuple[Cas, ...]:
    redovi: list[Cas] = []
    for jedinica in jedinice:
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        p = promenljive[jedinica.indeks]
        dan_var = p.dan_b if nedelja_b else p.dan
        blok_var = p.blok_b if nedelja_b else p.blok
        prostorije_var = p.prostorije_b if nedelja_b else p.prostorije
        assert dan_var is not None and blok_var is not None
        assert prostorije_var is not None
        dan = solver.value(dan_var)
        blok = solver.value(blok_var)
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
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    solver.parameters.num_search_workers = broj_radnika
    solver.parameters.random_seed = seme
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Rezultat(_status_tekst(status), (), None, None)

    casovi = _izvuci_casove(solver, ulaz, jedinice, promenljive)
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
    """Reši obe nedelje zajedno, sa inverznom smenom osnovne u B."""

    model, jedinice, promenljive = napravi_model(
        ulaz,
        prostorije,
        nedostupnosti,
        Smena.CRVENA,
        hintovi,
        sa_nedeljom_b=True,
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = vremensko_ogranicenje
    solver.parameters.num_search_workers = broj_radnika
    solver.parameters.random_seed = seme
    status = solver.solve(model)
    status_tekst = _status_tekst(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        prazan = Rezultat(status_tekst, (), None, None)
        return prazan, prazan

    casovi_a = _izvuci_casove(solver, ulaz, jedinice, promenljive)
    casovi_b = _izvuci_casove(
        solver, ulaz, jedinice, promenljive, nedelja_b=True
    )
    cilj = solver.objective_value
    return (
        Rezultat(
            status_tekst,
            casovi_a,
            proveri(ulaz, prostorije, nedostupnosti, casovi_a, Smena.CRVENA),
            cilj,
        ),
        Rezultat(
            status_tekst,
            casovi_b,
            proveri(ulaz, prostorije, nedostupnosti, casovi_b, Smena.PLAVA),
            cilj,
        ),
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
