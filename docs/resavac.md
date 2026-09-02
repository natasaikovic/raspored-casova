# Rešavač rasporeda

Rešavač koristi OR-Tools CP-SAT. Osnovna i srednja škola učitavaju
se zajedno, jer dele nastavnike, korepetitore i prostorije. Jedno pokretanje
pravi obe nedelje:

```bash
python -m src.resavac --izlaz resenja/2026-27
```

Nastaju `nedelja_a.csv` (crvena smena ujutru) i `nedelja_b.csv` (plava smena
ujutru). Oba fajla su na latinici i imaju format opisan u
[`format-resenja.md`](format-resenja.md).

## Odnos nedelja A i B

Nedelje se rešavaju sekvencijalno: prvo nedelja A, pa nedelja B. Kada je A
pronađena, časovi srednje škole, stalnih smena i P1 fiksiraju se u B na isti
dan, blok i prostoriju. Naizmenične smene nisu strogo ogledalo:

- smena iz ulaznog CSV-a određuje dozvoljene blokove odeljenja u nedelji A;
- njena inverzna smena određuje dozvoljene blokove u nedelji B;
- naizmenična odeljenja osnovne škole dobijaju zasebne odluke za dan, blok i
  prostoriju u svakoj nedelji;
- srednja škola, odeljenja `13`, `23` i `33`, kao i P1, ostaju identični u obe
  nedelje jer su pri rešavanju B fiksirani na rezultat A.

Svaka nedelja dobija celo zadato vremensko ograničenje. Resursi i učenička
preklapanja proveravaju se zasebno za A i B, a oba dobijena CSV fajla zatim
prolaze kroz nezavisni proveravač. Prošlogodišnja referenca ne sadrži dve verzije
rasporeda istog odeljenja, pa ne daje osnov da se nametne jača simetrija.

## Čvrsta ograničenja

Rešavač ne sme da prekrši:

- fondove i grupisanje iz ulaznih CSV fajlova;
- smene osnovne škole i posebne termine P1;
- zauzetost odeljenja i polugrupa, nastavnika, korepetitora i prostorija;
- subotom završetak najkasnije do 15:05, uz snažnu prednost završetka do 13:15
  i korišćenja sala Sportske gimnazije;
- tip prostorije i posebnu učionicu za informatiku;
- dvočase igračkih predmeta i jedan glavni dvočas srednje škole dnevno;
- najviše četiri časa dnevno za odeljenja osnovne škole;
- najviše četiri igračka i četiri opšta časa srednjeg odeljenja dnevno;
- bez praznih časova učenika, osim tačno jednog putnog bloka pri promeni
  lokacije;
- najviše jednu promenu lokacije po odeljenju u toku dana;
- istovremenost Verske nastave i Građanskog vaspitanja;
- nedostupnost nastavnika iz `ulazi/nedostupnost.csv`.

Oznake `?` i `korepetitor br.1` tretiraju se kao ista buduća osoba, iako su u
ulazima privremeno zapisane različito.

Rešavanje svake nedelje ima dve faze. Glavni model bira termine i lokacije i
kontroliše zbirni kapacitet sala i učionica na svakoj lokaciji. Kada su termini
poznati, manji pomoćni model dodeljuje konkretne prostorije bez preklapanja.
Time se uklanjaju hiljade simetričnih izbora konkretnih sala iz glavne
pretrage, a CSV i dalje sadrži proverenu konkretnu prostoriju za svaki čas.
Posebna pravila, uključujući obaveznu `KM-uč1` za informatiku i termine
`NP-sala`, važe i u drugoj fazi.

## Optimizacija i provera

Prazni časovi učenika i promena lokacije modelirani su kao čvrsta pravila.
Za svako odeljenje i dan model bira kompaktan dnevni obrazac: prvi i poslednji
blok, ukupan broj časova, postojanje i položaj putnog bloka, kao i lokaciju pre
i posle njega. Ako odeljenje ostaje na jednoj lokaciji, svi dnevni časovi su
povezani. Ako jednom promeni lokaciju između Knez Miletine i Sportske
gimnazije, dve celine moraju biti neposredno jedna uz drugu. Za druge promene
lokacije između njih postoji tačno jedan slobodan blok za put. Druga promena
lokacije, povratak na prvu lokaciju i svaka druga praznina nisu dozvoljeni.

Samo Ivana Ljujić i Jelena Prvulović imaju čvrsto ograničenje od najviše jedne
pauze nedeljno, duge najviše dva bloka. Za sve ostale nastavnike i
korepetitore broj i trajanje pauza nisu čvrsti, ali svaka pauza i dalje
pogoršava cilj solvera. Isto pravilo primenjuje nezavisni proveravač.
Svaka osoba ima čvrsti dnevni maksimum od šest časova, dok cilj dodatno
kažnjava peti i šesti čas kako bi optimalno dnevno angažovanje bilo do četiri.

Svaki rezultat se zato odmah prosleđuje nezavisnom proveravaču. Komanda završava
statusom 1 ako raspored nije pronađen ili ako proveravač pronađe makar jednu
grešku. CSV ostaje sačuvan kao kandidat za sledeću iteraciju, ali se ne smatra
konačnim rasporedom.

Postojeći fajlovi u `radne_verzije/2026-27/` ne učitavaju se kao hintovi.
Podrazumevano vremensko ograničenje je pet minuta za svaku nedelju. Može se
promeniti:

```bash
python -m src.resavac \
  --izlaz resenja/2026-27 \
  --vremensko-ogranicenje 900 \
  --broj-radnika 8 \
  --seme 1
```

Isto seme, isti ulazi i isti broj radnika daju ponovljiv polazni model, ali
paralelna CP-SAT pretraga ne garantuje identičan rezultat na svakoj platformi.
