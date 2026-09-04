# Pravila za izradu rasporeda

Ovaj dokument sadrži početna pravila i poželjne osobine rasporeda časova. Pravila će se dopunjavati i precizirati tokom razvoja.

## Ustanova

Osnovna i srednja baletska škola su **jedna ustanova**: dele nastavnike,
korepetitore i prostorije, pa se raspored rešava kao jedan problem (sva tri
ulazna CSV fajla zajedno). Norma nastavnika i korepetitora je **20 časova
nedeljno u idealnom slučaju**, sabrano kroz obe škole; nekoliko ljudi je iznad
(22–24) i to je dozvoljeno.

## Srednja škola

### Smene i dnevno opterećenje

Srednja škola **nema smene** — radi ceo dan i sme da koristi bilo koji blok
(u praksi 08:00–16:00, ređe kasnije). Dnevno odeljenje sme da ima najviše
**4 igračka i 4 opšta časa**.

### Dvočasi

- **Glavni predmet** (Klasičan balet 12č, Savremena igra 10č, Narodna igra 10č)
  je **uvek dvočas, tačno jedan dnevno, nikad dva u istom danu**. Iz toga sledi
  da odseci sa 12 časova glavnog predmeta imaju čas i **subotom** (6 dvočasa).
- Ostali igrački predmeti sa neparnim fondom: dvočas + samostalan čas (3 = 2+1).
- **Repertoar i Karakterne igre treba kombinovati** (raspoređivati zajedno).
- Predmeti sa fondom 1 (npr. Solfeđo u osnovnoj) nisu dvočasi.

### Subota

- Subotom se prvo popunjavaju sale Sportske gimnazije.
- Nastava treba da se završi do 13:15 (zaključno sa blokom 6).
- Ako raspored nije moguće napraviti u tom okviru, dozvoljeni su blokovi 7 i 8,
  odnosno rad najkasnije do 15:05, ali ih solver snažno izbegava.
- Nastava posle 15:05 subotom nije dozvoljena.

### Polugrupe

Odeljenja narodnog odseka se za deo predmeta dele na polugrupe `А` i `Б`
(`I5А`, `I5Б`); to su **ista deca** kao `I5`, pa se polugrupa i celo odeljenje
ne smeju preklapati u vremenu. Istovremeni čas obe polugrupe nije obavezan.

### Opšti predmeti

- Jedan čas sme da pokrije **najviše 3 odeljenja**; grupisanje nije fiksno —
  solver sme da bira (u ulazu je zapisano prošlogodišnje grupisanje).
- **Verska nastava i Građansko vaspitanje** istog razreda drže se
  **istovremeno** (učenici pohađaju jedno od ta dva).
- Repertoar savremene igre i Igre XX veka **traže salu iako nemaju
  korepetitora** (spisak `SALA_BEZ_KOREPETITORA` u loaderu).

### Igrački predmeti

Za jedan čas igračkog predmeta potrebni su:

- jedno odeljenje;
- jedan nastavnik;
- jedan korepetitor;
- jedna sala.

### Opšti (obični) predmeti

Za jedan čas opšteg predmeta potrebni su:

- jedno ili više odeljenja;
- jedan nastavnik;
- nije potreban korepetitor;
- jedna učionica.

## Osnovna škola

### Dnevno opterećenje

Učenici osnovne baletske škole smeju da imaju najviše **4 časa dnevno**.
Ovo je čvrsto pravilo i važi u obe smene i u obe nedelje rasporeda.

### Klasičan balet

- Nedeljni fond Klasičnog baleta je **10 časova**.
- Tih 10 časova se obavezno raspoređuje kao **tačno jedan dvočas svakog
  radnog dana, od ponedeljka do petka**.
- Ovo je čvrsto pravilo: nijedan radni dan ne sme biti preskočen, dva dvočasa
  ne smeju biti spojena istog dana, a nijedan od ovih časova ne sme biti
  prebačen na subotu.

### Igrački predmeti

Za jedan čas igračkog predmeta potrebni su:

- jedno odeljenje;
- jedan nastavnik;
- jedan korepetitor;
- jedna sala.

### Opšti (obični) predmeti

Za jedan čas opšteg predmeta potrebni su:

- jedno ili više odeljenja;
- jedan nastavnik;
- nije potreban korepetitor;
- jedna učionica.

### Smene

Osnovna škola radi u dve smene:

