# Otvorena pitanja

Ovaj dokument je privremena lista pitanja na koja još nemamo potvrđen odgovor.
Ovde se zapisuju samo otvorena pitanja, a ne potvrđena pravila ili podaci.
Pitanja su poređana po tome koliko blokiraju izradu solvera.

Kada se dobije odgovor, u istom pull requestu treba:

- uneti potvrđeno pravilo u
  [pravila-rasporeda.md](pravila-rasporeda.md), odgovarajući podatak u CSV fajl
  u `ulazi/`, ili tehničku odluku u kod i testove;
- obrisati rešeno pitanje iz ovog dokumenta;
- dodati svako novo pitanje koje je nastalo kao posledica odgovora.

Git istorija i pull request čuvaju podatak o tome šta je odgovoreno i kada, pa
rešena pitanja ne treba zadržavati u ovom dokumentu.

## Blokira solver

- **Nedostupnost nastavnika.** `ulazi/nedostupnost.csv` je prazan, a zna se
  da neki nastavnici ne rade određenim danima i da nastavnici opštih predmeta
  rade i u drugim školama. Najvažniji podatak koji fali: šest nastavnika
  osnovne ima tačno 20 časova naspram 20 jutarnjih blokova (4 × 5), pa svaki
  nepoznati slobodan dan obara rešivost. Popunjava administrator, kako saznaje.

  Odgovor upisati u: `ulazi/nedostupnost.csv`.

- **Prioriteti sala.** Kolona `приоритет` u `ulazi/prostorije.csv` je
  prazna. Dovoljno je 1 (najbolja) do 3 po sali.

  Odgovor upisati u: `ulazi/prostorije.csv`.

- **„Dodatna sala koju ne treba koristiti“.** Koja je to sala u Knez
  Miletinoj? U prošlogodišnjem rasporedu ne postoji `KM-7`, a `KM-8` se
  koristila skoro samo za Primere i gimnastiku osnovne. Da li je `KM-7` ta
  zabranjena sala?

  Odgovor upisati u: `ulazi/prostorije.csv`.

- **Odeljenje П1.** Smena mu je slobodan tekst: „стално од 18,30 часова
  понедељком средом петком“. Da li to znači tačno blok 13 (18:30–19:15) i
  tačno ta tri dana?

  Odgovor upisati u: `ulazi/osnovna_baletska_skola.csv`.

## Pravila koja treba raščistiti

- **Mirror ne izlazi tačno.** Smenjujuća odeljenja osnovne se uparuju 6:7 —
  odeljenje 14 (plava) nema crvenog parnjaka. Kako se to rešava u praksi?

  Odgovor upisati u:
  [pravila-rasporeda.md](pravila-rasporeda.md).

- **Biblioteke.** Dve biblioteke u Knez Miletinoj — smeju li da se koriste kao
  obične učionice? Prošle godine se u njima držala samo verska nastava.

  Odgovor upisati u: `ulazi/prostorije.csv` i, ako predstavlja opšte pravilo,
  u [pravila-rasporeda.md](pravila-rasporeda.md).

- **Kadrovske rupe.** Korepetitor za 21 čas (osnovna
  `корепетитор br.1` 13 časova + srednja `?` 8 časova) još nije zaposlen;
  Dijani Jovanović (18 časova) sme da se doda. U referenci je nerazrešen par
  `Kristina / Ana` (2 časa petkom).

  Odgovor upisati u odgovarajuće CSV fajlove u `ulazi/`.
