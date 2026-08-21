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
    ``POSEBNA`` marks a group whose availability is written as free text in the
    input and needs a hand-written rule (currently only П1).
    """

    CRVENA = "црвена смена"
    PLAVA = "плава смена"
    STALNO_POPODNE = "стално послеподне"
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
    """A class group; the unit that attends lessons together."""

    oznaka: str
    razred: str
    smena: Smena
    skola: Skola


@dataclass(frozen=True)
class Predmet:
    """A subject, classified by whether it needs an accompanist.

    ``docs/pravila-rasporeda.md`` splits subjects into igrački (one group, one
    teacher, one korepetitor, one sala) and opšti (one or more groups, one
    teacher, no korepetitor, one učionica). Needing a korepetitor is what
    separates them, so it is derived rather than configured.
    """

    naziv: str
    igracki: bool

    @property
    def trazi_salu(self) -> bool:
        """Dance subjects need a sala; everything else takes a učionica."""
        return self.igracki


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
    skola: Skola

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
    return None
