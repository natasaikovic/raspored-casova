from pathlib import Path

from src.resavac import (
    NARODNO_POZORISTE,
    _moguce_prostorije,
    ucitaj_standardne_ulaze,
)


def _zahtev(ulaz, predmet, odeljenje):
    return next(z for z in ulaz.zahtevi if z.predmet == predmet and odeljenje in z.odeljenja)


def test_np_sale_samo_za_propisane_rkb_grupe():
    ulaz, prostorije, _ = ucitaj_standardne_ulaze(Path("ulazi"))
    np_sale = {p.oznaka for p in prostorije if p.lokacija == NARODNO_POZORISTE}
    assert np_sale == {"NP-1", "NP-2"}
    iv1 = {p.oznaka for p in _moguce_prostorije(_zahtev(ulaz, "Репертоар класичног балета", "IV1"), ulaz, prostorije)}
    i1 = {p.oznaka for p in _moguce_prostorije(_zahtev(ulaz, "Репертоар класичног балета", "I1"), ulaz, prostorije)}
    assert np_sale <= iv1
    assert not (np_sale & i1)
