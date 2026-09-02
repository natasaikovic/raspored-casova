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

Sekvencijalno rešavanje A → B bez hinta nije našlo nedelju A za 1801.596 s, pa nije spojeno.

- **Nedostupnost nastavnika.** `ulazi/nedostupnost.csv` je prazan, a zna se
  da neki nastavnici ne rade određenim danima i da nastavnici opštih predmeta
  rade i u drugim školama. Najvažniji podatak koji fali: šest nastavnika
  osnovne ima tačno 20 časova naspram 20 jutarnjih blokova (4 × 5), pa svaki
  nepoznati slobodan dan obara rešivost. Popunjava administrator, kako saznaje.

  Odgovor upisati u: `ulazi/nedostupnost.csv`.

- **Prioriteti sala.** Kolona `приоритет` u `ulazi/prostorije.csv` je
  delimično popunjena. Potvrđene su posebne namene sala 2, 4, 5 i 8, ali
  još nedostaju namena sala 3 i 6, kao i prioriteti sala u Sportskoj
  gimnaziji. Treba proveriti i da li je jedan broj 1–3 dovoljan pored
  prioriteta koji zavisi od predmeta.

  Odgovor upisati u: `ulazi/prostorije.csv`.

## Pravila koja treba raščistiti

- **Kadrovske rupe.** Dijani Jovanović (18 časova) sme da se doda. U
  referenci je nerazrešen par `Kristina / Ana` (2 časa petkom).

  Odgovor upisati u odgovarajuće CSV fajlove u `ulazi/`.
