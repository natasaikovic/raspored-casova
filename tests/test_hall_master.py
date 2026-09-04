from collections import defaultdict

from ortools.sat.python import cp_model

from src.model import TipProstorije
from src.resavac import (
    KNEZ_MILETINA,
    SPORTSKA_GIMNAZIJA,
    _dodaj_hall_ogranicenja,
    _intervali_hall_podskupa,
    _jedinice,
    _moguce_prostorije,
    ucitaj_standardne_ulaze,
)


def _fiksni_interval(model, ime):
    return model.new_fixed_size_interval_var(0, 1, ime)


def test_hall_pravi_podskup_sabira_sve_uze_skupove_kandidata():
    model = cp_model.CpModel()
    tip = TipProstorije.SALA
    intervali = {
        ("L", tip, frozenset({"A", "B"})): [_fiksni_interval(model, "ab")],
        ("L", tip, frozenset({"A"})): [_fiksni_interval(model, "a")],
        ("L", tip, frozenset({"B"})): [_fiksni_interval(model, "b")],
    }
    _dodaj_hall_ogranicenja(model, {("L", tip): 3}, intervali, {})

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    assert solver.solve(model) == cp_model.INFEASIBLE


def test_pomocni_obicni_interval_se_ne_broji_dvaput():
    tip = TipProstorije.SALA
    izvorni = frozenset({"A", "B"})
    intervali = {("L", tip, izvorni): ["izvorni"]}
    pomocni = {("L", tip, frozenset({"A"}), izvorni): ["obicni"]}

    assert _intervali_hall_podskupa(
        ("L", tip, izvorni), intervali, pomocni
    ) == ["izvorni"]
    assert _intervali_hall_podskupa(
        ("L", tip, frozenset({"A"})), intervali, pomocni
    ) == ["obicni"]


def test_stvarni_skupovi_kandidata_prate_inkluziju_fizickih_soba():
    ulaz, prostorije, _ = ucitaj_standardne_ulaze("ulazi")
    po_kljucu = defaultdict(list)
    for jedinica in _jedinice(ulaz):
        zahtev = ulaz.zahtevi[jedinica.zahtev_indeks]
        tip = (
            TipProstorije.SALA
            if ulaz.predmeti[zahtev.predmet].trazi_salu
            else TipProstorije.UCIONICA
        )
        for lokacija in (KNEZ_MILETINA, SPORTSKA_GIMNAZIJA):
            kandidati = frozenset(
                soba.oznaka
                for soba in _moguce_prostorije(
                    zahtev, ulaz, prostorije, jedinica.trajanje
                )
                if soba.lokacija == lokacija
            )
            if kandidati:
                po_kljucu[(lokacija, tip, kandidati)].append(
                    (jedinica.indeks, zahtev.predmet)
                )

    km_sale = {
        kljuc[2]: stavke
        for kljuc, stavke in po_kljucu.items()
        if kljuc[:2] == (KNEZ_MILETINA, TipProstorije.SALA)
    }
    obicne_sale = frozenset({"KM-1", "KM-2", "KM-3", "KM-4", "KM-5", "KM-6"})
    puni_skup_sala = obicne_sale | {"KM-8"}
    pomocni = {
        (KNEZ_MILETINA, TipProstorije.SALA, obicne_sale, puni_skup_sala):
            ["grana_bez_km8"]
    }
    intervali_sala = {
        (KNEZ_MILETINA, TipProstorije.SALA, kandidati): stavke
        for kandidati, stavke in km_sale.items()
    }
    ukljucene_sale = _intervali_hall_podskupa(
        (KNEZ_MILETINA, TipProstorije.SALA, obicne_sale),
        intervali_sala,
        pomocni,
    )
    for singleton in ({"KM-2"}, {"KM-4"}, {"KM-5"}):
        assert any(
            stavka in ukljucene_sale
            for stavka in km_sale[frozenset(singleton)]
        )
    assert "grana_bez_km8" in ukljucene_sale
    assert not any(stavka in ukljucene_sale for stavka in km_sale[puni_skup_sala])

    km_ucionice = {
        kljuc[2]: stavke
        for kljuc, stavke in po_kljucu.items()
        if kljuc[:2] == (KNEZ_MILETINA, TipProstorije.UCIONICA)
    }
    opste_cetiri = frozenset({"KM-уч1", "KM-уч2", "KM-уч3", "KM-уч7"})
    opste_pet = opste_cetiri | {"KM-библиотека"}
    intervali_ucionica = {
        (KNEZ_MILETINA, TipProstorije.UCIONICA, kandidati): stavke
        for kandidati, stavke in km_ucionice.items()
    }
    ukljucene_cetiri = _intervali_hall_podskupa(
        (KNEZ_MILETINA, TipProstorije.UCIONICA, opste_cetiri),
        intervali_ucionica,
        {},
    )
    ukljucene_pet = _intervali_hall_podskupa(
        (KNEZ_MILETINA, TipProstorije.UCIONICA, opste_pet),
        intervali_ucionica,
        {},
    )
    for singleton in ({"KM-уч1"}, {"KM-уч2"}):
        stavke = km_ucionice[frozenset(singleton)]
        assert any(stavka in ukljucene_cetiri for stavka in stavke)
        assert any(stavka in ukljucene_pet for stavka in stavke)
    videoteka = km_ucionice[frozenset({"KM-видеотека"})]
    assert not any(stavka in ukljucene_cetiri for stavka in videoteka)
    assert not any(stavka in ukljucene_pet for stavka in videoteka)

    sg_sale = {
        kljuc[2]: stavke
        for kljuc, stavke in po_kljucu.items()
        if kljuc[:2] == (SPORTSKA_GIMNAZIJA, TipProstorije.SALA)
    }
    sg_pun = frozenset({"SG-1", "SG-2", "SG-3"})
    ukljucene_sg = _intervali_hall_podskupa(
        (SPORTSKA_GIMNAZIJA, TipProstorije.SALA, sg_pun),
        {
            (SPORTSKA_GIMNAZIJA, TipProstorije.SALA, kandidati): stavke
            for kandidati, stavke in sg_sale.items()
        },
        {},
    )
    assert any(
        stavka in ukljucene_sg
        for stavka in sg_sale[frozenset({"SG-1"})]
    )
