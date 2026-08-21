# Uputstvo za AI agente

## O projektu

Raspored časova za baletsku školu — osnovnu i srednju. Krajnji korisnik je
školski administrator koji nije programer.

## Ulazni podaci

- Ulaz su CSV fajlovi u `ulazi/`, sa ćiriličnim zaglavljima.
- Jedan red = jedan predmet za jedno ili više odeljenja, sa nedeljnim fondom.
- NE uvoditi YAML, JSON ni Excel kao ulazni format. CSV je izabran namerno:
  administrator ga menja preko AI asistenta, a git prikazuje čitljiv diff.
- Fajlove menja asistent, pa validacija mora ostati stroga.
- Čitati sa `utf-8-sig` — BOM se često pojavi.

## Konvencije u kodu

- Struktura koda je engleska, domenske imenice ostaju srpske: `Smena`,
  `Odeljenje`, `Zahtev`, `Predmet`, `fond`, `korepetitor`. Ne prevoditi ih —
  tako se tipovi poklapaju sa kolonama u CSV-u i sa pravilima.
- Poruke o greškama pišu se ćirilicom, jer ih čita administrator.
- Validacija skuplja SVE greške u jednom prolazu i tek onda podiže izuzetak.
  Nikada ne prekidati na prvoj grešci — korisnik ispravlja fajl iz jednog pokušaja.

## Domenske odluke (ne menjati bez dogovora)

- Jedinica rasporeda je ODELJENJE, ne pojedinačni učenik.
- `Predmet.igracki` se IZVODI iz toga da li predmet ima korepetitora; ne
  konfiguriše se ručno. Igrački predmeti traže salu, opšti učionicu.
- Smena je ULAZNI PODATAK, ne odluka solvera.
- Subota je nastavni dan. Nedeljni raspored ima 6 dana. Bez subote instanca
  nije rešiva: šest nastavnika ima tačno 20 časova, a jutarnja smena ima 4
  bloka × 5 dana = 20, dakle nula rezerve.
- Crvena i plava smena se smenjuju nedeljno i raspoređuju se simetrično
  (mirror), pa se rešava jedna nedelja.
- Odeljenja 13, 23 i 33 su uvek popodne.
- Pre menjanja logike rasporeda pročitati `docs/pravila-rasporeda.md`.

## Testovi

- `python -m pytest`
- Testovi za loader koriste samo standardnu biblioteku i moraju tako i ostati.
- `ortools` je potreban samo za solver, kada bude napisan.
