from dataclasses import replace

import pytest
from ortools.sat.python import cp_model

from src.blokovi import OBAVEZNI_DVOCASI, SRPSKI, sukobi_fonda
from src.loader import UlazGreska
from src.model import DANI, Odeljenje, Predmet, Skola, Smena
from src.proveravac import Cas, Izvestaj, _proveri_stroge_blokove, proveri
from src.resavac import _jedinice, napravi_model, resi_obe_nedelje, ucitaj_standardne_ulaze
from tests.test_resavac import zahtev, ulaz, SALA, UCIONICA


def casovi(z, termini):
    return tuple(Cas(DANI[d], b, z.predmet, z.odeljenja, z.nastavnik,
                     z.korepetitor, SALA.oznaka if z.korepetitor else UCIONICA.oznaka, i+2)
                 for i, (d, b) in enumerate(termini))


def provera(z, termini, igracki=False):
    u = ulaz([z])
    if igracki:
        u = replace(u, predmeti={z.predmet: Predmet(z.predmet, False, True)})
    izv = Izvestaj()
    _proveri_stroge_blokove(u, casovi(z, termini), izv)
    return izv


@pytest.mark.parametrize('fond', [2, 4, 6, 8, 10])
@pytest.mark.parametrize('skola', [Skola.OSNOVNA, Skola.SREDNJA])
def test_parni_igracki_fond_iskljucivo_dvocasi(fond, skola):
    z = zahtev('Игре XX века', '11', fond, 'Ана')
    u = ulaz([z])
    u = replace(u, predmeti={z.predmet: Predmet(z.predmet, False, True)},
                odeljenja={'11': Odeljenje('11', 'први', Smena.CRVENA, skola)})
    assert [j.trajanje for j in _jedinice(u)] == [2] * (fond // 2)
    razbijeni = [(d, b) for d in range(fond // 2 - 1) for b in (1, 2)]
    razbijeni += [(fond // 2 - 1, 1), (fond // 2, 1)]
    assert provera(z, razbijeni, True).greske
    assert not provera(z, [(d, b) for d in range(fond // 2) for b in (1, 2)], True).greske


@pytest.mark.parametrize('predmet', sorted(OBAVEZNI_DVOCASI))
def test_obavezni_dvocas_odbija_dva_dana(predmet):
    z = zahtev(predmet, '11', 2, 'Ана')
    assert [j.trajanje for j in _jedinice(ulaz([z]))] == [2]
    assert provera(z, [(0, 1), (1, 1)]).greske
    assert not provera(z, [(0, 1), (0, 2)]).greske


@pytest.mark.parametrize('termini', [[(0, 1), (1, 1), (2, 1)], [(0, 1), (0, 2), (0, 3)]])
def test_srpski_odbija_singles_i_trocas(termini):
    z = zahtev(SRPSKI, '11', 3, 'Ана')
    assert provera(z, termini).greske
    assert not provera(z, [(0, 1), (0, 2), (1, 1)]).greske


@pytest.mark.parametrize('drugi_predmet', [False, True])
def test_svi_predmeti_ne_smeju_biti_razdvojeni(drugi_predmet):
    z = zahtev('Теорија', '11', 2, 'Ана')
    zz = zahtev('Други предмет', '11', 1, 'Мила')
    u = ulaz([z, zz] if drugi_predmet else [z])
    c = casovi(z, [(0, 1), (0, 3)])
    if drugi_predmet:
        c += casovi(zz, [(0, 2)])
    assert any('непрекинут' in e for e in proveri(u, (UCIONICA,), (), c).greske)


@pytest.mark.parametrize('polje,vrednost', [('nastavnik', 'Други'), ('korepetitor', 'Други'), ('prostorija', 'KM-2'), ('odeljenja', ('11', '12'))])
def test_dvocas_mora_imati_isto_osoblje_grupu_i_sobu(polje, vrednost):
    z = zahtev('Класичан балет', '11', 2, 'Ана', 'Ива')
    a, b = casovi(z, [(0, 1), (0, 2)])
    izv = Izvestaj()
    _proveri_stroge_blokove(ulaz([z]), (a, replace(b, **{polje: vrednost})), izv)
    assert any('неисправан двочас' in e for e in izv.greske)


@pytest.mark.parametrize('b', [False, True])
@pytest.mark.parametrize('p,fond,blokovi', [('Теорија', 2, [1, 3]), (SRPSKI, 3, [1, 3])])
def test_model_strogo_odbija_razdvajanje_i_srpski_isti_dan(b, p, fond, blokovi):
    z = zahtev(p, '11', fond, 'Ана')
    m, js, vs = napravi_model(ulaz([z]), (UCIONICA,), (), Smena.CRVENA, sa_nedeljom_b=True, sa_ciljem=False)
    for j, blok in zip(js, blokovi):
        v = vs[j.indeks]
        m.add((v.dan_b if b else v.dan) == 0)
        m.add((v.blok_b if b else v.blok) == blok + (8 if b else 0))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    assert solver.solve(m) == cp_model.INFEASIBLE


def test_neparni_fondovi_se_prijavljuju_zbirno_i_hint_ne_zaobilazi():
    u, sobe, n = ucitaj_standardne_ulaze('ulazi')
    greske = sukobi_fonda(u)
    assert len(greske) == 13
    assert all('ред' in e and 'фонд' in e for e in greske)
    with pytest.raises(UlazGreska) as exc:
        napravi_model(u, sobe, n, Smena.CRVENA)
    assert len(exc.value.greske) == 13
    a, b = resi_obe_nedelje(u, sobe, n, hintovi=casovi(u.zahtevi[0], [(0, 1)]))
    for r in (a, b):
        assert r.status == 'НЕУСАГЛАШЕН УЛАЗ'
        assert not r.pronadjen
        assert len(r.izvestaj.greske) == 13


def test_spojena_odeljenja_i_polugrupa_kontinuitet():
    z = replace(zahtev('Теорија', 'I5', 2, 'Ана'), odeljenja=('I5', 'I4'))
    zz = zahtev('Теорија', 'I5А', 1, 'Мила')
    u = ulaz([z, zz])
    u = replace(u, odeljenja={**u.odeljenja, 'I5А': replace(u.odeljenja['I5А'], roditelj='I5')})
    c = casovi(z, [(0, 1), (0, 2)]) + casovi(zz, [(0, 4)])
    izv = Izvestaj()
    _proveri_stroge_blokove(u, c, izv)
    assert any('I5А' in e and 'непрекинут' in e for e in izv.greske)

@pytest.mark.parametrize('p,fond,igracki', [('Солфеђо', 2, False), (SRPSKI, 3, False), ('Игре XX века', 2, True)])
def test_solver_prihvata_ispravne_blokove_obe_nedelje(p, fond, igracki):
    from src.resavac import _izvuci_casove
    z = zahtev(p, '11', fond, 'Ана')
    u = ulaz([z])
    if igracki:
        u = replace(u, predmeti={p: Predmet(p, False, True)})
    sobe = (SALA,) if igracki else (UCIONICA,)
    m, js, vs = napravi_model(u, sobe, (), Smena.CRVENA, sa_nedeljom_b=True, sa_ciljem=False)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    solver.parameters.num_search_workers = 1
    assert solver.solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    for b in (False, True):
        c = _izvuci_casove(solver, u, js, vs, nedelja_b=b)
        r = proveri(u, sobe, (), c, Smena.PLAVA if b else Smena.CRVENA)
        assert r.ispravan, r.tekst()


def test_dvocas_ne_moze_imati_korepetitora_samo_na_jednom_casu():
    z = replace(zahtev('Класичан балет', '11', 2, 'Ана', 'Ива'), fond_korepeticije=1)
    m, _, _ = napravi_model(ulaz([z]), (SALA,), (), Smena.CRVENA)
    solver = cp_model.CpSolver()
    assert solver.solve(m) == cp_model.INFEASIBLE
