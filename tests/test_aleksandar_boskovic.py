import csv
from pathlib import Path

from src.proveravac import ALEKSANDAR_BOSKOVIC, Cas, Izvestaj, _proveri_aleksandra_boskovica


def _cas(dan, blok, odeljenja, red):
    return Cas(dan, blok, "Историја", odeljenja, ALEKSANDAR_BOSKOVIC, None, "KM-уч2", red)


def test_ulaz_dodeljuje_aleksandru_sve_tri_grupe_drugog_razreda():
    with Path("ulazi/ostali_casovi.csv").open(encoding="utf-8", newline="") as f:
        redovi = list(csv.DictReader(f))
    istorija = [r for r in redovi if r["предмет"] == "Историја" and r["наставник"] == ALEKSANDAR_BOSKOVIC]
    assert len(istorija) == 3
    assert {r["разред"] for r in istorija} == {"II"}
    assert sum(int(r["недељни фонд часова"]) for r in istorija) == 6
    assert {r["одељење"] for r in istorija} == {"II1,II3", "II2,II4", "II5"}


def test_aleksandar_je_nedostupan_pre_sedmog_bloka_radnim_danima():
    with Path("ulazi/nedostupnost.csv").open(encoding="utf-8", newline="") as f:
        redovi = [r for r in csv.DictReader(f) if r["наставник"] == ALEKSANDAR_BOSKOVIC]
    assert len(redovi) == 5
    assert {r["дан"] for r in redovi} == {"понедељак", "уторак", "среда", "четвртак", "петак"}
    assert all(r["од блока"] == "1" and r["до блока"] == "6" for r in redovi)


def test_proveravac_prihvata_dva_dana_po_tri_uzastopna_casa():
    casovi = []
    red = 2
    for dan in ("понедељак", "четвртак"):
        for blok, grupa in zip((7, 8, 9), (("II1", "II3"), ("II2", "II4"), ("II5",))):
            casovi.append(_cas(dan, blok, grupa, red))
            red += 1
    izvestaj = Izvestaj()
    _proveri_aleksandra_boskovica(casovi, izvestaj)
    assert izvestaj.greske == []


def test_proveravac_odbija_rupu_u_aleksandrovom_trocasu():
    casovi = [
        _cas("понедељак", 7, ("II1", "II3"), 2),
        _cas("понедељак", 8, ("II2", "II4"), 3),
        _cas("понедељак", 10, ("II5",), 4),
        _cas("четвртак", 7, ("II1", "II3"), 5),
        _cas("четвртак", 8, ("II2", "II4"), 6),
        _cas("четвртак", 9, ("II5",), 7),
    ]
    izvestaj = Izvestaj()
    _proveri_aleksandra_boskovica(casovi, izvestaj)
    assert any("3 uzastopna" in greska for greska in izvestaj.greske)
