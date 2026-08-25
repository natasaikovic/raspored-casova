# Rešavač rasporeda

Prva verzija rešavača koristi OR-Tools CP-SAT. Osnovna i srednja škola učitavaju
se zajedno, jer dele nastavnike, korepetitore i prostorije. Jedno pokretanje
pravi obe nedelje:

```bash
python -m src.resavac --izlaz resenja/2026-27
```

Nastaju `nedelja_a.csv` (crvena smena ujutru) i `nedelja_b.csv` (plava smena
ujutru). Oba fajla su na latinici i imaju format opisan u
[`format-resenja.md`](format-resenja.md).

## Čvrsta ograničenja

Rešavač ne sme da prekrši:

- fondove i grupisanje iz ulaznih CSV fajlova;
- smene osnovne škole i posebne termine P1;
- zauzetost odeljenja i polugrupa, nastavnika, korepetitora i prostorija;
- tip prostorije i posebnu učionicu za informatiku;
- dvočase igračkih predmeta i jedan glavni dvočas srednje škole dnevno;
- najviše četiri igračka i četiri opšta časa srednjeg odeljenja dnevno;
- istovremenost Verske nastave i Građanskog vaspitanja;
- nedostupnost nastavnika iz `ulazi/nedostupnost.csv`.

Oznake `?` i `korepetitor br.1` tretiraju se kao ista buduća osoba, iako su u
ulazima privremeno zapisane različito.

## Optimizacija i provera

Prazni časovi učenika i korišćenje više lokacija u istom danu za sada su deo
funkcije kvaliteta. Model pokušava da ih ukloni, ali ih ne postavlja kao čvrsto
ograničenje, jer bi nalaženje prve radne verzije bilo znatno sporije.

Svaki rezultat se zato odmah prosleđuje nezavisnom proveravaču. Komanda završava
statusom 1 ako raspored nije pronađen ili ako proveravač pronađe makar jednu
grešku. CSV ostaje sačuvan kao kandidat za sledeću iteraciju, ali se ne smatra
konačnim rasporedom.

Postojeći fajlovi u `radne_verzije/2026-27/` koriste se samo kao početni CP-SAT
hintovi. Oni ne postaju ograničenja i solver sme potpuno da promeni svaki termin
i prostoriju. Za pokretanje bez njih koristi se `--bez-hintova`.

Podrazumevano vremensko ograničenje je pet minuta po nedelji. Može se promeniti:

```bash
python -m src.resavac \
  --izlaz resenja/2026-27 \
  --vremensko-ogranicenje 900 \
  --broj-radnika 8 \
  --seme 1
```

Isto seme, isti ulazi i isti broj radnika daju ponovljiv polazni model, ali
paralelna CP-SAT pretraga ne garantuje identičan rezultat na svakoj platformi.
