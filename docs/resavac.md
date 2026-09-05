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

Nedelje se rešavaju zajedno u jednom modelu. Time izbor dobrog rasporeda za A
ne može naknadno da učini B nemogućom. Časovi srednje škole, stalnih smena i P1
dele isti dan, blok i prostoriju u obe nedelje. Naizmenične smene nisu strogo
ogledalo:

- smena iz ulaznog CSV-a određuje dozvoljene blokove odeljenja u nedelji A;
- njena inverzna smena određuje dozvoljene blokove u nedelji B;
- naizmenična odeljenja osnovne škole dobijaju zasebne odluke za dan, blok i
  prostoriju u svakoj nedelji;
- srednja škola, odeljenja `13`, `23` i `33`, kao i P1, ostaju identični u obe
  nedelje jer su pri rešavanju B fiksirani na rezultat A.

Obe nedelje dele jedno ukupno zadato vremensko ograničenje. Resursi i učenička
preklapanja proveravaju se zasebno za A i B, a oba dobijena CSV fajla zatim
prolaze kroz nezavisni proveravač. Prošlogodišnja referenca ne sadrži dve verzije
rasporeda istog odeljenja, pa ne daje osnov da se nametne jača simetrija.

## Čvrsta ograničenja

Rešavač ne sme da prekrši:

- fondove i grupisanje iz ulaznih CSV fajlova;
- smene osnovne škole i posebne termine P1;
- zauzetost odeljenja i polugrupa, nastavnika, korepetitora i prostorija;
- subotom završetak najkasnije do 15:05, uz snažnu prednost završetka do 13:15
  i korišćenja sala Sportske gimnazije; sama subota se dodatno naplaćuje, pa
  je solver koristi samo kad je jeftinija od alternative;
- tip prostorije i posebnu učionicu za informatiku;
- sale `SG-1`, `SG-2` ili `SG-3` za Narodnu igru – glavni predmet i
  Repertoar narodne igre;
- dvočase igračkih predmeta i jedan glavni dvočas srednje škole dnevno;
- najviše četiri časa dnevno za odeljenja osnovne škole;
- najviše četiri igračka i četiri opšta časa srednjeg odeljenja dnevno;
- bez praznih časova učenika, osim tačno jednog putnog bloka pri promeni
  lokacije;
- najviše jednu promenu lokacije po odeljenju u toku dana;
- istovremenost Verske nastave i Građanskog vaspitanja;
- nedostupnost nastavnika iz `ulazi/nedostupnost.csv`.
- poseban raspored istorije II razreda kod Aleksandra Boškovića: svih šest
  časova je posle 13:30 i složeno u dva radna dana po tri uzastopna časa,
  sa po jednim časom svake od tri grupe u oba dana.
- istoriju kod Dušana Ilijina ponedeljkom, četvrtkom i petkom, tako da su dva
  časa svake grupe različitim danima, a zbir praznih blokova između njegovog
  prvog i poslednjeg časa po danima nije veći od dva nedeljno.

Oznake `?` i `korepetitor br.1` tretiraju se kao ista buduća osoba, iako su u
ulazima privremeno zapisane različito.

Model istovremeno bira termine, lokacije i konkretne prostorije. Posebna
pravila, uključujući obaveznu `KM-uč1` za informatiku i termine `NP-sala`, važe
u obe faze. Pri dodeli konkretnih prostorija Narodna igra – glavni predmet
preferira `SG-1`; odstupanje na `SG-2` ili `SG-3` manje se kažnjava za `IV5`
nego za ostala odeljenja. Prioritet se primenjuje i pri zasebnoj dodeli jedne
nedelje i pri zajedničkoj dodeli prostorija za obe nedelje.

## Optimizacija i provera

Prazni časovi učenika i promena lokacije modelirani su kao čvrsta pravila.
Za svako odeljenje i dan model bira kompaktan dnevni obrazac: prvi i poslednji
blok, ukupan broj časova, postojanje i položaj putnog bloka, kao i lokaciju pre
i posle njega. Ako odeljenje ostaje na jednoj lokaciji, svi dnevni časovi su
povezani. Ako jednom promeni lokaciju između Knez Miletine i Sportske
gimnazije, dve celine moraju biti neposredno jedna uz drugu. Za druge promene
lokacije između njih postoji tačno jedan slobodan blok za put. Druga promena
lokacije, povratak na prvu lokaciju i svaka druga praznina nisu dozvoljeni.

Ivana Ljujić i Jelena Prvulović imaju čvrsto ograničenje od najviše jedne
pauze nedeljno, duge najviše dva bloka. Dušan Ilijin može imati više pauza,
ali njihov zbir po praznim blokovima u celoj nedelji ne sme biti veći od dva.
Za sve ostale nastavnike i korepetitore broj i trajanje pauza nisu čvrsti, ali
svaka pauza i dalje pogoršava cilj solvera. Isto pravilo primenjuje nezavisni
proveravač.
Svaka osoba ima čvrsti dnevni maksimum od šest časova, dok cilj dodatno
kažnjava peti i šesti čas kako bi optimalno dnevno angažovanje bilo do četiri.

