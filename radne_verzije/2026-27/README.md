# Radna verzija rasporeda 2026/27

Ovaj direktorijum sadrzi validiranu radnu verziju rasporeda za dve
nedelje koje se smenjuju:

- `nedelja_a.csv` — crvena smena je jutarnja;
- `nedelja_b.csv` — plava smena je jutarnja.

Raspored od prosle godine iz `referenca/raspored_2025_26.csv` koriscen je kao
polazna osnova za dane, blokove i prostorije. Aktuelni zahtevi iz `ulazi/` imaju
prednost: fondovi, odeljenja, nastavnici i korepetitori preuzeti su iz njih.

Obe CSV datoteke imaju zaglavlja i vrednosti na latinici. Svaka sadrzi 863
rasporedjena casa i pokriva sve aktuelne fondove. Proveravac nije prijavio
preklapanja nastavnika, korepetitora, prostorija ili odeljenja, termine van
smene, pogresne prostorije, nedostajuce fondove ni prazne blokove u rasporedu
ucenika.

## Rezultat provere

Radna verzija prolazi celu proveru:

| Nedelja | Greske | Upozorenja |
| --- | ---: | ---: |
| A | 0 | 285 |
| B | 0 | 286 |

Upozorenja su preporuke za dalju optimizaciju: uglavnom pauze nastavnika,
optimalni dnevni maksimum od cetiri casa i prioriteti sala. Ne predstavljaju
krsenje cvrstih pravila.

Provera se ponavlja komandama:

```bash
python -m src.proveravac radne_verzije/2026-27/nedelja_a.csv --jutarnja-smena crvena
python -m src.proveravac radne_verzije/2026-27/nedelja_b.csv --jutarnja-smena plava
```

Ovo je upotrebljiva, validirana polazna verzija za dalju optimizaciju.
