from pathlib import Path

p = Path("src/proveravac.py")
t = p.read_text(encoding="utf-8")

stari_poziv = "    _proveri_aleksandra_boskovica(casovi, izvestaj)\n"
novi_poziv = "    _proveri_aleksandra_boskovica(casovi, izvestaj, ulaz)\n"
if stari_poziv not in t:
    raise SystemExit("Nije pronađen poziv provere Aleksandra")
t = t.replace(stari_poziv, novi_poziv, 1)

stari_potpis = '''def _proveri_aleksandra_boskovica(\n    casovi: Sequence[Cas],\n    izvestaj: Izvestaj,\n) -> None:\n    \"\"\"Aleksandar radi II razred: dva dana po tri uzastopna časa od 7. bloka.\"\"\"\n\n'''
novi_potpis = '''def _proveri_aleksandra_boskovica(\n    casovi: Sequence[Cas],\n    izvestaj: Izvestaj,\n    ulaz: Ulaz | None = None,\n) -> None:\n    \"\"\"Aleksandar radi II razred: dva dana po tri uzastopna časa od 7. bloka.\"\"\"\n\n    # U punoj proveri ovo pravilo važi samo ako je Aleksandar stvarno deo\n    # konkretnog ulaza. Direktni jedinični testovi mogu pozvati pomoćnu\n    # funkciju bez ulaza i tada se proveravaju prosleđeni Aleksandrovi časovi.\n    if ulaz is not None and not any(\n        zahtev.predmet == ISTORIJA and zahtev.nastavnik == ALEKSANDAR_BOSKOVIC\n        for zahtev in ulaz.zahtevi\n    ):\n        return\n\n'''
if stari_potpis not in t:
    raise SystemExit("Nije pronađen potpis funkcije provere Aleksandra")
t = t.replace(stari_potpis, novi_potpis, 1)

p.write_text(t, encoding="utf-8")
