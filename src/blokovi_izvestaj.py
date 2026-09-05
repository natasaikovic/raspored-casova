"""Nezavisna provera CSV para i pregled stvarnih obaveznih dvočasa.

Izlaz je dijagnostika kandidata; neuspešna provera nikad ne objavljuje raspored.
"""
import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path

from .blokovi import INFORMATIKA, OBAVEZNI_DVOCASI, SRPSKI
from .km8 import proveri_km8
from .model import BLOKOVI, DANI, Smena
from .proveravac import _kanonizuj_casove, proveri, ucitaj_resenje
from .resavac import ucitaj_standardne_ulaze, _hint_postuje_medjunedeljne_invarijante


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raspored', type=Path, required=True)
    parser.add_argument('--izlaz', type=Path, required=True)
    parser.add_argument('--ulazi', type=Path, default=Path('ulazi'))
    args = parser.parse_args(argv)
    u, sobe, n = ucitaj_standardne_ulaze(args.ulazi)
    args.izlaz.mkdir(parents=True, exist_ok=True)
    tekst = ['ПРОВЕРА КАНДИДАТА — ово није нови распоред.']
    redovi, nedelje = [], []
    ispravno = True
    obavezni = {(z.predmet, o) for z in u.zahtevi for o in z.odeljenja
                if z.predmet in OBAVEZNI_DVOCASI
                or (z.predmet == INFORMATIKA and z.fond == 2)
                or (z.predmet == SRPSKI and z.fond == 3)
                or (u.predmeti[z.predmet].trazi_salu and z.fond % 2 == 0)}
    for nedelja, ime, smena in [('А', 'a', Smena.CRVENA), ('Б', 'b', Smena.PLAVA)]:
        p = args.raspored / f'nedelja_{ime}.csv'
        c = _kanonizuj_casove(u, sobe, ucitaj_resenje(p))
        nedelje.append(c)
        r = proveri(u, sobe, n, c, smena)
        ispravno &= r.ispravan
        tekst.append(f'Недеља {nedelja}: грешке {len(r.greske)}, упозорења {len(r.upozorenja)}, '
                     f'недозвољене доделе КМ-8 {len(proveri_km8(u, c, smena))}.')
        tekst.append(f'Извор: {p}; SHA256 {hashlib.sha256(p.read_bytes()).hexdigest()}')
        tekst.extend(r.greske)
        grupe = defaultdict(list)
        for cas in c:
            if any((cas.predmet, o) in obavezni for o in cas.odeljenja):
                grupe[(cas.dan, cas.predmet, cas.odeljenja)].append(cas)
        for (dan, predmet, odeljenja), casovi in sorted(grupe.items(), key=lambda x: (DANI.index(x[0][0]), x[0][1:])):
            casovi.sort(key=lambda x: x.blok)
            for a, b in zip(casovi[::2], casovi[1::2]):
                if b.blok != a.blok + 1 or (a.nastavnik, a.korepetitor, a.prostorija) != (b.nastavnik, b.korepetitor, b.prostorija):
                    continue
                redovi.append((nedelja, ';'.join(odeljenja), predmet, dan,
                               str(BLOKOVI[a.blok-1]), str(BLOKOVI[b.blok-1]), a.prostorija,
                               a.nastavnik, a.korepetitor or '', 'ИСПРАВНА' if r.ispravan else 'НЕИСПРАВНА'))
    iste = _hint_postuje_medjunedeljne_invarijante(u, *nedelje)
    tekst.append(f'Једнак распоред СБШ и осталих сталних смена А/Б: {"ДА" if iste else "НЕ"}.')
    tekst.append('Преглед двочаса садржи само стварне исправне парове; не доказује испуњен недељни фонд.')
    with (args.izlaz / 'pregled_dvocasa_kandidata.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(('недеља', 'одељење/група', 'предмет', 'дан', 'први термин', 'други термин',
                    'просторија', 'наставник', 'корепетитор', 'провера целе недеље'))
        w.writerows(redovi)
    (args.izlaz / 'provera_prethodnog_rasporeda.txt').write_text('\n'.join(tekst)+'\n', encoding='utf-8')
    print('\n'.join(t for t in tekst if t.startswith(('Недеља', 'Једнак'))))
    return 0 if ispravno and iste else 1


if __name__ == '__main__':
    raise SystemExit(main())
