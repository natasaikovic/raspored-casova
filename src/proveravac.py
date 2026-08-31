"""Provera predloženog rasporeda u odnosu na ulazne CSV podatke.

Jedan red rešenja predstavlja jedan školski blok. Proveravač je namerno
nezavisan od budućeg rešavača: isti format može da proizvede OR-Tools, AI agent
ili čovek, a rezultat prolazi kroz potpuno istu proveru.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence

from .izuzeci import dozvoljen_peti_cas_solfedja, izuzet_od_ogranicenja_pauza
from .loader import (
    UlazGreska,
    ucitaj_nedostupnost,
    ucitaj_prostorije,
    ucitaj_vise,
)
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


KOLONE_RESENJA = (
    "дан",
    "блок",
    "предмет",
    "одељења",
    "наставник",
    "корепетитор",
    "просторија",
)

KOLONE_RESENJA_LATINICA = (
    "dan",
    "blok",
    "predmet",
    "odeljenja",
    "nastavnik",
    "korepetitor",
    "prostorija",
)

VERSKA = "Верска настава"
GRADJANSKO = "Грађанско васпитање"
ALTERNATIVNI_PREDMETI = frozenset({VERSKA, GRADJANSKO})
INFORMATIKA = "Рачунарство и информатика"
REPERTOAR_KLASICNOG = "Репертоар класичног балета"
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


@dataclass(frozen=True)
class Cas:
    """Jedan održani časovni blok iz CSV rešenja."""

    dan: str
    blok: int
    predmet: str
    odeljenja: tuple[str, ...]
    nastavnik: str
    korepetitor: str | None
    prostorija: str
    red: int

    @property
    def termin(self) -> tuple[str, int]:
        return self.dan, self.blok

    @property
    def gde(self) -> str:
        return f"ред {self.red}"


@dataclass
class Izvestaj:
    """Sve pronađene greške i upozorenja, skupljene u jednom prolazu."""

    greske: list[str] = field(default_factory=list)
    upozorenja: list[str] = field(default_factory=list)

    @property
    def ispravan(self) -> bool:
        return not self.greske

    def tekst(self, latinica: bool = False) -> str:
        delovi: list[str] = []
        if self.greske:
            delovi.append(f"Распоред није исправан ({len(self.greske)} грешака):")
            delovi.extend(f"  - {poruka}" for poruka in self.greske)
        else:
            delovi.append("Распоред је исправан.")
        if self.upozorenja:
            delovi.append(f"Упозорења ({len(self.upozorenja)}):")
            delovi.extend(f"  - {poruka}" for poruka in self.upozorenja)
        rezultat = "\n".join(delovi)
        return u_latinicu(rezultat) if latinica else rezultat


class ResenjeGreska(ValueError):
    """CSV rešenja nije moguće pročitati."""

    def __init__(self, greske: Iterable[str]) -> None:
        self.greske = list(greske)
        super().__init__("\n".join(self.greske))


def ucitaj_resenje(putanja: str | Path) -> tuple[Cas, ...]:
    """Učitaj strogo definisan CSV format i prijavi sve strukturne greške."""

    putanja = Path(putanja)
    greske: list[str] = []
    casovi: list[Cas] = []
    try:
        with putanja.open(encoding="utf-8-sig", newline="") as datoteka:
            citac = csv.DictReader(datoteka)
            zaglavlje = tuple((ime or "").strip() for ime in (citac.fieldnames or ()))
            latinica = bool(set(zaglavlje) & set(KOLONE_RESENJA_LATINICA))
            kolone = KOLONE_RESENJA_LATINICA if latinica else KOLONE_RESENJA
            nedostaju = [kolona for kolona in kolone if kolona not in zaglavlje]
            visak = [kolona for kolona in zaglavlje if kolona not in kolone]
            greske.extend(f"недостаје колона „{kolona}“" for kolona in nedostaju)
            greske.extend(f"непозната колона „{kolona}“" for kolona in visak)
            if nedostaju:
                raise ResenjeGreska(greske)

            for broj_reda, sirov_red in enumerate(citac, start=2):
                red = {
                    (kljuc or "").strip(): (vrednost or "").strip()
                    for kljuc, vrednost in sirov_red.items()
                    if kljuc
                }
                pocetak = len(greske)

                def obavezno(kolona: str) -> str:
                    vrednost = red.get(kolona, "")
                    if not vrednost:
                        greske.append(
                            f"ред {broj_reda}: „{kolona}“ не сме бити празно"
                        )
                    return vrednost

                nazivi = dict(zip(KOLONE_RESENJA, kolone))
                dan = obavezno(nazivi["дан"])
                predmet = obavezno(nazivi["предмет"])
                nastavnik = obavezno(nazivi["наставник"])
                prostorija = obavezno(nazivi["просторија"])
                sirova_odeljenja = obavezno(nazivi["одељења"])
                odeljenja = tuple(
                    deo.strip() for deo in sirova_odeljenja.split(";") if deo.strip()
                )
                if len(set(odeljenja)) != len(odeljenja):
                    greske.append(f"ред {broj_reda}: одељење је наведено више пута")
                if "," in sirova_odeljenja:
                    greske.append(
                        f"ред {broj_reda}: одељења се раздвајају знаком ; а не зарезом"
                    )

                blok: int | None = None
                sirovi_blok = obavezno(nazivi["блок"])
                if sirovi_blok:
                    try:
                        blok = int(sirovi_blok)
                    except ValueError:
                        greske.append(
                            f"ред {broj_reda}: „блок“ мора бити цео број"
                        )
                    else:
                        if not 1 <= blok <= len(BLOKOVI):
                            greske.append(
                                f"ред {broj_reda}: блок мора бити између 1 и "
                                f"{len(BLOKOVI)}"
                            )

                if len(greske) == pocetak and blok is not None:
                    casovi.append(
                        Cas(
                            dan=dan,
                            blok=blok,
                            predmet=predmet,
                            odeljenja=odeljenja,
                            nastavnik=nastavnik,
                            korepetitor=red.get(nazivi["корепетитор"], "") or None,
                            prostorija=prostorija,
                            red=broj_reda,
                        )
                    )
    except OSError as greska:
        raise ResenjeGreska([f"не могу да прочитам {putanja}: {greska}"]) from greska

    if greske:
        raise ResenjeGreska(greske)
    return tuple(casovi)


def proveri(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    nedostupnosti: Sequence[Nedostupnost],
    casovi: Sequence[Cas],
    jutarnja_smena: Smena = Smena.CRVENA,
) -> Izvestaj:
    """Proveri kompletno rešenje. Funkcija ne prekida na prvoj grešci."""

    izvestaj = Izvestaj()
    if jutarnja_smena not in (Smena.CRVENA, Smena.PLAVA):
        raise ValueError("Јутарња смена мора бити црвена или плава")

    casovi = _kanonizuj_casove(ulaz, prostorije, casovi)
    prostorije_po_oznaci = {p.oznaka: p for p in prostorije}
    zahtevi_po_odeljenju = {
        (zahtev.predmet, odeljenje): zahtev
        for zahtev in ulaz.zahtevi
        for odeljenje in zahtev.odeljenja
    }
    pogodjeni: dict[int, tuple[Zahtev, ...]] = {}

    for cas in casovi:
        zahtevi_casa = _proveri_red(
            cas,
            ulaz,
            prostorije_po_oznaci,
            zahtevi_po_odeljenju,
            nedostupnosti,
            jutarnja_smena,
            izvestaj,
        )
        if zahtevi_casa:
            pogodjeni[cas.red] = zahtevi_casa

    _proveri_fondove(ulaz, casovi, pogodjeni, izvestaj)
    _proveri_sudare(ulaz, casovi, izvestaj)
    _proveri_dnevni_raspored(ulaz, prostorije_po_oznaci, casovi, izvestaj)
    _proveri_dvocase(ulaz, casovi, izvestaj)
    _proveri_versku_i_gradjansko(ulaz, casovi, izvestaj)
    _proveri_narodno_pozoriste(ulaz, casovi, izvestaj)
    _upozori_na_pauze_nastavnika(casovi, izvestaj)
    return izvestaj


def _kanonizuj_casove(
    ulaz: Ulaz,
    prostorije: Sequence[Prostorija],
    casovi: Sequence[Cas],
) -> tuple[Cas, ...]:
    """Poveži latinične izlazne vrednosti sa kanonskim vrednostima iz ulaza."""

    def mapa(vrednosti: Iterable[str]) -> dict[str, str]:
        return {kljuc_pisma(vrednost): vrednost for vrednost in vrednosti}

    dani = mapa(DANI)
    predmeti = mapa(ulaz.predmeti)
    odeljenja = mapa(ulaz.odeljenja)
    nastavnici = mapa(ulaz.nastavnici)
    korepetitori = mapa(ulaz.korepetitori)
    oznake_prostorija = mapa(p.oznaka for p in prostorije)

    def nadji(vrednost: str, vrednosti: dict[str, str]) -> str:
        return vrednosti.get(kljuc_pisma(vrednost), vrednost)

    return tuple(
        replace(
            cas,
            dan=nadji(cas.dan, dani),
            predmet=nadji(cas.predmet, predmeti),
            odeljenja=tuple(nadji(o, odeljenja) for o in cas.odeljenja),
            nastavnik=nadji(cas.nastavnik, nastavnici),
            korepetitor=(
                nadji(cas.korepetitor, korepetitori) if cas.korepetitor else None
            ),
            prostorija=nadji(cas.prostorija, oznake_prostorija),
        )
        for cas in casovi
    )


def _proveri_red(
    cas: Cas,
    ulaz: Ulaz,
    prostorije: dict[str, Prostorija],
    zahtevi_po_odeljenju: dict[tuple[str, str], Zahtev],
    nedostupnosti: Sequence[Nedostupnost],
    jutarnja_smena: Smena,
    izvestaj: Izvestaj,
) -> tuple[Zahtev, ...]:
    if cas.dan not in DANI:
        izvestaj.greske.append(
            f"{cas.gde}: непознат дан „{cas.dan}“; дозвољено је {', '.join(DANI)}"
        )

    if cas.predmet not in ulaz.predmeti:
        izvestaj.greske.append(f"{cas.gde}: непознат предмет „{cas.predmet}“")

    if len(cas.odeljenja) > 3 and cas.predmet not in ALTERNATIVNI_PREDMETI:
        izvestaj.greske.append(
            f"{cas.gde}: један час сме да обухвати највише 3 одељења"
        )

    zahtevi: list[Zahtev] = []
    for oznaka in cas.odeljenja:
        if oznaka not in ulaz.odeljenja:
            izvestaj.greske.append(f"{cas.gde}: непознато одељење {oznaka}")
            continue
        zahtev = zahtevi_po_odeljenju.get((cas.predmet, oznaka))
        if zahtev is None:
            izvestaj.greske.append(
                f"{cas.gde}: одељење {oznaka} нема предмет „{cas.predmet}“"
            )
            continue
        zahtevi.append(zahtev)
        if zahtev.nastavnik != cas.nastavnik:
            izvestaj.greske.append(
                f"{cas.gde}: „{cas.predmet}“ одељењу {oznaka} држи "
                f"{zahtev.nastavnik}, а не {cas.nastavnik}"
            )
        if cas.korepetitor and cas.korepetitor != zahtev.korepetitor:
            ocekivan = zahtev.korepetitor or "нико"
            izvestaj.greske.append(
                f"{cas.gde}: за {oznaka} је корепетитор {ocekivan}, "
                f"а наведен је {cas.korepetitor}"
            )
        _proveri_smenu(cas, zahtev, jutarnja_smena, izvestaj)

    if zahtevi:
        razredi = {z.razred for z in zahtevi}
        nastavnici = {z.nastavnik for z in zahtevi}
        if len(razredi) > 1:
            izvestaj.greske.append(
                f"{cas.gde}: на истом часу су одељења различитих разреда"
            )
        if len(nastavnici) > 1:
            izvestaj.greske.append(
                f"{cas.gde}: груписана одељења немају истог наставника"
            )

    predmet = ulaz.predmeti.get(cas.predmet)
    if predmet and predmet.trazi_salu and len(cas.odeljenja) != 1:
        izvestaj.greske.append(
            f"{cas.gde}: предмет који тражи салу мора имати тачно једно одељење"
        )

    prostorija = prostorije.get(cas.prostorija)
    if prostorija is None:
        izvestaj.greske.append(
            f"{cas.gde}: непозната просторија {cas.prostorija}"
        )
    elif predmet:
        ocekivani_tip = (
            TipProstorije.SALA if predmet.trazi_salu else TipProstorije.UCIONICA
        )
        if prostorija.tip is not ocekivani_tip:
            izvestaj.greske.append(
                f"{cas.gde}: предмет „{cas.predmet}“ тражи {ocekivani_tip.value}, "
                f"а {cas.prostorija} је {prostorija.tip.value}"
            )
        if cas.predmet == INFORMATIKA and cas.prostorija != "KM-уч1":
            izvestaj.greske.append(
                f"{cas.gde}: {INFORMATIKA} мора бити у просторији KM-уч1"
            )
        if cas.prostorija == "NP-сала":
            if cas.predmet != REPERTOAR_KLASICNOG:
                izvestaj.greske.append(
                    f"{cas.gde}: NP-сала је само за {REPERTOAR_KLASICNOG}"
                )
            if cas.blok not in (10, 11):
                izvestaj.greske.append(
                    f"{cas.gde}: NP-сала се користи само у блоковима 10 и 11"
                )

    if cas.dan == "субота":
        if cas.blok > 8:
            izvestaj.greske.append(
                f"{cas.gde}: суботом настава не сме трајати после 15:05"
            )
        elif cas.blok > 6:
            izvestaj.upozorenja.append(
                f"{cas.gde}: суботњи час после 13:15 треба избегавати"
            )
        if prostorija and prostorija.tip is TipProstorije.SALA and not (
            cas.prostorija.startswith("SG-")
        ):
            izvestaj.upozorenja.append(
                f"{cas.gde}: суботом предност имају сале Спортске гимназије"
            )

    for stavka in nedostupnosti:
        if (
            stavka.nastavnik == cas.nastavnik
            and stavka.dan == cas.dan
            and stavka.od_bloka <= cas.blok <= stavka.do_bloka
        ):
            izvestaj.greske.append(
                f"{cas.gde}: наставник {cas.nastavnik} није доступан "
                f"({cas.dan}, блокови {stavka.od_bloka}–{stavka.do_bloka})"
            )
        if (
            cas.korepetitor
            and stavka.nastavnik == cas.korepetitor
            and stavka.dan == cas.dan
            and stavka.od_bloka <= cas.blok <= stavka.do_bloka
        ):
            izvestaj.greske.append(
                f"{cas.gde}: корепетитор {cas.korepetitor} није доступан "
                f"({cas.dan}, блокови {stavka.od_bloka}–{stavka.do_bloka})"
            )

    return tuple(zahtevi)


def _proveri_narodno_pozoriste(
    ulaz: Ulaz, casovi: Sequence[Cas], izvestaj: Izvestaj
) -> None:
    ima_np_program = all(
        any(
            z.predmet == REPERTOAR_KLASICNOG and oznaka in z.odeljenja
            for z in ulaz.zahtevi
        )
        for oznaka in ("IV1", "IV2")
    )
    if not ima_np_program:
        return
    np_casovi = [cas for cas in casovi if cas.prostorija == "NP-сала"]
    po_odeljenju = Counter(
        cas.odeljenja[0] for cas in np_casovi if len(cas.odeljenja) == 1
    )
    if po_odeljenju["IV1"] != 4:
        izvestaj.greske.append(
            f"NP-сала: IV1 мора имати 4 блока (два двочаса), има {po_odeljenju['IV1']}"
        )
    if po_odeljenju["IV2"] != 4:
        izvestaj.greske.append(
            f"NP-сала: IV2 мора имати 4 блока (два двочаса), има {po_odeljenju['IV2']}"
        )
    treci = po_odeljenju["III1"] + po_odeljenju["III2"]
    if treci != 2:
        izvestaj.greske.append(
            f"NP-сала: III1 или III2 морају имати један двочас (2 блока), има {treci}"
        )
    if len(np_casovi) != 10:
        izvestaj.greske.append(
            f"NP-сала: потребно је укупно 10 блокова (5 двочаса), има {len(np_casovi)}"
        )


def _proveri_smenu(
    cas: Cas, zahtev: Zahtev, jutarnja: Smena, izvestaj: Izvestaj
) -> None:
    smena = zahtev.smena
    dozvoljeni: tuple[int, ...] | None = None
    if smena in (Smena.CRVENA, Smena.PLAVA):
        if smena is jutarnja:
            dozvoljeni = PRVA_SMENA
            if dozvoljen_peti_cas_solfedja(
                cas.predmet, cas.nastavnik, cas.odeljenja
            ):
                dozvoljeni = PRVA_SMENA + (5,)
        else:
            dozvoljeni = DRUGA_SMENA
    elif smena is Smena.STALNO_POPODNE:
        dozvoljeni = DRUGA_SMENA
    elif smena is Smena.POSEBNA:
        poznati_opis = "стално од 18,30 часова понедељком средом петком"
        if zahtev.smena_opis == poznati_opis:
            upozorenje = (
                "за П1 је привремено протумачено да шест часова значи "
                "два часа понедељком, средом и петком у блоковима 13–14"
            )
            if upozorenje not in izvestaj.upozorenja:
                izvestaj.upozorenja.append(upozorenje)
            if cas.dan not in ("понедељак", "среда", "петак") or cas.blok not in (13, 14):
                izvestaj.greske.append(
                    f"{cas.gde}: {zahtev.odeljenja[0]} сме само понедељком, "
                    "средом и петком у блоковима 13–14"
                )
        else:
            izvestaj.greske.append(
                f"{cas.gde}: није програмирано правило посебне смене "
                f"„{zahtev.smena_opis}“"
            )
        return
    if dozvoljeni is not None and cas.blok not in dozvoljeni:
        izvestaj.greske.append(
            f"{cas.gde}: одељење {zahtev.odeljenja[0]} је у смени "
            f"„{smena.value}“ и не сме у блок {cas.blok}"
        )


def _proveri_fondove(
    ulaz: Ulaz,
    casovi: Sequence[Cas],
    pogodjeni: dict[int, tuple[Zahtev, ...]],
    izvestaj: Izvestaj,
) -> None:
    pokrivenost = Counter(
        (cas.predmet, oznaka)
        for cas in casovi
        for oznaka in cas.odeljenja
        if cas.red in pogodjeni
    )
    for zahtev in ulaz.zahtevi:
        for oznaka in zahtev.odeljenja:
            stvarno = pokrivenost[(zahtev.predmet, oznaka)]
            if stvarno != zahtev.fond:
                izvestaj.greske.append(
                    f"предмет „{zahtev.predmet}“ за {oznaka}: потребно "
                    f"{zahtev.fond}, распоређено {stvarno}"
                )

    cilj_sesija = Counter()
    for zahtev in ulaz.zahtevi:
        skola = ulaz.odeljenja[zahtev.odeljenja[0]].skola
        cilj_sesija[(zahtev.predmet, zahtev.nastavnik, zahtev.razred, skola)] += zahtev.fond
    stvarne_sesije = Counter()
    for cas in casovi:
        zahtevi = pogodjeni.get(cas.red)
        if not zahtevi:
            continue
        prvi = zahtevi[0]
        skola = ulaz.odeljenja[prvi.odeljenja[0]].skola
        stvarne_sesije[(cas.predmet, cas.nastavnik, prvi.razred, skola)] += 1
    for kljuc in sorted(set(cilj_sesija) | set(stvarne_sesije), key=str):
        if cilj_sesija[kljuc] != stvarne_sesije[kljuc]:
            predmet, nastavnik, razred, _skola = kljuc
            izvestaj.greske.append(
                f"број заједничких часова „{predmet}“, разред {razred}, "
                f"наставник {nastavnik}: потребно {cilj_sesija[kljuc]}, "
                f"распоређено {stvarne_sesije[kljuc]}"
            )

    cilj_korepeticije = Counter()
    for zahtev in ulaz.zahtevi:
        if zahtev.korepetitor:
            cilj_korepeticije[
                (zahtev.predmet, zahtev.nastavnik, zahtev.razred, zahtev.korepetitor)
            ] += zahtev.fond_korepeticije
    stvarna_korepeticija = Counter()
    for cas in casovi:
        zahtevi = pogodjeni.get(cas.red)
        if zahtevi and cas.korepetitor:
            stvarna_korepeticija[
                (cas.predmet, cas.nastavnik, zahtevi[0].razred, cas.korepetitor)
            ] += 1
    for kljuc in sorted(set(cilj_korepeticije) | set(stvarna_korepeticija), key=str):
        if cilj_korepeticije[kljuc] != stvarna_korepeticija[kljuc]:
            predmet, nastavnik, razred, korepetitor = kljuc
            izvestaj.greske.append(
                f"корепетиција за „{predmet}“, разред {razred}, наставник "
                f"{nastavnik}, корепетитор {korepetitor}: потребно "
                f"{cilj_korepeticije[kljuc]}, распоређено {stvarna_korepeticija[kljuc]}"
            )


def _proveri_sudare(ulaz: Ulaz, casovi: Sequence[Cas], izvestaj: Izvestaj) -> None:
    # Nastavnik i korepetitor su isti fizicki resurs.
    zauzeca_osoba: dict[tuple[tuple[str, int], str], list[Cas]] = defaultdict(list)
    for cas in casovi:
        zauzeca_osoba[(cas.termin, cas.nastavnik)].append(cas)
        if cas.korepetitor:
            zauzeca_osoba[(cas.termin, cas.korepetitor)].append(cas)
    for ((dan, blok), osoba), stavke in zauzeca_osoba.items():
        if len(stavke) <= 1:
            continue
        redovi = ", ".join(str(c.red) for c in stavke)
        izvestaj.greske.append(
            f"особа {osoba} је заузета више пута: {dan}, блок {blok}, редови {redovi}"
        )
    _prijavi_duple_resurse(
        casovi,
        "просторија",
        lambda c: (c.termin, c.prostorija),
        lambda c: c.prostorija,
        izvestaj,
    )

    polugrupe = defaultdict(list)
    for odeljenje in ulaz.odeljenja.values():
        if odeljenje.roditelj:
            polugrupe[odeljenje.roditelj].append(odeljenje.oznaka)

    zauzeca: dict[tuple[tuple[str, int], str], list[Cas]] = defaultdict(list)
    for cas in casovi:
        for oznaka in cas.odeljenja:
            tokeni = polugrupe.get(oznaka, [oznaka])
            for token in tokeni:
                zauzeca[(cas.termin, token)].append(cas)
    for ((dan, blok), token), stavke in zauzeca.items():
        if len(stavke) <= 1 or _dozvoljen_alternativni_preklop(stavke):
            continue
        redovi = ", ".join(str(c.red) for c in stavke)
        izvestaj.greske.append(
            f"одељење/полугрупа {token} има преклапање: {dan}, блок {blok}, "
            f"редови {redovi}"
        )


def _prijavi_duple_resurse(
    casovi: Iterable[Cas], naziv: str, kljuc, vrednost_resursa, izvestaj: Izvestaj
) -> None:
    grupe: dict[object, list[Cas]] = defaultdict(list)
    for cas in casovi:
        grupe[kljuc(cas)].append(cas)
    for stavke in grupe.values():
        if len(stavke) <= 1:
            continue
        prvi = stavke[0]
        vrednost = vrednost_resursa(prvi)
        redovi = ", ".join(str(c.red) for c in stavke)
        izvestaj.greske.append(
            f"{naziv} {vrednost} је заузет више пута: {prvi.dan}, "
            f"блок {prvi.blok}, редови {redovi}"
        )


def _dozvoljen_alternativni_preklop(casovi: Sequence[Cas]) -> bool:
    return len(casovi) == 2 and {c.predmet for c in casovi} == ALTERNATIVNI_PREDMETI


def _rasporedi_po_ucenickoj_grupi(
    ulaz: Ulaz, casovi: Sequence[Cas]
) -> dict[str, list[Cas]]:
    polugrupe = defaultdict(list)
    for odeljenje in ulaz.odeljenja.values():
        if odeljenje.roditelj:
            polugrupe[odeljenje.roditelj].append(odeljenje.oznaka)
    rezultat: dict[str, list[Cas]] = defaultdict(list)
    for cas in casovi:
        if cas.predmet not in ulaz.predmeti:
            continue
        for oznaka in cas.odeljenja:
            if oznaka not in ulaz.odeljenja:
                continue
            for token in polugrupe.get(oznaka, [oznaka]):
                rezultat[token].append(cas)
    return rezultat


def _proveri_dnevni_raspored(
    ulaz: Ulaz,
    prostorije: dict[str, Prostorija],
    casovi: Sequence[Cas],
    izvestaj: Izvestaj,
) -> None:
    for grupa, stavke in _rasporedi_po_ucenickoj_grupi(ulaz, casovi).items():
        po_danu: dict[str, list[Cas]] = defaultdict(list)
        for cas in stavke:
            po_danu[cas.dan].append(cas)
        for dan, dnevni in po_danu.items():
            po_bloku: dict[int, list[Cas]] = defaultdict(list)
            for cas in dnevni:
                po_bloku[cas.blok].append(cas)
            blokovi = sorted(po_bloku)

            if ulaz.odeljenja[grupa].skola is Skola.OSNOVNA:
                if len(blokovi) > 4:
                    izvestaj.greske.append(
                        f"{grupa} има {len(blokovi)} часова у дану {dan}; "
                        "максимум за основну школу је 4"
                    )
            elif ulaz.odeljenja[grupa].skola is Skola.SREDNJA:
                igracki = sum(
                    1
                    for blok in blokovi
                    if any(ulaz.predmeti[c.predmet].igracki for c in po_bloku[blok])
                )
                opsti = sum(
                    1
                    for blok in blokovi
                    if any(c.predmet in OPSTI_PREDMETI for c in po_bloku[blok])
                )
                if igracki > 4:
                    izvestaj.greske.append(
                        f"{grupa} има {igracki} играчких часова у дану {dan}; максимум је 4"
                    )
                if opsti > 4:
                    izvestaj.greske.append(
                        f"{grupa} има {opsti} општих часова у дану {dan}; максимум је 4"
                    )

            lokacije_po_bloku: dict[int, str] = {}
            for blok, casovi_bloka in po_bloku.items():
                lokacije = {
                    prostorije[c.prostorija].lokacija
                    for c in casovi_bloka
                    if c.prostorija in prostorije
                }
                if len(lokacije) == 1:
                    lokacije_po_bloku[blok] = next(iter(lokacije))
                elif len(lokacije) > 1:
                    izvestaj.greske.append(
                        f"{grupa} је истовремено на више локација: {dan}, блок {blok}"
                    )

            promene = 0
            for prethodni, sledeci in zip(blokovi, blokovi[1:]):
                lokacija_pre = lokacije_po_bloku.get(prethodni)
                lokacija_posle = lokacije_po_bloku.get(sledeci)
                if not lokacija_pre or not lokacija_posle:
                    continue
                menja = lokacija_pre != lokacija_posle
                razmak = sledeci - prethodni
                if menja:
                    promene += 1
                    neposredan_prelaz = {lokacija_pre, lokacija_posle} == {
                        "Кнез Милетина 8", "Спортска гимназија"
                    }
                    ocekivani_razmak = 1 if neposredan_prelaz else 2
                    if razmak < ocekivani_razmak:
                        izvestaj.greske.append(
                            f"{grupa} мења локацију без слободног блока: {dan}, "
                            f"блокови {prethodni}–{sledeci}"
                        )
                    elif razmak > ocekivani_razmak:
                        opis = (
                            "са паузом између Кнез Милетине и Спортске гимназије"
                            if neposredan_prelaz
                            else "са паузом дужом од једног блока"
                        )
                        izvestaj.greske.append(
                            f"{grupa} мења локацију {opis}: {dan}, "
                            f"блокови {prethodni}–{sledeci}"
                        )
                elif razmak > 1:
                    izvestaj.greske.append(
                        f"{grupa} има празан час без промене локације: {dan}, "
                        f"блокови {prethodni} и {sledeci}"
                    )
            if promene > 1:
                izvestaj.greske.append(
                    f"{grupa} мења локацију {promene} пута у дану {dan}; максимум је једном"
                )


def _proveri_dvocase(ulaz: Ulaz, casovi: Sequence[Cas], izvestaj: Izvestaj) -> None:
    po_predmetu_i_odeljenju: dict[tuple[str, str], list[Cas]] = defaultdict(list)
    for cas in casovi:
        for oznaka in cas.odeljenja:
            po_predmetu_i_odeljenju[(cas.predmet, oznaka)].append(cas)

    for zahtev in ulaz.zahtevi:
        if not ulaz.predmeti[zahtev.predmet].igracki:
            continue
        for oznaka in zahtev.odeljenja:
            stavke = po_predmetu_i_odeljenju[(zahtev.predmet, oznaka)]
            parovi, samostalni, predugi = _prebroj_blokove(stavke)
            odeljenje = ulaz.odeljenja[oznaka]
            glavni = (
                odeljenje.skola is Skola.SREDNJA
                and "главни предмет" in zahtev.predmet
            )
            osnovni_klasicni = (
                odeljenje.skola is Skola.OSNOVNA
                and zahtev.predmet == "Класичан балет"
                and zahtev.fond == 10
            )
            if odeljenje.skola is Skola.SREDNJA:
                if predugi:
                    izvestaj.greske.append(
                        f"„{zahtev.predmet}“ за {oznaka} има низ дужи од два часа"
                    )
                ocekivani_parovi = zahtev.fond // 2
                ocekivani_samostalni = zahtev.fond % 2
                if parovi != ocekivani_parovi or samostalni != ocekivani_samostalni:
                    izvestaj.greske.append(
                        f"„{zahtev.predmet}“ за {oznaka}: очекује се "
                        f"{ocekivani_parovi} двочаса и {ocekivani_samostalni} "
                        f"самосталних часова, пронађено {parovi} и {samostalni}"
                    )
                if glavni:
                    po_danu = Counter(c.dan for c in stavke)
                    if any(broj != 2 for broj in po_danu.values()):
                        izvestaj.greske.append(
                            f"главни предмет „{zahtev.predmet}“ за {oznaka} мора "
                            "имати тачно један двочас дневно"
                        )
            elif osnovni_klasicni:
                po_danu = Counter(c.dan for c in stavke)
                ocekivano = {dan: 2 for dan in DANI[:5]}
                if predugi or po_danu != ocekivano or parovi != 5:
                    izvestaj.greske.append(
                        f"„Класичан балет“ за {oznaka} мора имати тачно један "
                        "двочас сваког дана од понедељка до петка"
                    )
            elif predugi or parovi * 2 + samostalni != zahtev.fond:
                izvestaj.upozorenja.append(
                    f"проверити двочасе за „{zahtev.predmet}“, одељење {oznaka}"
                )


def _prebroj_blokove(casovi: Sequence[Cas]) -> tuple[int, int, bool]:
    parovi = 0
    samostalni = 0
    predugi = False
    po_danu: dict[str, list[int]] = defaultdict(list)
    for cas in casovi:
        po_danu[cas.dan].append(cas.blok)
    for blokovi in po_danu.values():
        sortirani = sorted(set(blokovi))
        nizovi: list[list[int]] = []
        for blok in sortirani:
            if nizovi and blok == nizovi[-1][-1] + 1:
                nizovi[-1].append(blok)
            else:
                nizovi.append([blok])
        for niz in nizovi:
            if len(niz) == 2:
                parovi += 1
            elif len(niz) == 1:
                samostalni += 1
            else:
                predugi = True
    return parovi, samostalni, predugi


def _proveri_versku_i_gradjansko(
    ulaz: Ulaz, casovi: Sequence[Cas], izvestaj: Izvestaj
) -> None:
    termini: dict[tuple[str, str], set[tuple[str, int]]] = defaultdict(set)
    for cas in casovi:
        if cas.predmet in ALTERNATIVNI_PREDMETI:
            for oznaka in cas.odeljenja:
                termini[(cas.predmet, oznaka)].add(cas.termin)
    ima_predmet = {
        (zahtev.predmet, oznaka)
        for zahtev in ulaz.zahtevi
        if zahtev.predmet in ALTERNATIVNI_PREDMETI
        for oznaka in zahtev.odeljenja
    }
    for oznaka in ulaz.odeljenja:
        if (VERSKA, oznaka) not in ima_predmet or (GRADJANSKO, oznaka) not in ima_predmet:
            continue
        verska = termini[(VERSKA, oznaka)]
        gradjansko = termini[(GRADJANSKO, oznaka)]
        if verska != gradjansko:
            izvestaj.greske.append(
                f"Верска настава и Грађанско васпитање за {oznaka} "
                "морају бити истовремено"
            )


def _upozori_na_pauze_nastavnika(
    casovi: Sequence[Cas], izvestaj: Izvestaj
) -> None:
    """Proveri nedeljni kontinuitet svih osoba, bez obzira na njihovu ulogu."""

    termini: dict[tuple[str, str], set[int]] = defaultdict(set)
    for cas in casovi:
        osobe = {cas.nastavnik}
        if cas.korepetitor:
            osobe.add(cas.korepetitor)
        for osoba in osobe:
            if osoba in (KOREPETITOR_BR_1, NEPOZNATI_KOREPETITOR):
                osoba = "будући корепетитор"
            termini[(osoba, cas.dan)].add(cas.blok)

    pauze_po_osobi: Counter[str] = Counter()
    for (osoba, dan), blokovi in sorted(termini.items()):
        sortirani = sorted(blokovi)
        broj_casova = len(sortirani)
        if broj_casova > 6:
            izvestaj.greske.append(
                f"особа {osoba} има {broj_casova} часова у дану {dan}; максимум је 6"
            )
        elif broj_casova > 4:
            izvestaj.upozorenja.append(
                f"особа {osoba} има {broj_casova} часова у дану {dan}; оптимално је до 4"
            )
        for prethodni, sledeci in zip(sortirani, sortirani[1:]):
            duzina = sledeci - prethodni - 1
            if duzina <= 0:
                continue
            pauze_po_osobi[osoba] += 1
            izvestaj.upozorenja.append(
                f"особа {osoba} има паузу од {duzina} блока у дану {dan} "
                f"између блокова {prethodni} и {sledeci}"
            )
            if duzina > 2 and not izuzet_od_ogranicenja_pauza(osoba):
                izvestaj.greske.append(
                    f"особа {osoba} има паузу од {duzina} блока у дану {dan}; "
                    "максимум су два блока"
                )
    for osoba, broj_pauza in sorted(pauze_po_osobi.items()):
        if broj_pauza > 1 and not izuzet_od_ogranicenja_pauza(osoba):
            izvestaj.greske.append(
                f"особа {osoba} има {broj_pauza} паузе у недељи; максимум је једна"
            )


def proveri_datoteku(
    resenje: str | Path,
    direktorijum_ulaza: str | Path = "ulazi",
    jutarnja_smena: Smena = Smena.CRVENA,
) -> Izvestaj:
    """Praktični API: učitaj standardne ulaze i proveri jednu datoteku."""

    direktorijum = Path(direktorijum_ulaza)
    try:
        ulaz = ucitaj_vise(
            [
                direktorijum / "osnovna_baletska_skola.csv",
                direktorijum / "srednja_baletska_skola.csv",
                direktorijum / "ostali_casovi.csv",
            ]
        )
        prostorije = ucitaj_prostorije(direktorijum / "prostorije.csv")
        nedostupnosti = ucitaj_nedostupnost(direktorijum / "nedostupnost.csv")
        casovi = ucitaj_resenje(resenje)
    except (UlazGreska, ResenjeGreska) as greska:
        return Izvestaj(greske=list(greska.greske))
    return proveri(ulaz, prostorije, nedostupnosti, casovi, jutarnja_smena)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Провера CSV распореда часова")
    parser.add_argument("resenje", type=Path, help="CSV датотека са решењем")
    parser.add_argument(
        "--ulazi", type=Path, default=Path("ulazi"), help="директоријум са улазима"
    )
    parser.add_argument(
        "--jutarnja-smena",
        choices=("crvena", "plava"),
        default="crvena",
        help="која наизменична смена је ујутру (подразумевано: crvena)",
    )
    argumenti = parser.parse_args(argv)
    jutarnja = Smena.CRVENA if argumenti.jutarnja_smena == "crvena" else Smena.PLAVA
    izvestaj = proveri_datoteku(argumenti.resenje, argumenti.ulazi, jutarnja)
    print(izvestaj.tekst(latinica=True))
    return 0 if izvestaj.ispravan else 1


if __name__ == "__main__":
    raise SystemExit(main())
