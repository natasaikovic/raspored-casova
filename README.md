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

## Provera rešenja

Predloženi raspored može da napravi budući rešavač, AI agent ili čovek. Bez
obzira na način nastanka, proverava se istom komandom:

```bash
python -m src.proveravac putanja/do/resenja.csv
```

Format rešenja i spisak provera opisani su u dokumentu
[docs/format-resenja.md](docs/format-resenja.md). Kratak, nepotpun primer nalazi
se u `primeri/format-resenja.csv`.

## Automatsko rešavanje

Prva CP-SAT verzija rešavača pravi obe nedelje i svaki rezultat odmah šalje
nezavisnom proveravaču:

```bash
python -m src.resavac --izlaz resenja/2026-27
```

Čvrsta ograničenja, optimizacija, hintovi i opcije komandne linije opisani su u
[docs/resavac.md](docs/resavac.md).

## Trenutno stanje

Učitavanje, validacija ulaza, domenski model, nezavisna provera i prva CP-SAT
verzija automatskog rešavača postoje.

## Testovi

Instalirajte zavisnosti:

```bash
python -m pip install -r requirements.txt
```

Pokrenite testove:

```bash
python -m pytest
```
