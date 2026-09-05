"""Provera A/B para i sledljiv pregled svakog časa u KM-8.

python -m src.km8_izvestaj --raspored izlaz --ulazi ulazi
"""

import argparse
import csv
from pathlib import Path

from .km8 import dozvola_za, proveri_km8
from .model import BLOKOVI, Smena
from .proveravac import _kanonizuj_casove, proveri, ucitaj_resenje
from .resavac import ucitaj_standardne_ulaze, _hint_postuje_medjunedeljne_invarijante


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raspored', type=Path, required=True)
    parser.add_argument('--ulazi', type=Path, default=Path('ulazi'))
    args = parser.parse_args(argv)
    u, sobe, nedostupnosti = ucitaj_standardne_ulaze(args.ulazi)
    redovi, tekst, nedelje = [], [], []
    ispravno = True
    for nedelja, ime, jutarnja in [('А', 'a', Smena.CRVENA), ('Б', 'b', Smena.PLAVA)]:
        casovi = _kanonizuj_casove(u, sobe, ucitaj_resenje(args.raspored / f'nedelja_{ime}.csv'))
        nedelje.append(casovi)
        r = proveri(u, sobe, nedostupnosti, casovi, jutarnja)
        km8_greske = proveri_km8(u, casovi, jutarnja)
        ispravno = ispravno and r.ispravan and not km8_greske
        km8 = [c for c in casovi if c.prostorija == 'KM-8']
        tekst.append(f'Недеља {nedelja}: {len(casovi)} часова; грешке {len(r.greske)}; '
                     f'упозорења {len(r.upozorenja)}; часови у КМ-8 {len(km8)}; '
                     f'недозвољене доделе у КМ-8 {len(km8_greske)}.')
        tekst.extend(r.greske)
        for c in km8:
            dozvole = [dozvola_za(u, c.predmet, o) for o in c.odeljenja]
            redovi.append((nedelja, c.dan, BLOKOVI[c.blok-1].pocetak,
                           BLOKOVI[c.blok-1].kraj, c.predmet,
                           ';'.join(c.odeljenja),
                           ';'.join(u.odeljenja[o].skola.value for o in c.odeljenja),
                           ';'.join(str(d.red_excel) if d else 'НЕМА ДОЗВОЛЕ' for d in dozvole),
                           ';'.join(d.napomena for d in dozvole if d and d.napomena)))
    iste = _hint_postuje_medjunedeljne_invarijante(u, *nedelje)
    tekst.append(f'Једнак распоред СБШ и осталих сталних смена А/Б: {"ДА" if iste else "НЕ"}.')
    ispravno = ispravno and iste
    with (args.raspored / 'km8_pregled.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(('недеља','дан','почетак','крај','предмет','одељење/група',
                    'ниво школе','ред Excel листа КМ-8','напомена'))
        w.writerows(redovi)
    (args.raspored / 'provera.txt').write_text('\n'.join(tekst) + '\n', encoding='utf-8')
    print('\n'.join(tekst))
    return 0 if ispravno else 1


if __name__ == '__main__':
    raise SystemExit(main())
