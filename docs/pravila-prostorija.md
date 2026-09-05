# Strukturisana pravila prostorija

Izvor pravila je `ulazi/pravila_prostorija.csv`. Jedan red je jedno atomsko
pravilo: jedna prostorija, jedan predmet i najviše jedno odeljenje. Prazno
odeljenje znači sva odeljenja, prazan oblik časa znači svaki oblik, a
`двочас` važi samo za sesiju od dva uzastopna bloka.

## Semantika nivoa

- `обавезно` je čvrsto pravilo. Ako za čas postoji više obaveznih prostorija,
  one su ravnopravne alternative. Kod grupisanog časa izabrana prostorija mora
  zadovoljiti obavezni skup svakog odeljenja.
- `први` nosi kaznu 0, a `други` kaznu 1.000.
- prostorija koju nijedan red ne pokriva ostaje dozvoljena i, kada za taj čas
  postoji meko pravilo, nosi kaznu 10.000;
- `изузетно` je dozvoljeno uz kaznu 100.000;
- `забрањено` je čvrsta zabrana.

Pravilo za konkretan predmet ima prednost nad wildcard pravilom `*` iste
prostorije. Zato četiri izričita izuzetka za `KM-библиотека` i `Глума и вокал`
u `KM-видеотека` nisu blokirani podrazumevanom zabranom tih prostorija.

Ista semantika se koristi u modelu termina, završnoj dodeli prostorija i
nezavisnom proveravaču. Model termina ima skrivenu konkretnu sobu, pa ne može
izabrati termin koji tek naknadna dodela soba ne može da realizuje.

## Dostupnost sala

`ulazi/dostupnost_prostorija.csv` je whitelist: prostorija koja ima makar jedan
red sme se koristiti samo u navedenim danima i blokovima. Za prostorije bez
redova nema dodatnog vremenskog ograničenja.

Narodno pozorište ima dve sale i obe su u katalogu prostorija. `NP-1` radi
svakog radnog dana od 16 časova, a `NP-2` samo sredom. Ranija zbirna oznaka
`NP-сала` više ne postoji, pa se sredom zaista mogu držati dva časa odjednom.

Model termina ne bira konkretnu salu, pa bi bez dodatnog uslova gledao lokaciju
kao da sve njene sale rade svakog dana. Zato se za svaku salu sa whitelistom
kapacitet lokacije zauzima u terminima kada ta sala ne radi.

## Pravila koja ostaju u kodu

Dozvole za KM-8 su posebna, obavezna CSV lista `ulazi/dozvole_km8.csv`.
Svaki od 60 redova čuva svih osam izvornih kolona i broj reda Excel lista,
nivo škole i mašinski čitljive uslove. Prazna lista ne dozvoljava ništa,
a nedostajuća datoteka je greška. Nepoznata napomena ili neslaganje napomene
sa strukturiranim uslovima je greška pri učitavanju.

Filter se primenjuje pre svih povrataka kandidata prostorija, u punom modelu,
u lokacijskom masteru posebno za A/B, pri naknadnoj dodeli sala i obradi
hintova. Jedinice ostaju nedeljni blokovi 2+1; dozvola jednog časa ne deli
jedinicu od dva časa. Puni model i naknadna dodela imaju zbirnu nedeljnu kvotu.
Proveravač nezavisno proverava svaki čas, stvarnu smenu, nedeljnu kvotu i
susedne časove istog predmeta/grupe čak i kad su upisani u različite sale.
Oznake KM-8 i КМ-8 predstavljaju istu salu.

Raniji prioritet KM-8 za Primenjenu gimnastiku i rezervna namena za
Tradicionalno pevanje ostaju u opštoj tabeli, sada ograničeni na tačne
grupe. Oni ne mogu da zaobiđu zatvorenu listu dozvola.

Primenjena gimnastika sme i u druge sale. Ako je Klasičan balet istog
odeljenja tog dana u Sportskoj gimnaziji, lokacija Primenjene gimnastike se
sa njim obavezno usklađuje. Kvote pet termina u Narodnom pozorištu i subotnji
prioritet Sportske gimnazije ostaju nepromenjeni.