- prva smena: 08:00–11:20;
- druga smena: 15:15–20:00.

Organizacija smena po razredima:

- u prvom razredu odeljenje 13 je uvek u popodnevnoj smeni, dok ostala odeljenja menjaju smene;
- u drugom razredu odeljenje 23 je uvek u popodnevnoj smeni, dok ostala odeljenja menjaju smene;
- u trećem razredu odeljenje 33 je uvek u popodnevnoj smeni, dok ostala odeljenja menjaju smene;
- četvrti razred nema odeljenje koje je uvek u popodnevnoj smeni.

Pripremno odeljenje `П1` ima nedeljni fond od **3 časa**, koji se održavaju kao
tri pojedinačna časa: ponedeljkom, sredom i petkom u bloku 13 (18:30–19:15).
Časovi se ne spajaju u dvočase.

Poželjno je da odeljenja koja menjaju smene budu simetrično raspoređena.
Odeljenje 14 nema parnjaka u suprotnoj smeni, ali i dalje redovno menja smene
iz nedelje u nedelju; zahtev za simetriju na njega se ne primenjuje.

## Učionice, sale i lokacije

Spisak prostorija je u `ulazi/prostorije.csv` (18 prostorija, izvučene iz
prošlogodišnjeg rasporeda — nisu se menjale). Kolona `приоритет` još nije
popunjena.

### Knez Miletina

- šest redovnih sala;
- `KM-3` i `KM-6` su manje sale. Najčešće se koriste za OBŠ, a u SBŠ za
  sporedne predmete kada nema dovoljno prostora;
- sala br. 8, u kojoj se načelno održava **Primenjena gimnastika**, jer su u
  njoj gimnastički rekviziti, a neravan pod nije pogodan za igračke predmete;
- četiri učionice;
- jedna biblioteka, koja je najmanja učionica i koristi se za opšte predmete
  samo u nuždi;
- jedna videoteka, koja se koristi isključivo za predmet **Gluma**.

### Sportska gimnazija

- tri sale;
- jedna učionica.
- Predmeti **Narodna igra – glavni predmet** i **Repertoar narodne igre**
  održavaju se isključivo u salama `SG-1`, `SG-2` i `SG-3`.
- Za **Narodnu igru – glavni predmet** prioritet je `SG-1`. Ako ona nije
  dostupna, `SG-2` ili `SG-3` prvenstveno se dodeljuju odeljenju `IV5`, koje
  ima najmanje učenika; odstupanje za druga odeljenja je lošije rešenje.

### Narodno pozorište

- jedna sala;
- može se koristiti samo od 16:00 do 17:40;
- koristi se samo za predmet **Repertoar klasičnog baleta**;
- `IV1` ima u toj sali **dva dvočasa nedeljno**;
- `IV2` ima u toj sali **dva dvočasa nedeljno**;
- preostali **peti termin** u nedelji popunjava se jednim dvočasom predmeta
  Repertoar klasičnog baleta za **`III1` ili `III2`**; solver sme da izabere
  koje od ta dva odeljenja koristi taj termin ako to olakšava raspored.

Svaki od ovih termina u Narodnom pozorištu je dvočas **16:00–17:40**.

### Posebne prostorije i prioriteti

- Informatika se održava u specijalnoj učionici.
- Gluma se održava isključivo u videoteci.
- Primenjena gimnastika u načelu se održava u `KM-8`, ali sme da se održi u
  bilo kojoj sali. Ako se časovi Klasičnog baleta nekog odeljenja održavaju u
  Sportskoj gimnaziji, časovi Primenjene gimnastike tog odeljenja moraju se
  održati na istoj lokaciji, како učenici не би мењали локацију.
- `KM-8` nije pogodna za igračke predmete zbog neravnog poda. Izuzetno, u njoj
  sme da se održava **Tradicionalno pevanje**, jer sala ima klavir, a učenici
  mogu da sede na podu. Drugi predmeti nisu potvrđeni kao dozvoljeni u `KM-8`.
- Sala br. 4 je najveća i prioritetno se koristi za **Klasičan balet —
  glavni predmet**.
- Sale br. 1, 2 i 5 jednake su veličine i koriste se za srednju školu.
- Sala br. 2 prioritetno se koristi za **Karakterne igre**.
- Sala br. 5 prioritetno se koristi za **Savremenu igru**, **Repertoar
  savremene igre** i **Improvizacije**.
