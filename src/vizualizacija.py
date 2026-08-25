"""Napravi samostalni HTML pregled dve CSV nedelje rasporeda."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Sequence


OBAVEZNE_KOLONE = (
    "dan",
    "blok",
    "predmet",
    "odeljenja",
    "nastavnik",
    "korepetitor",
    "prostorija",
)


def ucitaj(putanja: Path, nedelja: str) -> list[dict[str, object]]:
    with putanja.open(encoding="utf-8-sig", newline="") as datoteka:
        citac = csv.DictReader(datoteka)
        nedostaju = [kolona for kolona in OBAVEZNE_KOLONE if kolona not in (citac.fieldnames or ())]
        if nedostaju:
            raise ValueError(
                f"{putanja}: nedostaju kolone: {', '.join(nedostaju)}"
            )

        rezultat: list[dict[str, object]] = []
        for broj_reda, red in enumerate(citac, start=2):
            try:
                blok = int(red["blok"])
            except (TypeError, ValueError) as greska:
                raise ValueError(
                    f"{putanja}:{broj_reda}: blok mora biti ceo broj"
                ) from greska
            rezultat.append(
                {
                    "nedelja": nedelja,
                    "dan": red["dan"].strip(),
                    "blok": blok,
                    "predmet": red["predmet"].strip(),
                    "odeljenja": [
                        deo.strip()
                        for deo in red["odeljenja"].split(";")
                        if deo.strip()
                    ],
                    "nastavnik": red["nastavnik"].strip(),
                    "korepetitor": red["korepetitor"].strip(),
                    "prostorija": red["prostorija"].strip(),
                }
            )
    return rezultat


SABLON = """<!doctype html>
<html lang="sr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pregled rasporeda</title>
<style>
:root { color-scheme: light; font-family: system-ui, sans-serif; }
body { margin: 0; background: #f5f7fb; color: #172033; }
header { padding: 20px 24px; background: #263a63; color: white; }
header h1 { margin: 0 0 4px; font-size: 24px; }
header p { margin: 0; opacity: .8; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; padding: 16px 24px; background: white; box-shadow: 0 2px 8px #0001; position: sticky; top: 0; z-index: 2; }
label { display: grid; gap: 4px; font-size: 13px; font-weight: 650; }
select { min-width: 180px; padding: 8px; border: 1px solid #cbd3e1; border-radius: 6px; background: white; }
main { padding: 20px 24px 40px; overflow-x: auto; }
.meta { margin: 0 0 12px; color: #526079; }
table { border-collapse: separate; border-spacing: 0; width: 100%; min-width: 1000px; background: white; box-shadow: 0 2px 12px #0001; }
th, td { border-right: 1px solid #dfe4ed; border-bottom: 1px solid #dfe4ed; padding: 7px; vertical-align: top; }
th { background: #e8edf7; text-align: left; }
th:first-child, td:first-child { width: 62px; text-align: center; font-weight: 700; background: #f1f4f9; }
.lesson { padding: 7px; margin: 0 0 5px; border-left: 4px solid #5377b8; border-radius: 4px; background: #eef3fc; font-size: 12px; line-height: 1.35; }
.lesson:last-child { margin-bottom: 0; }
.lesson strong { display: block; font-size: 13px; }
.empty { color: #a3abba; text-align: center; }
@media print {
  .controls { position: static; box-shadow: none; }
  main { padding: 8px; }
  th { position: static; }
}
</style>
</head>
<body>
<header>
  <h1>Raspored časova 2026/27</h1>
  <p>Radni pregled generisan iz CSV datoteka</p>
</header>
<section class="controls">
  <label>Nedelja<select id="week"><option>A</option><option>B</option></select></label>
  <label>Prikaz po<select id="kind">
    <option value="odeljenja">odeljenju</option>
    <option value="nastavnik">nastavniku</option>
    <option value="korepetitor">korepetitoru</option>
    <option value="prostorija">prostoriji</option>
  </select></label>
  <label>Izbor<select id="entity"></select></label>
</section>
<main>
  <p class="meta" id="meta"></p>
  <table>
    <thead><tr><th>Blok</th><th>Ponedeljak</th><th>Utorak</th><th>Sreda</th><th>Četvrtak</th><th>Petak</th><th>Subota</th></tr></thead>
    <tbody id="grid"></tbody>
  </table>
</main>
<script>
const lessons = __PODACI__;
const days = ["ponedeljak","utorak","sreda","četvrtak","petak","subota"];
const week = document.querySelector("#week");
const kind = document.querySelector("#kind");
const entity = document.querySelector("#entity");
const grid = document.querySelector("#grid");
const meta = document.querySelector("#meta");

function values() {
  const field = kind.value;
  const set = new Set();
  lessons.filter(x => x.nedelja === week.value).forEach(x => {
    if (field === "odeljenja") x.odeljenja.forEach(v => set.add(v));
    else if (x[field]) set.add(x[field]);
  });
  return [...set].sort((a,b) => a.localeCompare(b, "sr", {numeric:true}));
}
function matches(x, value) {
  return kind.value === "odeljenja" ? x.odeljenja.includes(value) : x[kind.value] === value;
}
function lessonCard(x) {
  const div = document.createElement("div");
  div.className = "lesson";
  const title = document.createElement("strong");
  title.textContent = x.predmet;
  div.append(title);
  const detail = kind.value === "odeljenja"
    ? [x.nastavnik, x.prostorija]
    : [x.odeljenja.join(", "), x.prostorija];
  div.append(document.createTextNode(detail.filter(Boolean).join(" · ")));
  if (x.korepetitor && kind.value !== "korepetitor") {
    div.append(document.createElement("br"), document.createTextNode("Korepetitor: " + x.korepetitor));
  }
  return div;
}
function fillEntities() {
  const previous = entity.value;
  entity.replaceChildren();
  values().forEach(value => {
    const option = document.createElement("option");
    option.value = option.textContent = value;
    entity.append(option);
  });
  if ([...entity.options].some(x => x.value === previous)) entity.value = previous;
  render();
}
function render() {
  grid.replaceChildren();
  const selected = entity.value;
  const chosen = lessons.filter(x => x.nedelja === week.value && matches(x, selected));
  meta.textContent = selected
    ? `Nedelja ${week.value} · ${selected} · ${chosen.length} časovnih blokova`
    : "Nema podataka za izabrani prikaz.";
  for (let block = 1; block <= 14; block++) {
    const tr = document.createElement("tr");
    const number = document.createElement("td");
    number.textContent = block;
    tr.append(number);
    days.forEach(day => {
      const td = document.createElement("td");
      const found = chosen.filter(x => x.dan === day && x.blok === block);
      if (!found.length) { td.className = "empty"; td.textContent = "—"; }
      else found.forEach(x => td.append(lessonCard(x)));
      tr.append(td);
    });
    grid.append(tr);
  }
}
week.addEventListener("change", fillEntities);
kind.addEventListener("change", fillEntities);
entity.addEventListener("change", render);
fillEntities();
</script>
</body>
</html>
"""


def napravi_html(nedelja_a: Path, nedelja_b: Path, izlaz: Path) -> None:
    podaci = ucitaj(nedelja_a, "A") + ucitaj(nedelja_b, "B")
    json_podaci = json.dumps(podaci, ensure_ascii=False).replace("</", "<\\/")
    izlaz.parent.mkdir(parents=True, exist_ok=True)
    izlaz.write_text(SABLON.replace("__PODACI__", json_podaci), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nedelja_a", type=Path)
    parser.add_argument("nedelja_b", type=Path)
    parser.add_argument("--izlaz", type=Path, default=Path("raspored.html"))
    argumenti = parser.parse_args(argv)
    napravi_html(argumenti.nedelja_a, argumenti.nedelja_b, argumenti.izlaz)
    print(f"Napravljen pregled: {argumenti.izlaz}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
