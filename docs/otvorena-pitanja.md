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

- **Naziv repertoara za SG-1.** Excel navodi `Repertoar savremene igre` za
  odeljenja narodnog odseka (`I5`–`IV5`). Da li je to tačno ili treba da piše
  `Repertoar narodne igre`?
- **Dve sale Narodnog pozorišta.** Da li su `NP-1` i `NP-2` dve zasebne sale
  koje mogu istovremeno da rade sredom? Kako se one odnose prema staroj zbirnoj
  oznaci `NP-sala` i pet postojećih nedeljnih termina?
- **Kraj termina u Narodnom pozorištu.** Excel navodi 17:30, a blok 11 traje
  do 17:40. Da li dostupnost važi do 17:40 ili treba drugačije definisati blok?
- **Sale SG-2 i SG-3.** Da li su ravnopravne alternative za predmete navedene
  uz `SG-1` i da li je `SG-1` čvrsta obaveza ili samo najviši prioritet?
- **Izuzetna upotreba KM-8.** Da li `KM-8`, pored obavezne Primenjene
  gimnastike, sme izuzetno da se koristi i za druge predmete?
- **Pretežno OBŠ u KM-3 i KM-6.** Da li je to samo meki prioritet i koji
  predmeti ili odeljenja imaju prednost u tim salama?
- **Najbrojnije grupe u KM-uč7.** Da li Excel napomena `I-1,2,3 i I-4,5`
  označava dve spojene grupe `I1,I2,I3` i `I4,I5`, i da li je KM-uč7 za njih
  obavezna ili samo prioritetna?
- **Biblioteka.** Da li se četiri navedena predmeta u `IV5` održavaju kao
  jedna spojena grupa ili odvojeno, i da li su svi ostali predmeti zaista
  strogo zabranjeni?
- **Naziv informatike.** Da li u Excelu navedeno `Informatika i računarstvo`
  znači postojeći predmet `Računarstvo i informatika`?
- **Dve muzičke učionice.** Da li su `KM-uč2` i `SG-muzuč` ravnopravne
  alternative za Solfeđo i Tradicionalno pevanje ili lokacija zavisi od
  odeljenja?

## Pravila koja treba raščistiti

- **Solfedjo 43.** Excel navodi III razred, a CSV IV razred. Koji razred je tačan?

- **Kadrovske rupe.** Dijani Jovanović (18 časova) sme da se doda. U
  referenci je nerazrešen par `Kristina / Ana` (2 časa petkom).

  Odgovor upisati u odgovarajuće CSV fajlove u `ulazi/`.
