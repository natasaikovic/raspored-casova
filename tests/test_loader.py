import pytest

from src.loader import UlazGreska, ucitaj
from src.model import Skola, Smena, kapacitet_smene

OBS = "ulazi/osnovna_baletska_skola.csv"

ZAGLAVLJE = (
    "предмет,разред,одељење,недељни фонд часова,часови корепетиције,"
    "наставник,корепетитор,смена\n"
)


def napravi(tmp_path, *redovi):
    """Write a small input file made of the given rows."""
    putanja = tmp_path / "ulaz.csv"
    putanja.write_text(ZAGLAVLJE + "".join(red + "\n" for red in redovi),
                       encoding="utf-8")
    return putanja


class TestStvarniUlaz:
    def test_ucitava_osnovnu_baletsku_skolu(self):
        ulaz = ucitaj(OBS)

        assert ulaz.skola is Skola.OSNOVNA
        assert len(ulaz.zahtevi) == 50
        assert ulaz.ukupno_casova == 218
        assert len(ulaz.odeljenja) == 17

    def test_prepoznaje_smene(self):
        ulaz = ucitaj(OBS)

        assert ulaz.odeljenja_po_smeni(Smena.CRVENA) == (
            "11", "15", "21", "24", "31", "41",
        )
        assert ulaz.odeljenja_po_smeni(Smena.STALNO_POPODNE) == ("13", "23", "33")
        assert ulaz.odeljenja["П1"].smena is Smena.POSEBNA

    def test_deli_predmete_na_igracke_i_opste(self):
        predmeti = ucitaj(OBS).predmeti

        assert predmeti["Класичан балет"].igracki
        assert predmeti["Класичан балет"].trazi_salu
        assert not predmeti["Солфеђо"].igracki
        assert not predmeti["Солфеђо"].trazi_salu

    def test_racuna_opterecenje(self):
        ulaz = ucitaj(OBS)

        nastavnici = ulaz.opterecenje_nastavnika()
        assert next(iter(nastavnici.items())) == ("Бранислава Порчић", 22)
        assert nastavnici["Александра Ула Ускоковић"] == 20
        assert ulaz.opterecenje_korepetitora()["Ђорђина Убовић"] == 22
        assert ulaz.opterecenje_odeljenja()["41"] == 16

    def test_nastavnici_smenjujucih_odeljenja_popunjavaju_jutarnji_prozor(self):
        """The six 20h teachers have no slack in a five-day morning week."""
        ulaz = ucitaj(OBS)
        opterecenje = ulaz.opterecenje_nastavnika()
        smene = ulaz.smene_nastavnika()
        kapacitet_na_pet_dana = kapacitet_smene(Smena.CRVENA, broj_dana=5)

        puni = {
            ime
            for ime, sati in opterecenje.items()
            if sati == kapacitet_na_pet_dana
            and all(smena.menja_se for smena in smene[ime])
        }

        assert puni == {
            "Александра Ула Ускоковић",
            "Каролина Марјановић",
            "Милица Марковић",
            "Драгана Величковић (Мартиновски)",
            "Ивана Лалић",
            "Теа Миловановић",
        }
        # Субота is what creates the slack these six need.
        assert kapacitet_smene(Smena.CRVENA, broj_dana=6) == 24


class TestValidacija:
    def test_prijavljuje_sve_greske_odjednom(self, tmp_path):
        putanja = napravi(
            tmp_path,
            "Класичан балет,први,11,не,10,Ана,Маја,црвена смена",
            "Класичан балет,први,12,10,10,,Маја,розе смена",
        )

        with pytest.raises(UlazGreska) as greska:
            ucitaj(putanja)

        assert len(greska.value.greske) == 3
        poruka = str(greska.value)
        assert "мора бити цео број" in poruka
        assert "непозната смена" in poruka
        assert "„наставник“ не сме бити празно" in poruka

    def test_odbija_nedostajucu_kolonu(self, tmp_path):
        putanja = tmp_path / "ulaz.csv"
        putanja.write_text("предмет,разред\nКласичан балет,први\n", encoding="utf-8")

        with pytest.raises(UlazGreska, match="недостаје колона"):
            ucitaj(putanja)

    def test_odbija_odeljenje_u_dve_smene(self, tmp_path):
        putanja = napravi(
            tmp_path,
            "Класичан балет,први,11,10,10,Ана,Маја,црвена смена",
            "Солфеђо,први,11,1,,Ана,,плава смена",
        )

        with pytest.raises(UlazGreska, match="одељење 11 је у смени"):
            ucitaj(putanja)

    def test_odbija_predmet_koji_meša_igracki_i_opsti(self, tmp_path):
        putanja = napravi(
            tmp_path,
            "Солфеђо,први,11,1,1,Ана,Маја,црвена смена",
            "Солфеђо,први,12,1,,Ана,,плава смена",
        )

        with pytest.raises(UlazGreska, match="негде има корепетитора"):
            ucitaj(putanja)

    def test_odbija_dupli_predmet_za_isto_odeljenje(self, tmp_path):
        putanja = napravi(
            tmp_path,
            "Класичан балет,први,11,10,10,Ана,Маја,црвена смена",
            "Класичан балет,први,11,4,4,Ана,Маја,црвена смена",
        )

        with pytest.raises(UlazGreska, match="већ постоји у реду"):
            ucitaj(putanja)

    def test_odbija_korepeticiju_bez_korepetitora(self, tmp_path):
        putanja = napravi(
            tmp_path,
            "Класичан балет,први,11,10,10,Ана,,црвена смена",
        )

        with pytest.raises(UlazGreska, match="корепетитор није наведен"):
            ucitaj(putanja)

    def test_podnosi_bom_na_pocetku(self, tmp_path):
        putanja = tmp_path / "ulaz.csv"
        putanja.write_text(
            ZAGLAVLJE + "Класичан балет,први,11,10,10,Ана,Маја,црвена смена\n",
            encoding="utf-8-sig",
        )

        assert len(ucitaj(putanja).zahtevi) == 1


class TestZajednickiCasovi:
    def test_jedan_red_moze_da_pokrije_vise_odeljenja(self, tmp_path):
        putanja = napravi(
            tmp_path,
            '"Српски језик",I,"I1,I2,I3",3,,Ана,,црвена смена',
        )

        ulaz = ucitaj(putanja)
        zahtev = ulaz.zahtevi[0]

        assert zahtev.odeljenja == ("I1", "I2", "I3")
        assert zahtev.zajednicki
        assert ulaz.skola is Skola.SREDNJA
        assert ulaz.opterecenje_odeljenja() == {"I1": 3, "I2": 3, "I3": 3}
