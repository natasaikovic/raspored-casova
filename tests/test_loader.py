import pytest

from src.loader import (
    UlazGreska,
    ucitaj,
    ucitaj_nedostupnost,
    ucitaj_prostorije,
    ucitaj_vise,
)
from src.model import Skola, Smena, kapacitet_smene

OBS = "ulazi/osnovna_baletska_skola.csv"
SVI_ULAZI = (
    OBS,
    "ulazi/srednja_baletska_skola.csv",
    "ulazi/ostali_casovi.csv",
)

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
        assert ulaz.ukupno_casova == 216
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
        assert ulaz.opterecenje_korepetitora()["Ђорђина Убовић"] == 14
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

        with pytest.raises(UlazGreska, match="већ постоји"):
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


class TestCelaInstitucija:
    """Both schools are one institution and load as one problem."""

    def test_ucitava_sva_tri_ulaza_zajedno(self):
        ulaz = ucitaj_vise(SVI_ULAZI)

        assert ulaz.skola is None
        assert len(ulaz.zahtevi) == 244
        assert ulaz.ukupno_casova == 864
        assert len(ulaz.odeljenja) == 45

    def test_srednja_radi_ceo_dan(self):
        ulaz = ucitaj_vise(SVI_ULAZI)

        assert ulaz.odeljenja["I1"].smena is Smena.CEO_DAN
        assert kapacitet_smene(Smena.CEO_DAN, broj_dana=6) == 84

    def test_polugrupe_pokazuju_na_celo_odeljenje(self):
        odeljenja = ucitaj_vise(SVI_ULAZI).odeljenja

        assert odeljenja["I5А"].roditelj == "I5"
        assert odeljenja["IV5Б"].roditelj == "IV5"
        assert odeljenja["I5"].roditelj is None
        assert odeljenja["11"].roditelj is None

    def test_sala_se_ne_izvodi_samo_iz_korepetitora(self):
        """Репертоар савремене игре needs a sala although nobody plays on it."""
        predmeti = ucitaj_vise(SVI_ULAZI).predmeti

        rsi = predmeti["Репертоар савремене игре"]
        assert rsi.trazi_salu and not rsi.igracki
        srp = predmeti["Српски језик и књижевност"]
        assert not srp.trazi_salu and not srp.igracki

    def test_opterecenje_se_sabira_kroz_obe_skole(self):
        ulaz = ucitaj_vise(SVI_ULAZI)

        # Ђорђина Убовић свира 14 часова у основној и предаје Солфеђо у средњој.
        assert ulaz.opterecenje_korepetitora()["Ђорђина Убовић"] == 14
        assert ulaz.opterecenje_nastavnika()["Ђорђина Убовић"] == 6
        # Лана Јеленковић reaches the 20h norm only across the two schools.
        assert ulaz.opterecenje_korepetitora()["Лана Јеленковић"] == 20
        assert ulaz.opterecenje_nastavnika()["Ива Илиевска"] == 20
        assert "Ива Илевска" not in ulaz.nastavnici

    def test_greske_nose_ime_datoteke(self, tmp_path):
        prva = napravi(tmp_path, "Класичан балет,први,11,10,10,Ана,Маја,црвена смена")
        druga = tmp_path / "drugi.csv"
        druga.write_text(
            ZAGLAVLJE + "Класичан балет,први,11,10,10,Ана,Маја,плава смена\n",
            encoding="utf-8",
        )

        with pytest.raises(UlazGreska) as greska:
            ucitaj_vise([prva, druga])

        poruka = str(greska.value)
        assert "drugi.csv, ред 2" in poruka
        assert "одељење 11 је у смени" in poruka


class TestProstorije:
    def test_ucitava_stvarni_spisak(self):
        prostorije = ucitaj_prostorije("ulazi/prostorije.csv")

        assert len(prostorije) == 18
        po_oznaci = {p.oznaka: p for p in prostorije}
        assert po_oznaci["KM-1"].tip.value == "сала"
        assert po_oznaci["KM-уч1"].tip.value == "учионица"
        assert po_oznaci["NP-сала"].lokacija == "Народно позориште"

    def test_odbija_nepoznat_tip_i_duplikat(self, tmp_path):
        putanja = tmp_path / "prostorije.csv"
        putanja.write_text(
            "ознака,локација,тип,приоритет,напомена\n"
            "KM-1,Кнез Милетина 8,сала,1,\n"
            "KM-1,Кнез Милетина 8,шупа,,\n",
            encoding="utf-8",
        )

        with pytest.raises(UlazGreska) as greska:
            ucitaj_prostorije(putanja)

        assert len(greska.value.greske) == 2
        assert "непознат тип „шупа“" in str(greska.value)
        assert "већ постоји" in str(greska.value)


class TestNedostupnost:
    def test_prazna_datoteka_znaci_svi_dostupni(self, tmp_path):
        putanja = tmp_path / "nedostupnost.csv"
        putanja.write_text(
            "наставник,дан,од блока,до блока,напомена\n",
            encoding="utf-8",
        )

        assert ucitaj_nedostupnost(putanja) == ()

    def test_ucitava_opseg_blokova(self, tmp_path):
        putanja = tmp_path / "nedostupnost.csv"
        putanja.write_text(
            "наставник,дан,од блока,до блока,напомена\n"
            "Ана,петак,1,14,ради у другој школи\n",
            encoding="utf-8",
        )

        (stavka,) = ucitaj_nedostupnost(putanja)

        assert stavka.nastavnik == "Ана"
        assert (stavka.od_bloka, stavka.do_bloka) == (1, 14)

    def test_odbija_los_dan_i_opseg(self, tmp_path):
        putanja = tmp_path / "nedostupnost.csv"
        putanja.write_text(
            "наставник,дан,од блока,до блока,напомена\n"
            "Ана,недеља,9,3,\n",
            encoding="utf-8",
        )

        with pytest.raises(UlazGreska) as greska:
            ucitaj_nedostupnost(putanja)

        assert "непознат дан „недеља“" in str(greska.value)
        assert "нису растући опсег" in str(greska.value)
