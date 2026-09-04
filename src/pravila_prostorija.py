"""Zajednička semantika strukturisanih pravila prostorija."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

from .model import (
    DANI,
    DostupnostProstorije,
    NivoPravilaProstorije,
    PraviloProstorije,
    Zahtev,
)

NP_SALA = "NP-сала"
NP_ALIASI = frozenset({"NP-1", "NP-2", NP_SALA})

KAZNE_NIVOA = {
    NivoPravilaProstorije.PRVI: 0,
    NivoPravilaProstorije.DRUGI: 1_000,
    NivoPravilaProstorije.IZUZETNO: 100_000,
}
KAZNA_NEPOKRIVENO = 10_000


def kanonska_prostorija(oznaka: str) -> str:
    """NP-1/NP-2 privremeno predstavljaju postojeću zbirnu NP-salu."""

    return NP_SALA if oznaka in NP_ALIASI else oznaka


def _oblik_odgovara(pravilo: PraviloProstorije, trajanje: int) -> bool:
    return pravilo.oblik_casa is None or (
        pravilo.oblik_casa == "двочас" and trajanje == 2
    )


def _nivo_za_odeljenje(
    pravila: Sequence[PraviloProstorije],
    prostorija: str,
    predmet: str,
    odeljenje: str,
    trajanje: int,
) -> NivoPravilaProstorije | None:
    """Vrati specifično pravilo; predmet ima prednost nad wildcardom."""

    prostorija = kanonska_prostorija(prostorija)
    kandidati = [
        p for p in pravila
        if kanonska_prostorija(p.prostorija) == prostorija
        and _oblik_odgovara(p, trajanje)
        and (not p.odeljenja or odeljenje in p.odeljenja)
    ]
    konkretna = [p for p in kandidati if p.predmet == predmet]
    izabrana = konkretna or [p for p in kandidati if p.predmet == "*"]
    if not izabrana:
        return None
    # Posle kanonizacije NP-1 i NP-2 mogu dati isti nivo za zbirnu salu.
    nivoi = {p.nivo for p in izabrana}
    if len(nivoi) != 1:
        raise ValueError(
            f"Сукобљена правила за {prostorija}, {predmet}, {odeljenje}"
        )
    return next(iter(nivoi))


def _odeljenja(zahtev: Zahtev) -> tuple[str, ...]:
    return zahtev.odeljenja or ("",)


def nivo_prostorije(
    pravila: Sequence[PraviloProstorije],
    zahtev: Zahtev,
    prostorija: str,
    trajanje: int,
) -> NivoPravilaProstorije | None:
    """Vrati najlošiji nivo koji konkretna soba ima za grupisani čas."""

    nivoi = [
        _nivo_za_odeljenje(
            pravila, prostorija, zahtev.predmet, odeljenje, trajanje
        )
        for odeljenje in _odeljenja(zahtev)
    ]
    prisutni = [nivo for nivo in nivoi if nivo is not None]
    if not prisutni:
        return None
    redosled = {
        NivoPravilaProstorije.OBAVEZNO: 0,
        NivoPravilaProstorije.PRVI: 1,
        NivoPravilaProstorije.DRUGI: 2,
        NivoPravilaProstorije.IZUZETNO: 3,
        NivoPravilaProstorije.ZABRANJENO: 4,
    }
    najlosiji = max(prisutni, key=redosled.__getitem__)
    if None in nivoi and najlosiji not in (
        NivoPravilaProstorije.IZUZETNO,
        NivoPravilaProstorije.ZABRANJENO,
    ):
        return None
    return najlosiji


def dozvoljena_prostorija(
    pravila: Sequence[PraviloProstorije],
    zahtev: Zahtev,
    prostorija: str,
    trajanje: int,
) -> bool:
    """Primeni zabranu i presek obaveznih skupova svih odeljenja."""

    odeljenja = _odeljenja(zahtev)
    for odeljenje in odeljenja:
        nivo = _nivo_za_odeljenje(
            pravila, prostorija, zahtev.predmet, odeljenje, trajanje
        )
        if nivo is NivoPravilaProstorije.ZABRANJENO:
            return False
        sve_sobe = {kanonska_prostorija(p.prostorija) for p in pravila}
        obavezne = {
            soba for soba in sve_sobe
            if _nivo_za_odeljenje(
                pravila, soba, zahtev.predmet, odeljenje, trajanje
            ) is NivoPravilaProstorije.OBAVEZNO
        }
        if obavezne and kanonska_prostorija(prostorija) not in obavezne:
            return False
    return True


def kazna_prostorije(
    pravila: Sequence[PraviloProstorije],
    zahtev: Zahtev,
    prostorija: str,
    trajanje: int,
) -> int:
    """Prvi < drugi < nepokriveno < izuzetno; bez pravila nema kazne."""

    ukupno = 0
    for odeljenje in _odeljenja(zahtev):
        nivo = _nivo_za_odeljenje(
            pravila, prostorija, zahtev.predmet, odeljenje, trajanje
        )
        if nivo in KAZNE_NIVOA:
            ukupno += KAZNE_NIVOA[nivo]
            continue
        if nivo is not None:
            continue
        ima_meko_pravilo = any(
            _nivo_za_odeljenje(
                pravila, p.prostorija, zahtev.predmet, odeljenje, trajanje
            ) in KAZNE_NIVOA
            for p in pravila
        )
        if ima_meko_pravilo:
            ukupno += KAZNA_NEPOKRIVENO
    return ukupno


def bolji_eksplicitni_kandidati(
    pravila: Sequence[PraviloProstorije],
    zahtev: Zahtev,
    prostorija: str,
    trajanje: int,
) -> tuple[str, ...]:
    """Sobe sa strogo manjom kaznom, za poruku proveravača."""

    trenutna = kazna_prostorije(pravila, zahtev, prostorija, trajanje)
    kandidati = {
        kanonska_prostorija(p.prostorija)
        for p in pravila
        if p.predmet == zahtev.predmet
        and _oblik_odgovara(p, trajanje)
        and any(not p.odeljenja or o in p.odeljenja for o in _odeljenja(zahtev))
        and p.nivo in (
            NivoPravilaProstorije.OBAVEZNO,
            NivoPravilaProstorije.PRVI,
            NivoPravilaProstorije.DRUGI,
        )
        and kazna_prostorije(pravila, zahtev, p.prostorija, trajanje) < trenutna
    }
    return tuple(sorted(kandidati))


def prostorija_dostupna(
    dostupnosti: Sequence[DostupnostProstorije],
    prostorija: str,
    dan: str,
    blokovi: Iterable[int],
) -> bool:
    """Whitelist važi samo za sobe koje imaju redove; NP aliasi čine uniju."""

    oznaka = kanonska_prostorija(prostorija)
    po_sobi: dict[str, list[DostupnostProstorije]] = defaultdict(list)
    for stavka in dostupnosti:
        po_sobi[kanonska_prostorija(stavka.prostorija)].append(stavka)
    if oznaka not in po_sobi:
        return True
    return all(
        any(
            stavka.dan == dan
            and stavka.od_bloka <= blok <= stavka.do_bloka
            for stavka in po_sobi[oznaka]
        )
        for blok in blokovi
    )