Svaki rezultat se zato odmah prosleđuje nezavisnom proveravaču. Komanda završava
statusom 1 ako raspored nije pronađen ili ako proveravač pronađe makar jednu
grešku. CSV ostaje sačuvan kao kandidat za sledeću iteraciju, ali se ne smatra
konačnim rasporedom.

Glavni model se rešava dvofazno: prva faza bez funkcije cilja traži
dopustivo rešenje, a druga faza uključuje postojeći cilj i dobija rešenje prve
faze preko običnih CP-SAT `add_hint` poziva. Ako optimizacija ne završi,
dopustivo rešenje prve faze se ipak proverava i čuva kao CSV i HTML pregled.
Tokom druge faze log beleži vreme, vrednost cilja i najbolju granicu svakog
novog incumbenta, a na kraju i relativni gap, broj grana i broj konflikata.

Posle isteka zajedničkog vremenskog budžeta faza 1 i 2, zaštita kvaliteta
materijalizuje kandidate sa konkretnim prostorijama i oba nezavisno proverava.
Kompletan i ispravan prethodni raspored A+B, zajedno sa svojim prostorijama,
služi kao besplatna regresiona granica. Ako takvog hinta nema, kandidat prve
faze dobija zasebnu proveru dodele prostorija sa starim limitom od 60 sekundi.
Prethodni A+B raspored mora proći i međunedeljna pravila zajedničkog modela:
časovi stalnih smena i srednje škole moraju imati isti termin i prostoriju.
Među kandidatima bez grešaka bira se najmanji zbir upozorenja obe nedelje, a pri
istom zbiru prednost ima faza 2. Ova dodatna evaluacija radi nakon solvera i
ne umanjuje niti menja njegov zadati vremenski budžet.

## Hladni start bez upotrebljivog hinta

Kada hinta nema ili je zastareo, pun model se pokazao pretežak za jedan solve,
pa se prvo rešava lakši **lokacijski master**: bira dan, blok i lokaciju, ali ne
i konkretnu salu. Njegovo rešenje se zatim dopunjava u dva koraka:

1. **Tačna dodela soba** uz zakucane termine i lokacije. Traje nekoliko sekundi.
2. Ako taj korak ne uspe, **isti termini** se rešavaju punim modelom u kojem
   su i lokacije i sale ponovo slobodne.
3. Ako ni to ne prođe, isti model se rešava još jednom, s tim da časovi iz
   UNSAT jezgra soba smeju i da promene termin.
4. Ako je i to pretesno, oslobađaju se svi časovi koje master drži na istoj
   lokaciji istog dana kao jezgro — jedan dan jedne zgrade. Ostatak nedelje
   ostaje zakucan, pa je to i dalje popravka, a ne nova pretraga.

Drugi korak postoji zato što master vidi samo koliko časova lokacija prima u
jednom trenutku, a ne koja sala može da primi koji čas. Tipičan primer: `SG-1`
je obavezna za Narodnu igru i zauzeta je u blokovima 1–2 i 4–5, pa tri dvočasa
klasičnog baleta u blokovima 2–4 ostaju za samo dve preostale sale. Po broju
časova po trenutku sve staje, a po salama ne staje. Umesto novog master solvea,
koji traje stotinama sekundi, isti termini se dopune za nekoliko sekundi.

Tek ako i to padne, master dobija zabranu nad dodelom iz UNSAT jezgra soba i
traži susedno rešenje. Log tada ispisuje i sadržaj jezgra — predmet, odeljenje,
dan, blok i sale među kojima se biralo — da se uzrok vidi bez ponavljanja
pokretanja.

Prethodni raspored (`--hintovi nedelja_a.csv --hintovi-b nedelja_b.csv`)
skraćuje prvu fazu sa više minuta na oko sekund. Termini iz CSV-a se uparuju
sa jedinicama modela i prvo se pokušavaju kao **fiksirane** vrednosti
(`fix_variables_to_their_hinted_value`): ako je stari raspored i dalje
dopustiv, to je odmah rešenje prve faze. Ako ulaz više ne dozvoljava stari
raspored, CP-SAT to javi za deo sekunde i pretraga prve faze ide od nule.
Obični, nefiksirani hintovi ovde ne pomažu: hint pokriva samo termine, a CP-SAT
ne uspeva da ga dopuni do potpunog rešenja. Nedelja B je potrebna zato što
naizmenična odeljenja osnovne škole imaju zasebne termine u B.

Hladni master je najuže grlo: na četiri radnika traje od deset do preko
dvadeset minuta, i to vreme jako varira po semenu. Zato radni tok koristi
granicu od 5400 sekundi. To je gornja granica, a ne trajanje — čim postoji
upotrebljiv hint, prva faza se vraća na oko sekund.

Podrazumevano vremensko ograničenje je pet minuta za zajednički model obe
nedelje. Može se promeniti:

```bash
python -m src.resavac \
  --izlaz resenja/2026-27 \
  --vremensko-ogranicenje 900 \
  --broj-radnika 8 \
  --seme 1
```

Isto seme, isti ulazi i isti broj radnika daju ponovljiv polazni model, ali
paralelna CP-SAT pretraga ne garantuje identičan rezultat na svakoj platformi.
