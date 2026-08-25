import csv

from src.vizualizacija import BLOK_VREMENA, napravi_html, ucitaj


def upisi_csv(putanja, zaglavlje, red):
    with putanja.open("w", encoding="utf-8", newline="") as datoteka:
        pisac = csv.writer(datoteka)
        pisac.writerow(zaglavlje)
        pisac.writerow(red)


def test_ucitava_cirilicni_csv_i_normalizuje_dan(tmp_path):
    csv_putanja = tmp_path / "nedelja.csv"
    upisi_csv(
        csv_putanja,
        ("дан", "блок", "предмет", "одељења", "наставник", "корепетитор", "просторија"),
        ("понедељак", "1", "Класичан балет", "11", "Мила", "Ива", "KM-1"),
    )

    casovi = ucitaj(csv_putanja, "A")

    assert casovi[0]["dan"] == "ponedeljak"
    assert casovi[0]["predmet"] == "Класичан балет"


def test_html_sadrzi_vremena_blokova(tmp_path):
    nedelja_a = tmp_path / "a.csv"
    nedelja_b = tmp_path / "b.csv"
    zaglavlje = (
        "dan", "blok", "predmet", "odeljenja",
        "nastavnik", "korepetitor", "prostorija",
    )
    red = ("ponedeljak", "1", "Balet", "11", "Mila", "", "KM-1")
    upisi_csv(nedelja_a, zaglavlje, red)
    upisi_csv(nedelja_b, zaglavlje, red)
    izlaz = tmp_path / "raspored.html"

    napravi_html(nedelja_a, nedelja_b, izlaz)

    html = izlaz.read_text(encoding="utf-8")
    assert BLOK_VREMENA[1] in html
    assert BLOK_VREMENA[14] in html
