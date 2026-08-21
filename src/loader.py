"""Read and validate the input CSV files under ``ulazi/``.

The input is expected to be edited by hand or by an assistant and arrive through
a pull request, so validation collects *every* problem in one pass instead of
stopping at the first. A person fixing the file should see the whole list once,
not discover the next error after each round trip.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .model import Odeljenje, Predmet, Skola, Smena, Ulaz, Zahtev

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
}

#: Free-text shift descriptions start with this and need a hand-written rule.
POSEBNA_SMENA_PREFIKS = "стално од"


class UlazGreska(ValueError):
    """Raised when the input file cannot be used, carrying every problem found."""

    def __init__(self, greske: Iterable[str]) -> None:
        self.greske = list(greske)
        naslov = f"Улаз није исправан ({_oblik_greske(len(self.greske))}):"
        super().__init__("\n".join([naslov, *(f"  - {g}" for g in self.greske)]))


def ucitaj(putanja: str | Path, skola: Skola | None = None) -> Ulaz:
    """Parse an input CSV into a validated :class:`Ulaz`.

    Raises :class:`UlazGreska` listing every problem when the file is unusable.
    """
    putanja = Path(putanja)
    # utf-8-sig: spreadsheet tools and assistants routinely prepend a BOM.
    with putanja.open(encoding="utf-8-sig", newline="") as datoteka:
        citac = csv.DictReader(datoteka)
        zaglavlje = [(ime or "").strip() for ime in (citac.fieldnames or [])]
        nedostaju = [kolona for kolona in KOLONE if kolona not in zaglavlje]
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

    greske: list[str] = []
    zahtevi: list[Zahtev] = []
    for pomeraj, red in enumerate(redovi, start=2):
        zahtev = _procitaj_red(red, pomeraj, greske)
        if zahtev:
            zahtevi.append(zahtev)

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
    if broj < 0 or (obavezan and broj == 0):
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
                    f"ред {zahtev.red}: одељење {oznaka} је у смени "
                    f"„{zahtev.smena.value}“, а у реду {ranije_smena[1]} "
                    f"у „{ranije_smena[0].value}“"
                )
            else:
                smene.setdefault(oznaka, (zahtev.smena, zahtev.red))
            ranije_razred = razredi.get(oznaka)
            if ranije_razred and ranije_razred[0] != zahtev.razred:
                greske.append(
                    f"ред {zahtev.red}: одељење {oznaka} је у разреду "
                    f"„{zahtev.razred}“, а у реду {ranije_razred[1]} "
                    f"у „{ranije_razred[0]}“"
                )
            else:
                razredi.setdefault(oznaka, (zahtev.razred, zahtev.red))
            odeljenja[oznaka] = Odeljenje(
                oznaka=oznaka,
                razred=razredi[oznaka][0],
                smena=smene[oznaka][0],
                skola=skola or _skola_za_razred(zahtev.razred),
            )
    return dict(sorted(odeljenja.items()))


def _sastavi_predmete(zahtevi: list[Zahtev], greske: list[str]) -> dict[str, Predmet]:
    """Derive igrački/opšti per subject and flag subjects that mix the two."""
    sa_korepetitorom: dict[str, list[int]] = defaultdict(list)
    bez_korepetitora: dict[str, list[int]] = defaultdict(list)
    for zahtev in zahtevi:
        cilj = sa_korepetitorom if zahtev.korepetitor else bez_korepetitora
        cilj[zahtev.predmet].append(zahtev.red)

    predmeti: dict[str, Predmet] = {}
    for naziv in sorted({z.predmet for z in zahtevi}):
        sa = sa_korepetitorom.get(naziv, [])
        bez = bez_korepetitora.get(naziv, [])
        if sa and bez:
            greske.append(
                f"предмет „{naziv}“ негде има корепетитора (редови "
                f"{_spisak(sa)}), а негде нема (редови {_spisak(bez)})"
            )
        predmeti[naziv] = Predmet(naziv=naziv, igracki=bool(sa))
    return predmeti


def _proveri_duplikate(zahtevi: list[Zahtev], greske: list[str]) -> None:
    """A group should appear at most once per subject."""
    vidjeno: dict[tuple[str, str], int] = {}
    for zahtev in zahtevi:
        for oznaka in zahtev.odeljenja:
            kljuc = (zahtev.predmet, oznaka)
            if kljuc in vidjeno:
                greske.append(
                    f"ред {zahtev.red}: предмет „{zahtev.predmet}“ за одељење "
                    f"{oznaka} већ постоји у реду {vidjeno[kljuc]}"
                )
            else:
                vidjeno[kljuc] = zahtev.red


def _oblik_greske(broj: int) -> str:
    """Serbian counts by the last digit, with 11-14 as the exception."""
    poslednja = broj % 10
    poslednje_dve = broj % 100
    if poslednja == 1 and poslednje_dve != 11:
        return f"{broj} грешка"
    if poslednja in (2, 3, 4) and poslednje_dve not in (12, 13, 14):
        return f"{broj} грешке"
    return f"{broj} грешака"


def _spisak(redovi: list[int]) -> str:
    return ", ".join(str(broj) for broj in sorted(redovi))


def _skola_za_razred(razred: str) -> Skola:
    return Skola.SREDNJA if razred in SREDNJI_RAZREDI else Skola.OSNOVNA


def _pogodi_skolu(zahtevi: list[Zahtev]) -> Skola:
    razredi = {zahtev.razred for zahtev in zahtevi}
    return Skola.SREDNJA if razredi <= SREDNJI_RAZREDI else Skola.OSNOVNA
