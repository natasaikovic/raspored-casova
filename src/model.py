"""Domain model for the ballet school timetable.

Code structure is English, domain nouns stay Serbian (smena, odeljenje, fond,
korepetitor) so that types map one-to-one onto the input CSV columns and
``docs/pravila-rasporeda.md``. Messages shown to the user are Cyrillic, because
the person reading them reads the schedule, not the code.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum


class Skola(Enum):
    """Which of the two schools a group belongs to."""

    OSNOVNA = "основна"
    SREDNJA = "средња"


class Smena(Enum):
    """Shift a group attends.

    ``CRVENA`` and ``PLAVA`` swap every week: one is in the morning window while
    the other is in the afternoon window. ``STALNO_POPODNE`` never swaps.
    ``CEO_DAN`` is the srednja škola, which has no shifts and may use any block.
    ``POSEBNA`` marks a group whose availability is written as free text in the
    input and needs a hand-written rule (currently only П1).
    """

    CRVENA = "црвена смена"
    PLAVA = "плава смена"
    STALNO_POPODNE = "стално послеподне"
    CEO_DAN = "цео дан"
    POSEBNA = "посебна"

    @property
    def menja_se(self) -> bool:
        """True when the group alternates between morning and afternoon."""
        return self in (Smena.CRVENA, Smena.PLAVA)


@dataclass(frozen=True)
class Blok:
    """One teaching block within a day."""

    broj: int
    pocetak: str
    kraj: str

    def __str__(self) -> str:
        return f"{self.pocetak} - {self.kraj}"


BLOKOVI: tuple[Blok, ...] = (
    Blok(1, "08:00", "08:45"),
    Blok(2, "08:50", "09:35"),
    Blok(3, "09:45", "10:30"),
    Blok(4, "10:35", "11:20"),
    Blok(5, "11:40", "12:25"),
    Blok(6, "12:30", "13:15"),
    Blok(7, "13:30", "14:15"),
    Blok(8, "14:20", "15:05"),
    Blok(9, "15:15", "16:00"),
    Blok(10, "16:00", "16:45"),
    Blok(11, "16:55", "17:40"),
    Blok(12, "17:40", "18:25"),
    Blok(13, "18:30", "19:15"),
    Blok(14, "19:15", "20:00"),
)

DANI: tuple[str, ...] = (
    "понедељак",
    "уторак",
    "среда",
    "четвртак",
    "петак",
    "субота",
)

#: Blocks belonging to the morning shift (08:00-11:20).
PRVA_SMENA: tuple[int, ...] = (1, 2, 3, 4)

#: Blocks belonging to the afternoon shift (15:15-20:00).
DRUGA_SMENA: tuple[int, ...] = (9, 10, 11, 12, 13, 14)


@dataclass(frozen=True)
class Odeljenje:
    """A class group; the unit that attends lessons together.

    ``roditelj`` links a half-group (``I5А``/``I5Б``) to its full group
    (``I5``): the same children, so the halves must never overlap in time with
    the full group's lessons.
    """

    oznaka: str
    razred: str
    smena: Smena
    skola: Skola
    roditelj: str | None = None


@dataclass(frozen=True)
class Predmet:
    """A subject, classified by accompanist and by the room it needs.

    In osnovna the two coincide: igrački predmeti have a korepetitor and need a
    sala. Srednja breaks the shortcut — Репертоар савремене игре and Игре XX
    века need a sala but have no korepetitor — so ``trazi_salu`` is stored
    separately instead of derived.
    """

    naziv: str
    igracki: bool
    trazi_salu: bool


class TipProstorije(Enum):
    SALA = "сала"
    UCIONICA = "учионица"


@dataclass(frozen=True)
class Prostorija:
    """A room: sala for dance subjects, učionica for everything else."""

    oznaka: str
    lokacija: str
    tip: TipProstorije
    prioritet: int | None
    napomena: str


class NivoPravilaProstorije(Enum):
    """Jačina strukturisanog pravila prostorije."""

    OBAVEZNO = "обавезно"
    PRVI = "први"
    DRUGI = "други"
    IZUZETNO = "изузетно"
    ZABRANJENO = "забрањено"


@dataclass(frozen=True)
class PraviloProstorije:
    """Jedno atomsko pravilo za predmet, odeljenje i oblik časa."""

    prostorija: str
    nivo: NivoPravilaProstorije
    predmet: str
    odeljenja: tuple[str, ...]
    oblik_casa: str | None
    napomena: str


@dataclass(frozen=True)
class DostupnostProstorije:
    """Uključivi opseg blokova u kome je prostorija dostupna."""

    prostorija: str
    dan: str
    od_bloka: int
    do_bloka: int
    napomena: str


@dataclass(frozen=True)
class Nedostupnost:
    """A block range in a day when a teacher cannot be scheduled."""

    nastavnik: str
    dan: str
    od_bloka: int
    do_bloka: int
    napomena: str


@dataclass(frozen=True)
class Zahtev:
    """One input row: a subject some group needs, so many periods per week."""

    predmet: str
    razred: str
    odeljenja: tuple[str, ...]
    fond: int
    fond_korepeticije: int
    nastavnik: str
    korepetitor: str | None
    smena: Smena
    smena_opis: str
    red: int
    datoteka: str = ""

    @property
    def gde(self) -> str:
        """Where this row lives, for error messages spanning several files."""
        if self.datoteka:
            return f"{self.datoteka}, ред {self.red}"
        return f"ред {self.red}"

    @property
    def zajednicki(self) -> bool:
        """True when one lesson serves several groups at once (opšti predmeti)."""
        return len(self.odeljenja) > 1


@dataclass(frozen=True)
class Ulaz:
    """A parsed and validated input file."""

    zahtevi: tuple[Zahtev, ...]
    odeljenja: dict[str, Odeljenje]
    predmeti: dict[str, Predmet]
    #: None when the input mixes both schools (the usual, whole-institution case).
    skola: Skola | None
    pravila_prostorija: tuple[PraviloProstorije, ...] = ()
    dostupnost_prostorija: tuple[DostupnostProstorije, ...] = ()

    @property
    def ukupno_casova(self) -> int:
        """Total periods that have to be placed in a week."""
        return sum(zahtev.fond for zahtev in self.zahtevi)

    @property
    def nastavnici(self) -> frozenset[str]:
        return frozenset(zahtev.nastavnik for zahtev in self.zahtevi)

    @property
    def korepetitori(self) -> frozenset[str]:
        return frozenset(
            zahtev.korepetitor for zahtev in self.zahtevi if zahtev.korepetitor
        )

    def opterecenje_nastavnika(self) -> dict[str, int]:
        """Weekly teaching hours per teacher, busiest first."""
        return self._po_osobi(lambda z: (z.nastavnik, z.fond))

    def opterecenje_korepetitora(self) -> dict[str, int]:
        """Weekly accompanying hours per accompanist, busiest first."""
        return self._po_osobi(
            lambda z: (z.korepetitor, z.fond_korepeticije) if z.korepetitor else None
        )

    def opterecenje_odeljenja(self) -> dict[str, int]:
        """Weekly periods per group."""
        ukupno: dict[str, int] = defaultdict(int)
        for zahtev in self.zahtevi:
            for oznaka in zahtev.odeljenja:
                ukupno[oznaka] += zahtev.fond
        return dict(sorted(ukupno.items()))

    def smene_nastavnika(self) -> dict[str, frozenset[Smena]]:
        """Shifts each teacher is pulled into by the groups they teach.

        A teacher whose groups all alternate is bound by the four-block morning
        window every other week; one spanning several shifts works both windows.
        """
        smene: dict[str, set[Smena]] = defaultdict(set)
        for zahtev in self.zahtevi:
            smene[zahtev.nastavnik].add(zahtev.smena)
        return {ime: frozenset(vrednosti) for ime, vrednosti in smene.items()}

    def _po_osobi(self, izvuci) -> dict[str, int]:
        ukupno: dict[str, int] = defaultdict(int)
        for zahtev in self.zahtevi:
            par = izvuci(zahtev)
            if par:
                ukupno[par[0]] += par[1]
        return dict(sorted(ukupno.items(), key=lambda stavka: -stavka[1]))

    def odeljenja_po_smeni(self, smena: Smena) -> tuple[str, ...]:
        """Group labels in a given shift, sorted."""
        return tuple(
            sorted(o.oznaka for o in self.odeljenja.values() if o.smena == smena)
        )


def kapacitet_smene(smena: Smena, broj_dana: int = len(DANI)) -> int | None:
    """Blocks available to a group in a week, or None when it cannot be derived.

    An alternating group sits in the four-block morning window every other week,
    and that narrower window is what binds; a stalno-popodne group always has the
    six-block afternoon window.
    """
    if smena.menja_se:
        return len(PRVA_SMENA) * broj_dana
    if smena is Smena.STALNO_POPODNE:
        return len(DRUGA_SMENA) * broj_dana
    if smena is Smena.CEO_DAN:
        return len(BLOKOVI) * broj_dana
    return None