- Odeljenja sa indeksima `1` i `2` pripadaju odseku Klasičan balet, sa
  indeksima `3` i `4` odseku Savremena igra, a sa indeksom `5` odseku Narodna
  igra.
- Na odseku Klasičan balet glavni predmeti su Klasičan balet — glavni predmet,
  Repertoar klasičnog baleta i Duetna igra; Savremena igra i Karakterne igre
  su sporedni predmeti.
- Na odseku Savremena igra glavni predmeti su Savremena igra — glavni predmet,
  Repertoar savremene igre i Improvizacije; Klasičan balet i Igre XX veka su
  sporedni predmeti. Iako je sporedan, Klasičan balet je bolje smestiti u veću
  salu.
- Na odseku Narodna igra glavni predmeti su Narodna igra — glavni predmet i
  Repertoar narodne igre; Klasičan balet, Karakterne igre i Savremena igra su
  sporedni predmeti. Repertoar narodne igre sme u manje sale Sportske
  gimnazije, naročito za `IV5`, koje ima 11 učenika.
- Starija odeljenja i glavni predmeti imaju prednost u većim salama u odnosu
  na mlađa odeljenja i sporedne predmete.
- **Repertoar klasičnog baleta** treba raspoređivati u veće sale, naročito za
  starije razrede. Dozvoljene su `KM-1`, `KM-2`, `KM-4`, `KM-5` i `SG-1`, kao
  i posebni termini u Narodnom pozorištu opisani iznad. Predmet ne sme da se
  održava u `KM-3`, `KM-6`, `SG-2` ni `SG-3`.
- Sale imaju prioritete: bolje sale treba koristiti češće, a lošije izbegavati kad god je moguće.
- Učenici smeju promeniti lokaciju najviše jednom u toku dana.
- Pri promeni lokacije **Knez Miletina ↔ Sportska gimnazija**, časovi moraju
  biti neposredno jedan za drugim, bez putnog bloka.
- Pri drugim promenama lokacije između časova mora postojati tačno jedan
  slobodan blok za put.

## Nastavnici i korepetitori

- Pojedini nastavnici nisu dostupni određenim danima (na primer, petkom);
  nastavnici opštih predmeta često rade i u drugim školama.
- Nedostupnost se beleži u `ulazi/nedostupnost.csv`
  (`наставник,дан,од блока,до блока,напомена`). Fajl sadrži potvrđene
  nedostupnosti; prazan fajl bi značio da su svi dostupni.
- Granice opsega su uključive: „od X do Y“ uključuje i blok X i blok Y.
- Časovi **nastavnika i korepetitora treba da budu povezani**, bez praznih
  blokova između angažovanja kad god je to moguće.
- Optimalno dnevno angažovanje nastavnika i korepetitora je najviše četiri
  časa, a čvrsti дневни maksimum je šest časova.
- Kraća pauza je bolja od duže; solver snažno kažnjava svaku pauzu, ali za sve
  osobe osim Ivane Ljujić i Jelene Prvulović broj i trajanje pauza nisu čvrsta
  ograničenja.
- Za **Ivanu Ljujić** i **Jelenu Prvulović** ostaje čvrsto pravilo: najviše
  jedna pauza nedeljno, duga najviše dva časovna bloka.
- Dušan Ilijin radi u školi ponedeljkom, četvrtkom i petkom. Predaje istoriju
  i grupi IV3,IV5, koja je ranije bila označena privremenim nazivom `nastavnik
  istorije br.2`. Njegov ukupan fond istorije je 14 časova.
- Kosta Milanović je korepetitor za Repertoar klasičnog baleta u odeljenjima
  IV1 i IV2, a Mirjana Anđelković za Primenjenu gimnastiku u odeljenjima 24,
  31, 32 i 34 i Istorijsko balske igre u odeljenjima 41, 42 i 43.

## Vremenski blokovi

| Broj | Početak | Kraj |
|---:|:---:|:---:|
| 1 | 08:00 | 08:45 |
| 2 | 08:50 | 09:35 |
| 3 | 09:45 | 10:30 |
| 4 | 10:35 | 11:20 |
| 5 | 11:40 | 12:25 |
| 6 | 12:30 | 13:15 |
| 7 | 13:30 | 14:15 |
| 8 | 14:20 | 15:05 |
| 9 | 15:15 | 16:00 |
| 10 | 16:00 | 16:45 |
| 11 | 16:55 | 17:40 |
| 12 | 17:40 | 18:25 |
| 13 | 18:30 | 19:15 |
| 14 | 19:15 | 20:00 |

