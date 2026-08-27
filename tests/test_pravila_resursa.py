from pathlib import Path

from src.resavac import NP_SALA, _moguce_prostorije, ucitaj_standardne_ulaze


def _zahtev(ulaz, predmet, odeljenje):
    return next(z for z in ulaz.zahtevi if z.predmet == predmet and odeljenje in z.odeljenja)


def test_np_sala_samo_za_propisane_rkb_grupe():
    ulaz, prostorije, _ = ucitaj_standardne_ulaze(Path("ulazi"))
    iv1 = _zahtev(ulaz, "Репертоар класичног балета", "IV1")
    i1 = _zahtev(ulaz, "Репертоар класичног балета", "I1")
    assert NP_SALA in {p.oznaka for p in _moguce_prostorije(iv1, ulaz, prostorije)}
    assert NP_SALA not in {p.oznaka for p in _moguce_prostorije(i1, ulaz, prostorije)}
