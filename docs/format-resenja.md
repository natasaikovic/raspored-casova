# Format CSV rešenja

Rešenje rasporeda je CSV datoteka sa sledećim kolonama:

| Kolona | Značenje | Primer |
|---|---|---|
| `дан` | Naziv nastavnog dana malim slovima | `понедељак` |
| `блок` | Broj bloka od 1 do 14 | `9` |
| `предмет` | Naziv identičan nazivu u ulaznom CSV-u | `Солфеђо` |
| `одељења` | Jedno ili više odeljenja, razdvojena znakom `;` | `I1;I2;I3` |
| `наставник` | Ime identično imenu u ulaznom CSV-u | `Милан Петровић` |
| `корепетитор` | Ime korepetitora ili prazno polje | `Ана Јовановић` |
| `просторија` | Oznaka iz `ulazi/prostorije.csv` | `KM-2` |

Jedan red predstavlja jedan blok od 45 minuta. Dvočas se zapisuje kao dva
reda sa uzastopnim brojevima blokova. Kada više odeljenja zajedno sluša isti
čas, navode se u jednom redu i razdvajaju tačkom-zarezom. Redosled redova nije
bitan.

Primer:

```csv
дан,блок,предмет,одељења,наставник,корепетитор,просторија
понедељак,9,Историја игре,I1;I3,Милош Лазаров,,KM-уч2
понедељак,10,Класичан балет,I5А,Валентина Трајковић,Ксенија Ристић,KM-2
понедељак,11,Класичан балет,I5А,Валентина Трајковић,Ксенија Ристић,KM-2
```

Ovo su samo ilustrativni redovi iz stvarnih ulaza, ne kompletan raspored.

## Pokretanje provere

Iz korena repozitorijuma:

```bash
python -m src.proveravac putanja/do/resenja.csv
```

Podrazumeva se nedelja u kojoj je crvena smena ujutru. Za suprotnu nedelju:

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
- smene, posebna smena П1 i nedostupnost nastavnika;
- sudari odeljenja i polugrupa, nastavnika, korepetitora i prostorija;
- odgovarajući tip prostorije i posebna pravila za informatiku i NP-salu;
- najviše tri odeljenja na zajedničkom času, osim Verske nastave i Građanskog;
- istovremenost Verske nastave i Građanskog vaspitanja;
- obavezni dvočasi igračkih predmeta srednje škole;
- dnevno opterećenje odeljenja srednje škole;
- prazni časovi učenika i promene lokacije.

Pauze nastavnika i nepotpuni obrasci dvočasa osnovne škole trenutno se
prijavljuju kao upozorenja, jer su u pravilima označeni kao poželjne osobine.
Za posebnu smenu П1 proveravač privremeno tumači fond od šest časova kao
dvočas ponedeljkom, sredom i petkom u blokovima 13–14 i prikazuje upozorenje,
jer odgovor na to otvoreno pitanje još nije potvrđen.
