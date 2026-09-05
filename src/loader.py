"""Read and validate the input CSV files under ``ulazi/``.

The input is expected to be edited by hand or by an assistant and arrive through
a pull request, so validation collects *every* problem in one pass instead of
stopping at the first. A person fixing the file should see the whole list once,
not discover the next error after each round trip.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from dataclasses import replace

from .pravila_prostorija import kanonska_prostorija

from .model import (
    BLOKOVI,
    DANI,
    DostupnostProstorije,
    Nedostupnost,
    NivoPravilaProstorije,
    Odeljenje,
    Predmet,
    PraviloProstorije,
    Prostorija,
    Skola,
    Smena,
    TipProstorije,
    Ulaz,
    Zahtev,
)

KOLONE = (
    "предмет",
    "разред",
    "одељење",
    "недељни фонд часова",
    "часови корепетиције",
    "наставник",
    "корепетитор",
    "смена",
)

OSNOVNI_RAZREDI = frozenset({"припремно", "први", "други", "трећи", "четврти"})
SREDNJI_RAZREDI = frozenset({"I", "II", "III", "IV"})

SMENE = {
    "црвена смена": Smena.CRVENA,
    "плава смена": Smena.PLAVA,
    "стално послеподне": Smena.STALNO_POPODNE,
    "цео дан": Smena.CEO_DAN,
}

#: Subjects that need a sala although no korepetitor plays on them.
SALA_BEZ_KOREPETITORA = frozenset({"Репертоар савремене игре", "Игре XX века"})

#: Half-group suffixes: ``I5А`` and ``I5Б`` are halves of ``I5``.
POLUGRUPA_SUFIKSI = ("А", "Б")

#: Free-text shift descriptions start with this and need a hand-written rule.
POSEBNA_SMENA_PREFIKS = "стално од"


class UlazGreska(ValueError):
    """Raised when the input file cannot be used, carrying every problem found."""

    def __init__(self, greske: Iterable[str]) -> None:
        self.greske = list(greske)
        naslov = f"Улаз није исправан ({_oblik_greske(len(self.greske))}):"
        super().__init__("\n".join([naslov, *(f"  - {g}" for g in self.greske)]))


def ucitaj(putanja: str | Path, skola: Skola | None = None) -> Ulaz:
    """Parse one input CSV into a validated :class:`Ulaz`.

    Raises :class:`UlazGreska` listing every problem when the file is unusable.
    """
    return ucitaj_vise([putanja], skola)


def ucitaj_vise(putanje: Iterable[str | Path], skola: Skola | None = None) -> Ulaz:
    """Parse several input CSVs into one validated :class:`Ulaz`.

    The whole institution is one scheduling problem — the two schools share
    teachers, korepetitori and rooms — so the files are merged and validated
    together. With more than one file, error messages carry the file name.
    """
    putanje = [Path(putanja) for putanja in putanje]
    vise = len(putanje) > 1
    greske: list[str] = []
    zahtevi: list[Zahtev] = []
    for putanja in putanje:
        oznaka = putanja.name if vise else ""
        prefiks = f"{oznaka}: " if oznaka else ""
        try:
            redovi = _procitaj_redove(putanja)
        except UlazGreska as greska:
            greske.extend(prefiks + poruka for poruka in greska.greske)
            continue
        lokalne: list[str] = []
        for pomeraj, red in enumerate(redovi, start=2):
            zahtev = _procitaj_red(red, pomeraj, lokalne)
            if zahtev:
                zahtevi.append(replace(zahtev, datoteka=oznaka))
        greske.extend(prefiks + poruka for poruka in lokalne)

    odeljenja = _sastavi_odeljenja(zahtevi, skola, greske)
    predmeti = _sastavi_predmete(zahtevi, greske)
    _proveri_duplikate(zahtevi, greske)

    if greske:
        raise UlazGreska(greske)

    return Ulaz(
        zahtevi=tuple(zahtevi),
        odeljenja=odeljenja,
        predmeti=predmeti,
        skola=skola or _pogodi_skolu(zahtevi),
    )


def _procitaj_redove(putanja: Path, kolone: tuple[str, ...] = KOLONE) -> list[dict]:
    """Read one CSV, check the header, and return stripped rows."""
    # utf-8-sig: spreadsheet tools and assistants routinely prepend a BOM.
    with putanja.open(encoding="utf-8-sig", newline="") as datoteka:
        citac = csv.DictReader(datoteka)
        zaglavlje = [(ime or "").strip() for ime in (citac.fieldnames or [])]
        nedostaju = [kolona for kolona in kolone if kolona not in zaglavlje]
        if nedostaju:
            raise UlazGreska(
                [f"недостаје колона „{kolona}“" for kolona in nedostaju]
            )
        redovi = [
            {(k or "").strip(): (v or "").strip() for k, v in red.items() if k}
            for red in citac
        ]
    if not redovi:
        raise UlazGreska(["датотека нема ниједан ред са подацима"])
    return redovi


def _procitaj_red(
    red: dict[str, Any], broj_reda: int, greske: list[str]
) -> Zahtev | None:
    """Turn one CSV row into a Zahtev, appending any problems to ``greske``."""
    pocetni_broj_gresaka = len(greske)

    def obavezno(kolona: str) -> str:
        vrednost = red.get(kolona, "")
        if not vrednost:
            greske.append(f"ред {broj_reda}: „{kolona}“ не сме бити празно")
        return vrednost

    predmet = obavezno("предмет")
    razred = obavezno("разред")
    sirovo_odeljenje = obavezno("одељење")
    nastavnik = obavezno("наставник")

    odeljenja = tuple(
        deo.strip() for deo in sirovo_odeljenje.split(",") if deo.strip()
    )
    if sirovo_odeljenje and not odeljenja:
        greske.append(f"ред {broj_reda}: „одељење“ не садржи ниједну ознаку")

    fond = _ceo_broj(red.get("недељни фонд часова", ""), "недељни фонд часова",
                     broj_reda, greske, obavezan=True)
    fond_korepeticije = _ceo_broj(red.get("часови корепетиције", ""),
                                  "часови корепетиције", broj_reda, greske)
    korepetitor = red.get("корепетитор", "") or None

    if fond is not None and fond_korepeticije is not None:
        if fond_korepeticije > fond:
            greske.append(
                f"ред {broj_reda}: часова корепетиције ({fond_korepeticije}) "
                f"има више него часова ({fond})"
            )
    if korepetitor and fond_korepeticije == 0:
        greske.append(
            f"ред {broj_reda}: наведен је корепетитор „{korepetitor}“, "
            "а часова корепетиције је 0"
        )
    if not korepetitor and (fond_korepeticije or 0) > 0:
        greske.append(
            f"ред {broj_reda}: има {fond_korepeticije} часова корепетиције, "
            "а корепетитор није наведен"
        )

    sirova_smena = obavezno("смена")
    smena = _procitaj_smenu(sirova_smena, broj_reda, greske)

    if len(greske) > pocetni_broj_gresaka:
        return None

    return Zahtev(
        predmet=predmet,
        razred=razred,
        odeljenja=odeljenja,
        fond=fond or 0,
        fond_korepeticije=fond_korepeticije or 0,
        nastavnik=nastavnik,
        korepetitor=korepetitor,
        smena=smena or Smena.POSEBNA,
        smena_opis=sirova_smena,
        red=broj_reda,
    )


def _ceo_broj(
    vrednost: str,
    kolona: str,
    broj_reda: int,
    greske: list[str],
    obavezan: bool = False,
    proveri_pozitivnost: bool = True,
) -> int | None:
    """Parse a non-negative integer cell; empty means zero unless required."""
    if not vrednost:
        if obavezan:
            greske.append(f"ред {broj_reda}: „{kolona}“ не сме бити празно")
            return None
        return 0
    try:
        broj = int(vrednost)
    except ValueError:
        greske.append(
            f"ред {broj_reda}: „{kolona}“ мора бити цео број, а пише „{vrednost}“"
        )
        return None
    if proveri_pozitivnost and (broj < 0 or (obavezan and broj == 0)):
        greske.append(f"ред {broj_reda}: „{kolona}“ мора бити већи од нуле")
        return None
    return broj


def _procitaj_smenu(
    vrednost: str, broj_reda: int, greske: list[str]
) -> Smena | None:
    if not vrednost:
        return None
    if vrednost in SMENE:
        return SMENE[vrednost]
    if vrednost.startswith(POSEBNA_SMENA_PREFIKS):
        return Smena.POSEBNA
    dozvoljene = ", ".join(f"„{ime}“" for ime in SMENE)
    greske.append(
        f"ред {broj_reda}: непозната смена „{vrednost}“; дозвољено је {dozvoljene} "
        f"или опис који почиње са „{POSEBNA_SMENA_PREFIKS}“"
    )
    return None


def _sastavi_odeljenja(
    zahtevi: list[Zahtev], skola: Skola | None, greske: list[str]
) -> dict[str, Odeljenje]:
    """Collect groups, checking each keeps one shift and one razred throughout."""
    smene: dict[str, tuple[Smena, int]] = {}
    razredi: dict[str, tuple[str, int]] = {}
    odeljenja: dict[str, Odeljenje] = {}
    for zahtev in zahtevi:
        for oznaka in zahtev.odeljenja:
            ranije_smena = smene.get(oznaka)
            if ranije_smena and ranije_smena[0] is not zahtev.smena:
                greske.append(
                    f"{zahtev.gde}: одељење {oznaka} је у смени "
                    f"„{zahtev.smena.value}“, а у {ranije_smena[1]} "
                    f"у „{ranije_smena[0].value}“"
                )
            else:
                smene.setdefault(oznaka, (zahtev.smena, zahtev.gde))
            ranije_razred = razredi.get(oznaka)
            if ranije_razred and ranije_razred[0] != zahtev.razred:
                greske.append(
                    f"{zahtev.gde}: одељење {oznaka} је у разреду "
                    f"„{zahtev.razred}“, а у {ranije_razred[1]} "
                    f"у „{ranije_razred[0]}“"
                )
            else:
                razredi.setdefault(oznaka, (zahtev.razred, zahtev.gde))
            odeljenja[oznaka] = Odeljenje(
                oznaka=oznaka,
                razred=razredi[oznaka][0],
                smena=smene[oznaka][0],
                skola=skola or _skola_za_razred(zahtev.razred),
            )
    return _povezi_polugrupe(dict(sorted(odeljenja.items())), greske)


def _povezi_polugrupe(
    odeljenja: dict[str, Odeljenje], greske: list[str]
) -> dict[str, Odeljenje]:
    """Link ``I5А``/``I5Б`` to ``I5`` and check the halves match the whole."""
    for oznaka, odeljenje in odeljenja.items():
        if not oznaka.endswith(POLUGRUPA_SUFIKSI):
            continue
        cela = odeljenja.get(oznaka[:-1])
        if cela is None:
            continue
        if cela.razred != odeljenje.razred or cela.smena is not odeljenje.smena:
            greske.append(
                f"полугрупа {oznaka} се не слаже са одељењем {cela.oznaka} "
                f"(разред „{odeljenje.razred}“/„{cela.razred}“, смена "
                f"„{odeljenje.smena.value}“/„{cela.smena.value}“)"
            )
        odeljenja[oznaka] = replace(odeljenje, roditelj=cela.oznaka)
    return odeljenja


def _sastavi_predmete(zahtevi: list[Zahtev], greske: list[str]) -> dict[str, Predmet]:
    """Derive igrački/opšti per subject and flag subjects that mix the two."""
    sa_korepetitorom: dict[str, list[str]] = defaultdict(list)
    bez_korepetitora: dict[str, list[str]] = defaultdict(list)
    for zahtev in zahtevi:
        cilj = sa_korepetitorom if zahtev.korepetitor else bez_korepetitora
        cilj[zahtev.predmet].append(zahtev.gde)

    predmeti: dict[str, Predmet] = {}
    for naziv in sorted({z.predmet for z in zahtevi}):
        sa = sa_korepetitorom.get(naziv, [])
        bez = bez_korepetitora.get(naziv, [])
        if sa and bez and naziv not in SALA_BEZ_KOREPETITORA:
            greske.append(
                f"предмет „{naziv}“ негде има корепетитора ({_spisak(sa)}), "
                f"а негде нема ({_spisak(bez)})"
            )
        igracki = bool(sa)
        predmeti[naziv] = Predmet(
            naziv=naziv,
            igracki=igracki,
            trazi_salu=igracki or naziv in SALA_BEZ_KOREPETITORA,
        )
    return predmeti


def _proveri_duplikate(zahtevi: list[Zahtev], greske: list[str]) -> None:
    """A group should appear at most once per subject."""
    vidjeno: dict[tuple[str, str], str] = {}
    for zahtev in zahtevi:
        for oznaka in zahtev.odeljenja:
            kljuc = (zahtev.predmet, oznaka)
            if kljuc in vidjeno:
                greske.append(
                    f"{zahtev.gde}: предмет „{zahtev.predmet}“ за одељење "
                    f"{oznaka} већ постоји ({vidjeno[kljuc]})"
                )
            else:
                vidjeno[kljuc] = zahtev.gde


def _oblik_greske(broj: int) -> str:
    """Serbian counts by the last digit, with 11-14 as the exception."""
    poslednja = broj % 10
    poslednje_dve = broj % 100
    if poslednja == 1 and poslednje_dve != 11:
        return f"{broj} грешка"
    if poslednja in (2, 3, 4) and poslednje_dve not in (12, 13, 14):
        return f"{broj} грешке"
    return f"{broj} грешака"


def _spisak(mesta: list[str]) -> str:
    return ", ".join(mesta)


def _skola_za_razred(razred: str) -> Skola:
    return Skola.SREDNJA if razred in SREDNJI_RAZREDI else Skola.OSNOVNA


def _pogodi_skolu(zahtevi: list[Zahtev]) -> Skola | None:
    razredi = {zahtev.razred for zahtev in zahtevi}
    if razredi <= SREDNJI_RAZREDI:
        return Skola.SREDNJA
    if razredi <= OSNOVNI_RAZREDI:
        return Skola.OSNOVNA
    return None


KOLONE_PROSTORIJA = ("ознака", "локација", "тип", "приоритет", "напомена")


def ucitaj_prostorije(putanja: str | Path) -> tuple[Prostorija, ...]:
    """Parse the room list, or raise :class:`UlazGreska` with every problem."""
    redovi = _procitaj_redove(Path(putanja), KOLONE_PROSTORIJA)
    greske: list[str] = []
    prostorije: list[Prostorija] = []
    vidjeno: dict[str, int] = {}
    tipovi = {tip.value: tip for tip in TipProstorije}
    for broj_reda, red in enumerate(redovi, start=2):
        pocetni_broj_gresaka = len(greske)
        oznaka = kanonska_prostorija(red["ознака"])
        if not oznaka:
            greske.append(f"ред {broj_reda}: „ознака“ не сме бити празно")
        elif oznaka in vidjeno:
            greske.append(
                f"ред {broj_reda}: просторија {oznaka} већ постоји "
                f"у реду {vidjeno[oznaka]}"
            )
        else:
            vidjeno[oznaka] = broj_reda
        tip = tipovi.get(red["тип"])
        if tip is None:
            dozvoljeni = ", ".join(f"„{ime}“" for ime in tipovi)
            greske.append(
                f"ред {broj_reda}: непознат тип „{red['тип']}“; "
                f"дозвољено је {dozvoljeni}"
            )
        prioritet = None
        if red["приоритет"]:
            prioritet = _ceo_broj(red["приоритет"], "приоритет", broj_reda, greske)
        if len(greske) > pocetni_broj_gresaka:
            continue
        prostorije.append(
            Prostorija(
                oznaka=oznaka,
                lokacija=red["локација"],
                tip=tip,
                prioritet=prioritet,
                napomena=red["напомена"],
            )
        )
    if greske:
        raise UlazGreska(greske)
    return tuple(prostorije)


KOLONE_PRAVILA_PROSTORIJA = (
    "просторија", "ниво", "предмет", "одељења", "облик часа", "напомена",
)
DOZVOLJENI_OBLICI_CASA = frozenset({"", "двочас"})
ODELJENJE_RE = re.compile(r"^(?:П1|[1-4][1-5]|(?:I|II|III|IV)[1-5](?:[АБ])?)$")


def ucitaj_pravila_prostorija(
    putanja: str | Path,
) -> tuple[PraviloProstorije, ...]:
    """Učitaj atomska pravila prostorija i prijavi sve greške odjednom."""

    redovi = _procitaj_redove(Path(putanja), KOLONE_PRAVILA_PROSTORIJA)
    greske: list[str] = []
    pravila: list[PraviloProstorije] = []
    vidjeno: dict[tuple[object, ...], int] = {}
    nivoi = {nivo.value: nivo for nivo in NivoPravilaProstorije}
    for broj_reda, red in enumerate(redovi, start=2):
        pocetni_broj_gresaka = len(greske)
        prostorija = kanonska_prostorija(red["просторија"])
        predmet = " ".join(red["предмет"].split())
        if not prostorija:
            greske.append(f"ред {broj_reda}: „просторија“ не сме бити празно")
        if not predmet:
            greske.append(f"ред {broj_reda}: „предмет“ не сме бити празно")
        elif ";" in predmet:
            greske.append(
                f"ред {broj_reda}: „предмет“ мора садржати један канонски "
                "назив, без листе раздвојене тачком и запетом"
            )
        sirovi_nivo = red["ниво"]
        nivo = nivoi.get(sirovi_nivo)
        if nivo is None:
            greske.append(
                f"ред {broj_reda}: непознат ниво „{sirovi_nivo}“; дозвољено је "
                + ", ".join(f"„{ime}“" for ime in nivoi)
            )
        sirova_odeljenja = red["одељења"]
        odeljenja: tuple[str, ...] = ()
        if sirova_odeljenja:
            delovi = tuple(deo.strip() for deo in sirova_odeljenja.split(","))
            if any(not deo for deo in delovi):
                greske.append(f"ред {broj_reda}: „одељења“ има празну ознаку")
            nepoznata = [deo for deo in delovi if deo and not ODELJENJE_RE.fullmatch(deo)]
            if nepoznata:
                greske.append(
                    f"ред {broj_reda}: неисправна ознака одељења "
                    + ", ".join(f"„{oznaka}“" for oznaka in nepoznata)
                )
            if len(set(delovi)) != len(delovi):
                greske.append(f"ред {broj_reda}: „одељења“ садрже дуплу ознаку")
            odeljenja = tuple(deo for deo in delovi if deo)
        oblik = red["облик часа"]
        if oblik not in DOZVOLJENI_OBLICI_CASA:
            greske.append(
                f"ред {broj_reda}: непознат облик часа „{oblik}“; "
                "дозвољено је празно или „двочас“"
            )
        kljuc = (
            prostorija, nivo.value if nivo else sirovi_nivo, predmet,
            oblik or "", tuple(sorted(set(odeljenja))),
        )
        if kljuc in vidjeno:
            greske.append(
                f"ред {broj_reda}: правило већ постоји у реду {vidjeno[kljuc]}"
            )
        else:
            vidjeno[kljuc] = broj_reda
        if len(greske) > pocetni_broj_gresaka:
            continue
        pravila.append(PraviloProstorije(
            prostorija, nivo, predmet, odeljenja, oblik or None, red["напомена"]
        ))
    if greske:
        raise UlazGreska(greske)
    return tuple(pravila)


KOLONE_DOSTUPNOSTI_PROSTORIJA = (
    "просторија", "дан", "од блока", "до блока", "напомена",
)


def ucitaj_dostupnost_prostorija(
    putanja: str | Path,
) -> tuple[DostupnostProstorije, ...]:
    """Učitaj whitelist opsege dostupnosti prostorija."""

    redovi = _procitaj_redove(Path(putanja), KOLONE_DOSTUPNOSTI_PROSTORIJA)
    greske: list[str] = []
    rezultat: list[DostupnostProstorije] = []
    vidjeno: dict[tuple[str, str, str, str], int] = {}
    for broj_reda, red in enumerate(redovi, start=2):
        pocetni_broj_gresaka = len(greske)
        prostorija = kanonska_prostorija(red["просторија"])
        if not prostorija:
            greske.append(f"ред {broj_reda}: „просторија“ не сме бити празно")
        dan = red["дан"]
        if dan not in DANI:
            greske.append(
                f"ред {broj_reda}: непознат дан „{dan}“; дозвољено је {', '.join(DANI)}"
            )
        od_bloka = _ceo_broj(
            red["од блока"], "од блока", broj_reda, greske,
            obavezan=True, proveri_pozitivnost=False,
        )
        do_bloka = _ceo_broj(
            red["до блока"], "до блока", broj_reda, greske,
            obavezan=True, proveri_pozitivnost=False,
        )
        for kolona, broj in (("од блока", od_bloka), ("до блока", do_bloka)):
            if broj is not None and not 1 <= broj <= len(BLOKOVI):
                greske.append(
                    f"ред {broj_reda}: „{kolona}“ мора бити између 1 и "
                    f"{len(BLOKOVI)}, а пише {broj}"
                )
        if od_bloka is not None and do_bloka is not None and od_bloka > do_bloka:
            greske.append(
                f"ред {broj_reda}: „од блока“ ({od_bloka}) мора бити мање "
                f"или једнако „до блока“ ({do_bloka})"
            )
        kljuc = (prostorija, dan, red["од блока"], red["до блока"])
        if kljuc in vidjeno:
            greske.append(
                f"ред {broj_reda}: доступност већ постоји у реду {vidjeno[kljuc]}"
            )
        else:
            vidjeno[kljuc] = broj_reda
        if len(greske) > pocetni_broj_gresaka:
            continue
        rezultat.append(DostupnostProstorije(
            prostorija, dan, od_bloka, do_bloka, red["напомена"]
        ))
    if greske:
        raise UlazGreska(greske)
    return tuple(rezultat)


def proveri_veze_pravila_prostorija(
    ulaz: Ulaz,
    prostorije: Iterable[Prostorija],
    pravila: Iterable[PraviloProstorije],
    dostupnosti: Iterable[DostupnostProstorije],
) -> None:
    """Proveri reference tek kada su učitani svi standardni ulazi."""

    greske: list[str] = []
    oznake_soba = {p.oznaka for p in prostorije}
    pravila = tuple(pravila)
    for pravilo in pravila:
        if pravilo.prostorija not in oznake_soba:
            greske.append(
                f"правило просторија: непозната просторија „{pravilo.prostorija}“"
            )
        if pravilo.predmet != "*" and pravilo.predmet not in ulaz.predmeti:
            greske.append(
                f"правило просторија: непознат предмет „{pravilo.predmet}“"
            )
        for odeljenje in pravilo.odeljenja:
            if odeljenje not in ulaz.odeljenja:
                greske.append(
                    f"правило просторија: непознато одељење „{odeljenje}“"
                )
    for dostupnost in dostupnosti:
        if dostupnost.prostorija not in oznake_soba:
            greske.append(
                "доступност просторија: непозната просторија "
                f"„{dostupnost.prostorija}“"
            )
    kanonski_nivoi: dict[tuple[object, ...], set[NivoPravilaProstorije]] = defaultdict(set)
    for pravilo in pravila:
        kljuc = (
            pravilo.prostorija,
            pravilo.predmet,
            pravilo.odeljenja,
            pravilo.oblik_casa,
        )
        kanonski_nivoi[kljuc].add(pravilo.nivo)
    for (soba, predmet, odeljenja, oblik), nivoi in kanonski_nivoi.items():
        if len(nivoi) > 1:
            greske.append(
                f"правила просторија: противречни нивои за {soba}, "
                f"„{predmet}“, {odeljenja or 'сва одељења'}, {oblik or 'сваки облик'}"
            )
    if greske:
        raise UlazGreska(dict.fromkeys(greske))


KOLONE_NEDOSTUPNOSTI = ("наставник", "дан", "од блока", "до блока", "напомена")


def ucitaj_nedostupnost(putanja: str | Path) -> tuple[Nedostupnost, ...]:
    """Parse teacher unavailability; an empty file means everyone is available."""
    putanja = Path(putanja)
    try:
        redovi = _procitaj_redove(putanja, KOLONE_NEDOSTUPNOSTI)
    except UlazGreska as greska:
        if greska.greske == ["датотека нема ниједан ред са подацима"]:
            return ()
        raise
    greske: list[str] = []
    stavke: list[Nedostupnost] = []
    for broj_reda, red in enumerate(redovi, start=2):
        pocetni_broj_gresaka = len(greske)
        nastavnik = red["наставник"]
        if not nastavnik:
            greske.append(f"ред {broj_reda}: „наставник“ не сме бити празно")
        dan = red["дан"]
        if dan not in DANI:
            dozvoljeni = ", ".join(DANI)
            greske.append(
                f"ред {broj_reda}: непознат дан „{dan}“; дозвољено је {dozvoljeni}"
            )
        od_bloka = _ceo_broj(red["од блока"], "од блока", broj_reda, greske,
                             obavezan=True)
        do_bloka = _ceo_broj(red["до блока"], "до блока", broj_reda, greske,
                             obavezan=True)
        if od_bloka and do_bloka:
            if not (1 <= od_bloka <= do_bloka <= len(BLOKOVI)):
                greske.append(
                    f"ред {broj_reda}: блокови {od_bloka}–{do_bloka} нису "
                    f"растући опсег између 1 и {len(BLOKOVI)}"
                )
        if len(greske) > pocetni_broj_gresaka:
            continue
        stavke.append(
            Nedostupnost(
                nastavnik=nastavnik,
                dan=dan,
                od_bloka=od_bloka,
                do_bloka=do_bloka,
                napomena=red["напомена"],
            )
        )
    if greske:
        raise UlazGreska(greske)
    return tuple(stavke)
