# Referenca: raspored 2025/26

Prošlogodišnji raspored, izvučen iz ručno vođene Excel tabele
`Raspored22092025.xlsx`. Tabela se ne nalazi u repozitorijumu.

> **Ovo nije ulaz.** Ulazni podaci su u `ulazi/`. Ovde je zabeleženo kako je
> raspored stvarno izgledao prošle godine.

## Čemu služi

1. **Provera modela.** Ovaj raspored je radio u praksi. Ako model ograničenja
   proglasi da krši pravila, greška je u modelu. To je najpouzdaniji test koji
   imamo.
2. **Topli start.** CP-SAT prima početno rešenje preko `AddHint()`. Raspored se
   iz godine u godinu menja samo delimično.
3. **Oblik izlaza.** Kolone su ujedno predlog onoga što solver treba da proizvede.

## Pismo

Sve je **latinicom, sa dijakritikom** (`Đorđina Ubović`, ne `Djordjina`).
Preslikavanje ćirilica ↔ latinica je jednoznačno u oba smera, pa se ovaj fajl
spaja sa ćiriličnim `ulazi/` kroz determinističku konverziju. Transliteracija
usput poravnava greške mešanog pisma iz izvorne tabele: `Марија` i `Marija`
postaju isti niz znakova, kao i `КИ` i `KИ`.

## `raspored_2025_26.csv`

565 redova.

| Kolona | Značenje |
|---|---|
| `dan` | Ponedeljak … Subota |
| `blok` | **početni** blok, 1–14 (vidi `docs/pravila-rasporeda.md`) |
| `lokacija` | Knez Miletina 8, Sportska gimnazija, Narodno pozorište |
| `sala` | jedinstvena oznaka, `KM-`/`SG-`/`NP-` + prostorija |
| `odeljenje` | `I1`…`IV4`, `11`…`44`; spisak razdvojen zarezom; `IV*` = ceo razred |
| `predmet` | pun naziv (vidi `predmeti.csv`) |
| `predmet_kod` | šifra kako piše u izvornoj tabeli |
| `nastavnik`, `korepetitor` | puna imena gde su razrešena (vidi `parovi.csv`) |
| `nedelja` | `A` ili `B` za osnovnu, prazno inače |
| `pouzdanost` | šta je pouzdano u tom redu |
| `napomena` | slobodan tekst kad nešto nije jednoznačno |

### Vrednosti kolone `pouzdanost`

| Vrednost | Redova | Značenje |
|---|---|---|
| `potpuno` | 376 | sve poznato |
| `opsti;bez_nastavnika` | 125 | opšti predmeti; nastavnik nije upisan u tabeli |
| `bez_nastavnika` | 26 | uglavnom Solfeđo, upisan bez nastavnika |
| `opsti;bez_odeljenja` | 24 | u ćeliji piše samo šifra predmeta |
| `nepotpuno` | 12 | u tabeli fali predmet ili nastavnik |
| `samo_ime` | 2 | par `Kristina / Ana` nije razrešen, vidi dole |

### Tri različita zapisa u izvornoj tabeli

Ista tabela koristi tri formata, i sva tri su ovde svedena na isti oblik:

1. **Srednja, igrački predmeti** — dva reda, `odeljenje | nastavnik` iznad
   `predmet | korepetitor`.
2. **Osnovna** — jedan red, `41 | Ula / Ksenija`. Goli broj odeljenja znači
   **Klasičan balet**; svaki drugi predmet ima šifru ispred (`PG 11`, `SOL 31`).
3. **Opšti predmeti** — u redovima učionica, `SRP I1,2,3` ili `IV građ`. Jedan
   čas pokriva više odeljenja odjednom, a nastavnik uglavnom nije upisan.

### Kolona `nedelja`

Na 52 mesta se u istoj sali, istog dana, u istom bloku i za isti predmet
pojavljuju **dva** odeljenja osnovne škole. To nisu preklapanja — to su dve
nedelje koje se smenjuju, zapisane jedna ispod druge. Gornji red je `A`, donji `B`.

