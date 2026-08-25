# Format CSV rešenja

Rešenje rasporeda je CSV datoteka sa sledećim kolonama:

| Kolona | Značenje | Primer |
|---|---|---|
| `dan` | Naziv nastavnog dana malim slovima | `ponedeljak` |
| `blok` | Broj bloka od 1 do 14 | `9` |
| `predmet` | Latinični naziv predmeta iz ulaznog CSV-a | `Solfeđo` |
| `odeljenja` | Jedno ili više odeljenja, razdvojena znakom `;` | `I1;I2;I3` |
| `nastavnik` | Ime nastavnika na latinici | `Milan Petrović` |
| `korepetitor` | Ime korepetitora ili prazno polje | `Ana Jovanović` |
| `prostorija` | Latinična oznaka iz `ulazi/prostorije.csv` | `KM-2` |

Jedan red predstavlja jedan blok od 45 minuta. Dvočas se zapisuje kao dva
reda sa uzastopnim brojevima blokova. Kada više odeljenja zajedno sluša isti
čas, navode se u jednom redu i razdvajaju tačkom-zarezom. Redosled redova nije
bitan.

Primer:

```csv
dan,blok,predmet,odeljenja,nastavnik,korepetitor,prostorija
ponedeljak,9,Istorija igre,I1;I3,Miloš Lazarov,,KM-uč2
ponedeljak,10,Klasičan balet,I5A,Valentina Trajković,Ksenija Ristić,KM-2
ponedeljak,11,Klasičan balet,I5A,Valentina Trajković,Ksenija Ristić,KM-2
```

Ovo su samo ilustrativni redovi iz stvarnih ulaza, ne kompletan raspored.

## Nedelje A i B

Kompletan raspored čine **dve CSV datoteke**, po jedna za svaku nedelju.
Crvena i plava smena se ogledaju: u nedelji A crvena je ujutru, a u nedelji B
plava je ujutru. Svaka datoteka se proverava zasebno:

```bash
python -m src.proveravac nedelja_a.csv --jutarnja-smena crvena
python -m src.proveravac nedelja_b.csv --jutarnja-smena plava
```

Srednja škola i stalno-popodnevna odeljenja imaju isti raspored u obe nedelje.
Proveravač za sada ne poredi dve datoteke i ne proverava njihovu međusobnu
simetriju; proverava samo da je svaka nedelja zasebno ispravna.

## Pokretanje provere

Iz korena repozitorijuma:

```bash
python -m src.proveravac putanja/do/resenja.csv
```

Ako opcija nije navedena, podrazumeva se nedelja A, u kojoj je crvena smena
ujutru. Za nedelju B koristi se:

```bash
python -m src.proveravac putanja/do/resenja.csv --jutarnja-smena plava
```

Program završava statusom 0 kada nema grešaka i statusom 1 kada rešenje krši
obavezno pravilo. Poželjna svojstva prikazuju se kao upozorenja i ne obaraju
proveru.

## Šta se proverava

- struktura CSV-a i postojanje svih oznaka u ulazu;
- nedeljni fond svakog predmeta za svako odeljenje;
- broj stvarnih zajedničkih časova i dozvoljeno pregrupisavanje opštih predmeta;
- fond korepeticije;
- smene, posebna smena P1 i nedostupnost nastavnika;
- sudari odeljenja i polugrupa, nastavnika, korepetitora i prostorija;
- odgovarajući tip prostorije i posebna pravila za informatiku i NP-salu;
- najviše tri odeljenja na zajedničkom času, osim Verske nastave i Građanskog;
- istovremenost Verske nastave i Građanskog vaspitanja;
- obavezni dvočasi igračkih predmeta srednje škole;
- dnevno opterećenje odeljenja srednje škole;
- prazni časovi učenika i promene lokacije.

Pauze nastavnika i nepotpuni obrasci dvočasa osnovne škole trenutno se
prijavljuju kao upozorenja, jer su u pravilima označeni kao poželjne osobine.
Za posebnu smenu P1 proveravač privremeno tumači fond od šest časova kao
dvočas ponedeljkom, sredom i petkom u blokovima 13–14 i prikazuje upozorenje,
jer odgovor na to otvoreno pitanje još nije potvrđen.
