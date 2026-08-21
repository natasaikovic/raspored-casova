# Raspored časova za baletsku školu

Projekat služi za izradu rasporeda časova za osnovnu i srednju baletsku školu.

## Ulazni podaci

Ulaz su CSV fajlovi u direktorijumu `ulazi/`, sa ćiriličnim zaglavljima. Za sada je dostupan:

- `ulazi/osnovna_baletska_skola.csv` — podaci za osnovnu baletsku školu.

Modul `src/loader.py` učitava CSV ulaz i proverava njegovu ispravnost, dok `src/model.py` sadrži domenski model rasporeda.

## Pravila rasporeda

Pravila i domenske odluke opisani su u dokumentu [docs/pravila-rasporeda.md](docs/pravila-rasporeda.md).

## Trenutno stanje

Učitavanje, validacija i domenski model postoje. Solver za pravljenje rasporeda još ne postoji — njegova izrada je sledeći korak.

## Testovi

Instalirajte zavisnosti:

```bash
python -m pip install -r requirements.txt
```

Pokrenite testove:

```bash
python -m pytest
```
