# Uputstvo za AI agente

## O projektu

Raspored časova za baletsku školu — osnovnu i srednju. Krajnji korisnik je
školski administrator koji nije programer.

Podaci i pravila ovog projekta namenjeni su objavljivanju u javnom GitHub
repozitorijumu. Školski administrator je potvrdio da su informacije koje se
unose u repozitorijum javno dostupne. Ovo ne ukida obavezu da se ne dodaju
lozinke, pristupni tokeni, privatni ključevi ili drugi tehnički poverljivi
podaci.

## Rad sa školskim administratorom i pull requestovima

Školski administrator ne treba da poznaje GitHub, grane, commitove ni pull
requestove. Agent samostalno obavlja ceo tehnički postupak i administratoru
jednostavnim jezikom pokazuje rezultat i traži samo odluke koje su zaista
potrebne.

Za svaku traženu izmenu agent treba da:

1. Napravi novu granu, uradi tražene izmene, pokrene odgovarajuće provere i
   **sam otvori pull request**. Više pull requestova sme biti otvoreno
   istovremeno, pod uslovom da se tiču različitih izmena i da im se grane ne
   preklapaju u istim delovima koda.
2. Po otvaranju pull requesta administratoru pošalje kratak sažetak promena,
   rezultate provera i, kada postoji, direktan link ili prikaz rezultata koji
   može da pregleda. Ne traži od administratora da koristi git ili GitHub.
3. Dok administrator traži dorade iste izmene, dodaje ih u isti otvoreni pull
   request; ne otvara dodatni za istu stvar.
4. Sam spaja pull request čim su ispunjeni uslovi iz odeljka „Uslovi za
   spajanje pull requesta", bez traženja posebnog odobrenja. Ako administrator
   kaže da izmene više nisu potrebne, zatvara pull request bez spajanja. Ako
   nije jasno da li rad treba prihvatiti ili odbaciti, ukratko objasni šta je
   ostalo otvoreno i pita administratora — ne nagađa i ne odbacuje izmene
   samovoljno.

### Odgovori na otvorena pitanja

Kada administrator odgovara na pitanja iz `docs/otvorena-pitanja.md`, agent ne
sme reći da je odgovor „zabeležen“ ako ga je samo zapamtio u razgovoru. Odgovor
je zabeležen tek kada su odgovarajući CSV, dokumentacija, kod ili testovi
izmenjeni i commitovani na grani otvorenog pull requesta.

- Svaki potvrđeni odgovor uneti kao **zaseban commit**.
- Jedan odgovor sme u istom commitu menjati više datoteka kada zajedno čine
  jednu domensku odluku.
- Posle svakog odgovora odmah commitovati odgovarajuće izmene, umesto da se
  odgovori skupljaju samo u razgovoru.
- Rešeno pitanje obrisati iz `docs/otvorena-pitanja.md`, potvrđeni podatak uneti
  na predviđeno mesto, a svaku novu nedoumicu nastalu iz odgovora dodati kao
  novo otvoreno pitanje.

## Ulazni podaci

- Ulaz su CSV fajlovi u `ulazi/`, sa ćiriličnim zaglavljima.
- Jedan red = jedan predmet za jedno ili više odeljenja, sa nedeljnim fondom.
- NE uvoditi YAML, JSON ni Excel kao ulazni format. CSV je izabran namerno:
  administrator ga menja preko AI asistenta, a git prikazuje čitljiv diff.
- Fajlove menja asistent, pa validacija mora ostati stroga.
- Čitati sa `utf-8-sig` — BOM se često pojavi.
- **Posle svake izmene ulaznih podataka obavezno pokrenuti rešavač.** Izmena
  ulaza nije završena samo zato što CSV prolazi validaciju ili testove: agent
  treba da proveri da solver i sa novim podacima može da napravi raspored i da
  administratoru prikaže novi rezultat ili jasno prijavi ako rešavanje ne uspe.

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
- Ako commit napravi GitHub Actions bot, novi PR workflow-i mogu biti označeni
  kao `action_required` umesto da se automatski izvrše. Posle takvog bota
  napraviti sledeći potreban commit preko normalnog GitHub pristupa ili
  eksplicitno pokrenuti proveru; ne tumačiti `action_required` kao neuspeh
  solvera ili testova.

## Workflow „Generisi raspored"

Ovaj workflow rešava obe nedelje i traje oko 30 minuta. Rezultat je artifact
`raspored-2026-27` sa `solver.log` i CSV fajlovima.

- Agent NIKADA ne pretpostavlja da run još traje. Posle 40 minuta stanje se
  proverava komandom:

  `gh run list -R natasaikovic/raspored-casova -L 5`

  `gh run download <ID> -R natasaikovic/raspored-casova -D <folder>`

- U `solver.log` se gledaju četiri stvari: red `HINT:` (da li je topli start
  preuzet), `FAZA 1 — trajanje`, `FAZA 2 — trajanje`, i za obe nedelje
  „Raspored je ispravan" sa brojem upozorenja.

- Faza 1 ima gornju granicu od 1500 s pri ukupnom budžetu od 1800 s. Ako se
  faza 1 približi toj granici, faza 2 ostaje bez vremena za optimizaciju i broj
  upozorenja raste. To je znak da treba prvo rešiti raspodelu vremena, a ne
  dodavati nova pravila.

- Zabranjeno: `stop_after_first_solution`, i spuštanje
  `--vremensko-ogranicenje` ispod 1800 na grani `main`.

- Jedan push po izmeni. Više pushova u kratkom razmaku pokreće više paralelnih
  run-ova od po 30 minuta i troši CI bez koristi.

### Uslovi za spajanje pull requesta

Pull request sa izmenom pravila ili ulaznih podataka sme se spojiti tek kada:

1. svi testovi prolaze;
2. `solver.log` daje „Raspored je ispravan" za OBE nedelje;
3. broj upozorenja za obe nedelje je upisan u opis pull requesta — ne
   ostavljati „biće dopunjeno";
4. ako je zbir upozorenja porastao za više od 10 u odnosu na prethodni
   `main`, u opisu stoji objašnjenje odakle skok dolazi.

Agent sam spaja pull request čim su uslovi 1–4 ispunjeni i ne traži posebno
odobrenje. Pull request koji menja samo dokumentaciju ne pokreće solver, pa
za njega važe samo uslov 1 i zeleni testovi.


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