Provera na uzorku pokazuje da `A` odgovara crvenoj, a `B` plavoj smeni, ali
prošlogodišnja podela po bojama nije nigde zapisana, pa su oznake namerno
neutralne. **Ne tumačiti `A` kao „crvena“ bez provere.**

### Dvočasi

Ogromna većina igračkih časova počinje na **neparnom bloku** i zauzima blokove
(1–2), (3–4), (5–6) i tako dalje. U koloni `blok` upisan je **početni** blok.

### Subota i Narodno pozorište

Subotom je zabeleženo 19 časova, skoro sve Klasičan balet i Repertoar KB —
posredan odgovor na pitanje koji predmeti smeju subotom, ali zaključak iz
prakse, ne zapisano pravilo.

Svih 5 časova u Narodnom pozorištu su `RKB` i svi u bloku 10 (16:00–16:45), što
se poklapa sa pravilom da se ta sala koristi samo od 16 do 18 i samo za
Repertoar KB.

## `parovi.csv`

Izvorna tabela osnovnu školu piše skraćeno, `Ula / Ksenija` — samo lična imena.
Ta imena se **ne razrešavaju globalno nego po paru**, jer ista skraćenica ume da
označi dve različite osobe:

```
Karolina / Marija  ->  Karolina Marjanović   /  Marija Radojević
Tea / Marija       ->  Tea Milovanović       /  Marija Cvetković
```

`Marija Cvetković` i `Marija Cvetković Kostić` su **dve različite osobe** — ne
spajati ih i ne dopunjavati kraće ime u duže.

Puna imena su pročitana iz listova po nastavniku, gde uz skraćeni par stoji i
pun zapis. Razrešeno je svih 13 parova i upisano direktno u
`raspored_2025_26.csv`; `parovi.csv` služi kao trag odakle šta dolazi.

Jedini nerazrešen par je `Kristina / Ana` (2 reda, petak). Kristina inače ide uz
Anđelu, pa je ovo verovatno zamena ili greška u izvornoj tabeli.

## `predmeti.csv`

Šifra → pun naziv, svih 33.

Nazivi igračkih predmeta su dobijeni direktno. Nazivi opštih predmeta (`SRP`,
`MAT`, `IST`, `FIL`…) su **pročitani sa lista `структура`**, gde uz svakog
nastavnika piše šta predaje — dakle izvedeni, a ne dati. Vredi ih proveriti.

`IXXv` je **Igre dvadesetog veka**. (`I` je Igre, ne Istorija — `XX` je rimski broj.)

## Poznati problemi u izvornoj tabeli

- **Mešano pismo.** `Tеа Milovanović` u listu `структура` počinje latiničnim `T`;
  isto važi za `Marija`/`Марија` i `КИ`/`KИ`. Transliteracija ovo poravnava, ali
  problem i dalje postoji u izvornoj tabeli.
- **Ista osoba, dva zapisa.** `Dragana Veličković` (prošlogodišnja tabela) i
  `Dragana Veličković (Martinovski)` (`ulazi/`); `Jelena Krasić Mihailović` i
  `Jelena Mihailović Krasić` (zamenjen redosled prezimena). Ovde je zadržan
  oblik iz izvorne tabele — namerno se ne skraćuje i ne produžava nijedno ime.
- **Spisak odeljenja se promenio.** Prošle godine 11–13, 21–24, 31–34, 41–44;
  ove godine 11–15, 21–24, 31–34, 41–43 i П1. Odeljenja 14, 15 i П1 su nova,
  44 više ne postoji. Topli start pokriva samo deo rasporeda.

## Napomena za AI agente

- Redovi sa `pouzdanost` različitim od `potpuno` imaju rupe koje su **stvarne**,
  a ne greške izvlačenja. Ne popunjavati ih pogađanjem.
- Nikada ne spajati imena koja se razlikuju samo po dodatnom prezimenu.
- Ovaj direktorijum se ne menja ručno. Ako treba ispraviti podatke, ispravlja se
  izvorna Excel tabela i ponovo izvlači.