## Redosled i poželjne osobine rasporeda

- Predmeti se uglavnom održavaju kao dvočasi (za srednju vidi tačna pravila
  gore; za osnovnu iz prošlogodišnjeg rasporeda sledi isto — igrački dvočasi).
- Obe škole i obe nedelje rešavaju se zajedno, u istom modelu.
- Učenici ne smeju imati prazne časove.
- Izuzetak je promena lokacije koja nije Knez Miletina ↔ Sportska gimnazija,
  kada učenici moraju imati tačno jedan slobodan blok za put. Između Knez
  Miletine i Sportske gimnazije časovi moraju biti neposredno jedan za drugim.
- Poželjno je da odeljenja koja naizmenično menjaju smene budu simetrično raspoređena.
- Za nastavnike i korepetitore kontinuitet časova je snažan prioritet; jedna
  pauza do dva bloka nedeljno je izuzetak, ne uobičajena organizacija rada.

## Dvofazno rešavanje

Isti model se rešava u dve faze unutar jednog ukupnog vremenskog ograničenja.
Prva, kratka faza nema funkciju cilja i traži bilo koji raspored koji zadovoljava
sva čvrsta pravila. Druga faza uključuje postojeću funkciju cilja i kao obične
CP-SAT hintove dobija vrednosti rešenja prve faze. Hint se ne učitava iz CSV-a,
artifacta niti drugog fajla i nije dodatno ograničenje modela.

Ako druga faza ne stigne da poboljša raspored, dopustivo rešenje prve faze ostaje
rezultat i moraju se sačuvati oba CSV fajla i HTML pregled. Zaustavljanje posle
prvog pronađenog rešenja nije dokaz validacije: oba izlaza i dalje prolaze kroz
nezavisni proveravač.

## Napomene za dalju razradu

Otvorena pitanja su izdvojena u [otvorena-pitanja.md](otvorena-pitanja.md).
Od prvobitnog spiska ostali su prioriteti sala i dostupnost nastavnika po danima.
Informatika ima jednu specijalnu učionicu (prošle godine `KM-uč1`); smene po
odeljenjima i dvočasi su sada zapisani gore i u ulaznim fajlovima.

- Izuzetak za peti čas jutarnje smene: Solfeđo 41 kod Marije Cvetković,
  Solfeđo 42 kod Sonje Pane Virijević i Solfeđo 43 kod Jelene Mihailović
  Krasić sme da bude u bloku 5 (11:40–12:25) kada je njihova smena jutarnja.
  U istom bloku sme da bude i Istorijsko balske igre kod Teodore Martinovski,
  ali isključivo za odeljenje 41. Time se ne menja čvrsti dnevni maksimum od
  četiri stvarna časa za učenike osnovne škole niti zabrana praznih časova:
  Ovaj čas u bloku 5 može neposredno da prati Klasičan balet u blokovima 3–4,
  dok raspored Klasičnog baleta u blokovima 2–3 ne može da ostavi blok 4 prazan.
  Izuzetak ne važi ni za jedan drugi predmet, nastavnika ili odeljenje.
- Ista fizicka osoba je jedan rasporedni resurs bez obzira da li u konkretnom casu nastupa kao nastavnik ili korepetitor; ne sme istovremeno obavljati obe uloge na razlicitim casovima.

### Istorija — Aleksandar Bošković

- Aleksandar Bošković preuzima sve tri grupe II razreda iz istorije: `II1,II3`, `II2,II4` i `II5`, ukupno 6 časova nedeljno.
- Zbog rada u drugoj školi dostupan je radnim danima tek od 7. bloka (od 13:30).
- Njegov fond se raspoređuje u tačno dva radna dana: svakog izabranog dana ima po jedan čas u sve tri grupe, ukupno 3 uzastopna časa.

### Istorija — Dušan Ilijin

- Dušan Ilijin predaje istoriju i spojenoj grupi IV3,IV5 (ranije označeno kao „nastavnik istorije br.2“).
- U školi je isključivo ponedeljkom, četvrtkom i petkom; utorkom i sredom radi u drugoj školi.
- Nijedna grupa ne sme imati dva časa istorije u istom danu; ovo je čvrsto pravilo za istoriju.
- Dušan Ilijin sme imati ukupno najviše dva prazna bloka između svojih časova u toku cele nedelje.
