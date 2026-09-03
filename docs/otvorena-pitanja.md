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

- **Teodora Martinovski — nerešiv konflikt fonda i dostupnosti.** Posle
  preuzimanja Klasičnog baleta u odeljenjima `21` i `41`, Teodora ima ukupno
  23 časa. Od toga je 21 čas u crvenoj smeni: `KB 21` (10), `KB 41` (10) i
  `Istorijsko balske igre 41` (1). Crvena jutarnja smena od ponedeljka do petka
  ima samo 20 blokova, a dva svakodnevna dvočasa `KB 21` i `KB 41` popunjavaju
  svih 20. Zato za `Istorijsko balske igre 41` ne ostaje nijedan termin, dok je
  Teodora subotom nedostupna u blokovima 1–14.

  Potrebno je potvrditi jednu od mogućnosti, bez unapred izabranog rešenja:

  - da Teodora bude dostupna subotom za najmanje jedan čas;
  - da `Istorijsko balske igre 41` preuzme drugi nastavnik;
  - da se deo fonda `KB 21` ili `KB 41` poveri drugom nastavniku;
  - da se za Teodoru i odeljenje `41` odobri tačno definisan izuzetak od
    jutarnje smene.

- **Prioriteti sala.** Kolona `приоритет` u `ulazi/prostorije.csv` je
  delimično popunjena. Potvrđene su posebne namene sala 2, 4, 5 i 8, ali
  još nedostaju namena sala 3 i 6, kao i prioriteti sala u Sportskoj
  gimnaziji. Treba proveriti i da li je jedan broj 1–3 dovoljan pored
  prioriteta koji zavisi od predmeta.

  Odgovor upisati u: `ulazi/prostorije.csv`.

## Pravila koja treba raščistiti

- **Solfedjo 43.** Excel navodi III razred, a CSV IV razred. Koji razred je tačan?

- **Kadrovske rupe.** Dijani Jovanović (18 časova) sme da se doda. U
  referenci je nerazrešen par `Kristina / Ana` (2 časa petkom).

  Odgovor upisati u odgovarajuće CSV fajlove u `ulazi/`.
