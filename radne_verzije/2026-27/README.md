# Radna verzija rasporeda 2026/27

Ovaj direktorijum sadrzi radnu, jos uvek nevalidnu verziju rasporeda za dve
nedelje koje se smenjuju:

- `nedelja_a.csv` — crvena smena je jutarnja;
- `nedelja_b.csv` — plava smena je jutarnja.

Raspored od prosle godine iz `referenca/raspored_2025_26.csv` koriscen je kao
polazna osnova za dane, blokove i prostorije. Aktuelni zahtevi iz `ulazi/` imaju
prednost: fondovi, odeljenja, nastavnici i korepetitori preuzeti su iz njih.

Obe CSV datoteke imaju zaglavlja i vrednosti na latinici. Svaka sadrzi 866
rasporedjenih redova i pokriva sve aktuelne fondove. Proveravac nije prijavio
preklapanja nastavnika, korepetitora, prostorija ili odeljenja, termine van
smene, pogresne prostorije ni nedostajuce fondove.

## Rezultat provere

Radna verzija jos nije prosla celu proveru:

| Nedelja | Greske | Upozorenja |
| --- | ---: | ---: |
| A | 151 | 92 |
| B | 148 | 94 |

Preostale greske odnose se na dnevni kontinuitet ucenika: prazne blokove i
promene lokacije bez tacno jednog slobodnog bloka, kao i previse promena
lokacije u istom danu. Upozorenja se uglavnom odnose na pauze nastavnika i
privremenu pretpostavku za odeljenje P1.

Provera se ponavlja komandama:

```bash
python -m src.proveravac radne_verzije/2026-27/nedelja_a.csv --jutarnja-smena crvena
python -m src.proveravac radne_verzije/2026-27/nedelja_b.csv --jutarnja-smena plava
```

Ovo je polazna tacka za dalju optimizaciju, a ne raspored spreman za objavu.
