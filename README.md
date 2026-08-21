# Raspored časova za baletsku školu

Projekat služi za izradu rasporeda časova za osnovnu i srednju baletsku školu.

## Ulazni podaci

Ulaz su CSV fajlovi u direktorijumu `ulazi/`, sa ćiriličnim zaglavljima. Za sada je dostupan:

- `ulazi/osnovna_baletska_skola.csv` — podaci za osnovnu baletsku školu.

Modul `src/loader.py` učitava CSV ulaz i proverava njegovu ispravnost, dok `src/model.py` sadrži domenski model rasporeda.

## Referentni raspored

Direktorijum `referenca/` sadrži prošlogodišnji raspored (2025/26), izvučen iz ručno vođene Excel tabele koja se ne nalazi u repozitorijumu. To **nije ulaz** — ulazni podaci nalaze se isključivo u direktorijumu `ulazi/`.

Referentni raspored služi za proveru modela ograničenja, topli start solvera (`AddHint()`) i kao predlog oblika izlaza. Detalji su u dokumentu [referenca/README.md](referenca/README.md).

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
