# Uputstvo za AI agente

## O projektu

Raspored časova za baletsku školu — osnovnu i srednju. Krajnji korisnik je
školski administrator koji nije programer.

## Rad sa školskim administratorom i pull requestovima

Školski administrator ne treba da poznaje GitHub, grane, commitove ni pull
requestove. Agent samostalno obavlja ceo tehnički postupak i administratoru
jednostavnim jezikom pokazuje rezultat i traži samo odluke koje su zaista
potrebne.

Za svaku traženu izmenu agent treba da:

1. **Pre početka rada proveri da li već postoji otvoren pull request.**
2. U repozitorijumu održava **najviše jedan otvoren pull request u svakom
   trenutku**.
3. Ako pull request već postoji, ne otvara novi i ne započinje odvojenu granu
   dok prethodni nije razrešen:
   - ako administrator kaže da je zadovoljan izmenama, agent sam spaja
     (mergeuje) postojeći pull request;
   - ako administrator kaže da izmene više nisu potrebne ili da treba odustati,
     agent zatvara postojeći pull request bez spajanja;
   - ako nije jasno da li postojeći rad treba prihvatiti ili odbaciti, agent
     ukratko objasni šta je ostalo otvoreno i pita administratora da izabere
     između završavanja i odustajanja. Ne nagađa i ne odbacuje izmene
     samovoljno.
4. Kada nema otvorenog pull requesta, napravi novu granu, uradi tražene izmene,
   pokrene odgovarajuće provere i **sam otvori pull request**.
5. Po otvaranju pull requesta administratoru pošalje kratak sažetak promena,
   rezultate provera i, kada postoji, direktan link ili prikaz rezultata koji
   može da pregleda. Ne traži od administratora da koristi git ili GitHub.
6. Dok administrator traži dorade iste izmene, agent ih dodaje u isti otvoreni
   pull request; ne otvara dodatni.
7. **Ne spaja pull request pre odobrenja administratora.** Kada administrator
   jasno kaže da je zadovoljan, da je dobro ili zatraži spajanje, agent
   samostalno mergeuje pull request i potvrđuje da je posao završen.

## Ulazni podaci

- Ulaz su CSV fajlovi u `ulazi/`, sa ćiriličnim zaglavljima.
- Jedan red = jedan predmet za jedno ili više odeljenja, sa nedeljnim fondom.
- NE uvoditi YAML, JSON ni Excel kao ulazni format. CSV je izabran namerno:
  administrator ga menja preko AI asistenta, a git prikazuje čitljiv diff.
- Fajlove menja asistent, pa validacija mora ostati stroga.
- Čitati sa `utf-8-sig` — BOM se često pojavi.

## Konvencije u kodu

- Struktura koda je engleska, domenske imenice ostaju srpske: `Smena`,
  `Odeljenje`, `Zahtev`, `Predmet`, `fond`, `korepetitor`. Ne prevoditi ih —
  tako se tipovi poklapaju sa kolonama u CSV-u i sa pravilima.
- Poruke o greškama pišu se ćirilicom, jer ih čita administrator.
- Validacija skuplja SVE greške u jednom prolazu i tek onda podiže izuzetak.
  Nikada ne prekidati na prvoj grešci — korisnik ispravlja fajl iz jednog pokušaja.

## Domenske odluke (ne menjati bez dogovora)

- Jedinica rasporeda je ODELJENJE, ne pojedinačni učenik. Polugrupe (`I5А`,
  `I5Б`) su polovine celog odeljenja (`I5`) — ista deca, pa se polugrupa i celo
  odeljenje ne smeju preklapati u vremenu.
- Obe škole su JEDNA ustanova: dele nastavnike, korepetitore i prostorije, pa
  se sva tri ulazna fajla učitavaju zajedno (`ucitaj_vise`) i rešavaju kao
  jedan problem. Norma je 20 časova nedeljno, zbirno kroz obe škole.
- `Predmet.igracki` se IZVODI iz toga da li predmet ima korepetitora; ne
  konfiguriše se ručno. `trazi_salu` je posebno polje: igrački predmeti traže
  salu, ali i Репертоар савремене игре i Игре XX века (bez korepetitora —
  spisak `SALA_BEZ_KOREPETITORA` u loaderu). Ostali predmeti traže učionicu.
- Smena je ULAZNI PODATAK, ne odluka solvera. Srednja škola nema smene —
  `цео дан` — i sme da koristi bilo koji blok.
- Subota je nastavni dan. Nedeljni raspored ima 6 dana. Bez subote instanca
  nije rešiva: šest nastavnika ima tačno 20 časova, a jutarnja smena ima 4
  bloka × 5 dana = 20, dakle nula rezerve.
- Crvena i plava smena se smenjuju nedeljno i raspoređuju se simetrično
  (mirror), pa se rešava jedna nedelja.
- Odeljenja 13, 23 i 33 su uvek popodne.
- Pre menjanja logike rasporeda pročitati `docs/pravila-rasporeda.md`.

## Testovi

- `python -m pytest`
- Testovi za loader koriste samo standardnu biblioteku i moraju tako i ostati.
- `ortools` je potreban samo za solver, kada bude napisan.


## Prikaz rasporeda korisniku

Workflow `.github/workflows/vizualizacija.yml` pravi artifact
`raspored-html`, koji sadrži samostalni fajl `raspored.html`. Kada korisnik
traži da vidi raspored, agent treba da:

1. pronađe poslednji uspešan workflow run **Vizuelizacija rasporeda** za tačan
   commit ili PR koji se trenutno pregleda (ne koristiti artifact starijeg
   commita);
2. pronađe i preuzme artifact `raspored-html`;
3. raspakuje ZIP u radni direktorijum;
4. priloži raspakovani `raspored.html` direktno u ChatGPT razgovoru kao
   klikabilan lokalni fajl, na primer:
   `[Otvori vizuelizaciju](sandbox:/apsolutna/putanja/raspored.html)`;
5. po potrebi doda i link ka GitHub workflow run-u radi provere porekla.

Nemoj korisniku proslediti samo GitHub API adresu artifacta: ona obično traži
GitHub prijavu i preuzima ZIP umesto da otvori HTML. Raspakovan HTML omogućava
da se interaktivni pregled otvori direktno iz razgovora. Artifact se čuva 30
dana; ako je istekao, ponovo pokrenuti workflow. Generisani HTML se ne commituje
u repozitorijum — CSV ostaje izvor istine.
