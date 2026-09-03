# Pravila prostorija

Ovaj dokument opisuje podatke o prostorijama iz Excel lista `Prostorije` i
način na koji će ih raspoređivač tumačiti. Normalizovani podaci su u
`ulazi/pravila_prostorija.csv`, a vremenska dostupnost u
`ulazi/dostupnost_prostorija.csv`. Postojeći aktivni katalog
`ulazi/prostorije.csv` ostaje nepromenjen.

## Izvor i zapis

Izvor je dostavljena Excel tabela za školsku 2026/27, list `Prostorije`.
Svaka od 24 popunjene ćelije u kolonama od `obavezno` do `zabranjeno`
normalizovana je u jedan red. Ti redovi predstavljaju 57 atomskih preslikavanja
predmeta i odeljenja na prostoriju. Više predmeta u jednom izvornom pravilu
razdvaja se tačkom i zapetom; `*` znači sve predmete, uz izuzetke navedene u
napomeni.

Kolona `odeljenja` je CSV-lista oznaka. Prazna vrednost znači sva odeljenja.
Oznake su usklađene sa postojećim ulazima (`IV1`, a ne Excel zapis `IV-1`).
Kolona `oblik časa` je prazna kada pravilo važi za sve oblike, a `dvočas`
kada je Excel izričito ograničio pravilo na dvočas.

Nazivi predmeta su usklađeni sa aktivnim ulazima gde je značenje jasno, na
primer `Računarstvo i informatika`. Sporni navod za `SG-1` ostavljen je kao
`Repertoar savremene igre`, tačno prema Excelu, dok administrator ne potvrdi da
li je trebalo da piše `Repertoar narodne igre`.

## Pet nivoa

- `obavezno` i `zabranjeno` su čvrsta pravila. Obavezno zahteva jednu od
  prostorija navedenih na tom nivou, a zabranjeno isključuje prostoriju.
- `prvi` i `drugi` su meki prioriteti, tim redom od boljeg ka slabijem.
- `izuzetno` je meko pravilo najnižeg prioriteta: prostorija se koristi samo
  kada bolje rešenje nije dostupno.

Konkretnije pravilo za predmet i odeljenje ima prednost nad wildcard pravilom
`*`. Zato su, na primer, izričito navedeni predmeti za biblioteku dozvoljeni
izuzetno iako wildcard red zabranjuje sve ostalo. Kada više prostorija ima isti
nivo za isti slučaj, one su ravnopravne alternative; redosled CSV redova ne
predstavlja dodatni prioritet.

## Vremenska dostupnost

`dostupnost_prostorija.csv` ima whitelist semantiku: ako je prostorija navedena
u fajlu, sme da se koristi samo u navedenim danima i uključivim opsezima
blokova. `NP-1` je navedena od ponedeljka do petka u blokovima 10–11, a `NP-2`
samo sredom u blokovima 10–11. Excel navodi 16:00–17:30, dok blok 11 traje do
17:40; odstupanje je sačuvano u napomeni i ostaje otvoreno pitanje.

## Inventar iz Excel tabele

Excel navodi 19 prostorija:

| Lokacija | Prostorije |
|---|---|
| Knez Miletina | sale 1, 2, 3, 4, 5, 6 i 8; učionice 1, 2, 3 i 7; biblioteka; videoteka |
| Sportska gimnazija | sale 1, 2 i 3; muzička učionica |
| Narodno pozorište | sale 1 i 2 |

U novim CSV fajlovima koriste se oznake `KM-1`–`KM-8`, `KM-uč1`–`KM-uč7`,
`KM-biblioteka`, `KM-videoteka`, `SG-1`–`SG-3`, `SG-muzuč`, `NP-1` i `NP-2`.
Stari aktivni katalog ima 18 prostorija i jednu zbirnu oznaku `NP-sala`; ovaj
PR namerno ne menja taj katalog niti proverava nove NP oznake prema njemu.

Napomene iz Excel inventara koje još nisu dovoljno precizne za mašinsko pravilo
ostaju dokumentovane: `KM-1` i `KM-2` su veće sale; `KM-3` i `KM-6` su male i
pretežno za osnovnu školu; `KM-4` je najveća sala u Knez Miletinoj; `KM-5` je
veća; `KM-8` je mala; `KM-uč7` je najveća učionica i namenjena najbrojnijim
grupama; `SG-1` je najveća sala u Sportskoj gimnaziji.

## Trenutno važeća pravila dok se pitanja ne razreše

Nova pravila još nisu povezana sa solverom i sama po sebi ne menjaju raspored.
Do razrešenja pitanja i posebne implementacije i dalje važe postojeća pravila:

- predmeti `Narodna igra – glavni predmet` i `Repertoar narodne igre` koriste
  sale `SG-1`, `SG-2` i `SG-3`; za glavni predmet prioritet je `SG-1`, a
  odstupanje ka `SG-2`/`SG-3` prvenstveno se daje odeljenju `IV5`;
- postojeća zbirna `NP-sala` koristi se za `Repertoar klasičnog baleta` u
  dvočasu 16:00–17:40: `IV1` i `IV2` po dva puta nedeljno, a peti termin dobija
  `III1` ili `III2`;
- učenici menjaju lokaciju najviše jednom dnevno; između Knez Miletine i
  Sportske gimnazije časovi su neposredno jedan za drugim, a za svaku drugu
  promenu lokacije postoji tačno jedan slobodan blok za put.

Loaderi za nove CSV fajlove trenutno samo parsiraju i samostalno validiraju
podatke. Solver i proveravač ih još ne učitavaju; njihovo povezivanje je zaseban
naredni korak, posle odgovora na [otvorena pitanja](otvorena-pitanja.md).
