"""Zatvorena lista dozvola za KM-8. Fondovi i zaposleni su izvorni podaci,
ne nova zaduženja. Prazna lista ne dozvoljava nijednu namenu.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

from .model import DozvolaKM8, Skola, Smena, Ulaz, Zahtev, PRVA_SMENA
from .pismo import kljuc_pisma


def predmet_kljuc(value: str) -> str:
    return " ".join(kljuc_pisma(value).casefold().replace("—", "-").replace("–", "-").split())


def grupa_kljuc(value: str) -> str:
    # Rimski brojevi ostaju rimski; polugrupa ostaje deo identiteta.
    return re.sub(r"[\s–—-]", "", kljuc_pisma(value)).upper()


def dozvola_za(ulaz: Ulaz, predmet: str, oznaka: str) -> DozvolaKM8 | None:
    odeljenje = ulaz.odeljenja.get(oznaka)
    if odeljenje is None:
        return None
    return next((d for d in ulaz.dozvole_km8
                 if d.skola is odeljenje.skola
                 and predmet_kljuc(d.predmet) == predmet_kljuc(predmet)
                 and grupa_kljuc(d.odeljenje) == grupa_kljuc(oznaka)), None)


def dozvoljen_km8(ulaz: Ulaz, zahtev: Zahtev, trajanje: int,
                  jutarnja: Smena | None = None, blok: int | None = None) -> bool:
    if not zahtev.odeljenja:
        return False
    for oznaka in zahtev.odeljenja:
        d = dozvola_za(ulaz, zahtev.predmet, oznaka)
        if d is None or (d.najvece_trajanje is not None and trajanje > d.najvece_trajanje):
            return False
        if d.samo_pre_podne:
            if jutarnja is not None and (
                zahtev.smena is not jutarnja or ulaz.odeljenja[oznaka].smena is not jutarnja
            ):
                return False
            if blok is not None and any(b not in PRVA_SMENA for b in range(blok, blok + trajanje)):
                return False
    return True


def ucitaj_dozvole_km8(putanja: str | Path) -> tuple[DozvolaKM8, ...]:
    from .loader import UlazGreska

    kolone = ('ред Excel', 'ниво школе', 'предмет', 'разред', 'одељење',
              'недељни фонд часова', 'часови корепетиције', 'наставник',
              'корепетитор', 'напомена', 'само преподне',
              'највише часова у КМ-8', 'највеће трајање')
    rezultat, greske, vidjeno, redovi = [], [], set(), set()
    with Path(putanja).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != kolone:
            raise UlazGreska([f'{putanja}: погрешне колоне дозвола КМ-8'])
        for red, raw in enumerate(reader, 2):
            try:
                if None in raw or None in raw.values():
                    raise ValueError('погрешан број колона')
                r = {k: v.strip() for k, v in raw.items()}
                note = r['напомена']
                notes = {'': (False, None, None),
                         'Само у преподневној смени': (True, None, None),
                         'Само један час. Двочас мора ићи у другу салу.': (False, 1, 1)}
                if note not in notes or r['само преподне'] not in ('0', '1'):
                    raise ValueError('непозната напомена или услов смене')
                uslovi = (r['само преподне'] == '1',
                          int(r['највише часова у КМ-8']) if r['највише часова у КМ-8'] else None,
                          int(r['највеће трајање']) if r['највеће трајање'] else None)
                if uslovi != notes[note]:
                    raise ValueError('напомена и структурирани услови се не слажу')
                d = DozvolaKM8(int(r['ред Excel']), Skola(r['ниво школе']),
                              r['предмет'], r['одељење'], r['разред'],
                              int(r['недељни фонд часова']), int(r['часови корепетиције'] or 0),
                              r['наставник'], r['корепетитор'] or None, note, *uslovi)
                pattern = r'[1-4][1-9]' if d.skola is Skola.OSNOVNA else r'(?:I|II|III|IV)[1-5][AB]?'
                if not re.fullmatch(pattern, grupa_kljuc(d.odeljenje)):
                    raise ValueError('ниво школе и ознака групе се не слажу')
                if d.red_excel < 2 or d.fond <= 0 or not d.predmet or not d.nastavnik:
                    raise ValueError('недостају обавезне вредности')
                key = (d.skola, predmet_kljuc(d.predmet), grupa_kljuc(d.odeljenje))
                if key in vidjeno or d.red_excel in redovi:
                    raise ValueError('поновљена дозвола или ред Excel')
                vidjeno.add(key); redovi.add(d.red_excel); rezultat.append(d)
            except (ValueError, KeyError) as e:
                greske.append(f'{putanja}, ред {red}: {e}')
    if greske:
        raise UlazGreska(greske)
    return tuple(rezultat)


def proveri_km8(ulaz, casovi, jutarnja):
    """Nezavisni pregled svakog časa, limita i dvočasa preko različitih sala."""
    from .pravila_prostorija import kanonska_prostorija

    greske, brojac = [], Counter()
    for c in casovi:
        if kanonska_prostorija(c.prostorija) != 'KM-8':
            continue
        razlozi = []
        if not c.odeljenja:
            razlozi.append('нема групе')
        for o in c.odeljenja:
            d = dozvola_za(ulaz, c.predmet, o)
            if d is None:
                razlozi.append(f'{o}: нема изричите дозволе')
                continue
            if d.samo_pre_podne and (
                ulaz.odeljenja[o].smena is not jutarnja or c.blok not in PRVA_SMENA
            ):
                razlozi.append(f'{o}: само преподневна смена (Excel ред {d.red_excel})')
            if d.najvece_trajanje == 1 and any(
                other.dan == c.dan and other.predmet == c.predmet and o in other.odeljenja
                and abs(other.blok - c.blok) == 1 for other in casovi
            ):
                razlozi.append(f'{o}: двочас мора цео у другу салу (Excel ред {d.red_excel})')
            brojac[(d.red_excel, o)] += 1
            if d.najvise_casova is not None and brojac[(d.red_excel, o)] > d.najvise_casova:
                razlozi.append(f'{o}: више од {d.najvise_casova} часа недељно (Excel ред {d.red_excel})')
        if razlozi:
            greske.append(f'{c.gde}: КМ-8, {c.dan}, блок {c.blok}, „{c.predmet}“: ' + '; '.join(razlozi))
    return greske
