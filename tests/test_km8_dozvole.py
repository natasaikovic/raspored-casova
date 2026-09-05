from dataclasses import replace
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from src.km8 import dozvola_za, dozvoljen_km8, proveri_km8, ucitaj_dozvole_km8
from src.loader import UlazGreska
from src.model import Skola, Smena
from src.proveravac import Cas, proveri
from src.resavac import (_moguce_prostorije, _dodeli_prostorije_obe,
                         napravi_model, ucitaj_standardne_ulaze)


@pytest.fixture(scope='module')
def stvarni():
    return ucitaj_standardne_ulaze('ulazi')


def zahtev(u, predmet, grupa):
    return next(z for z in u.zahtevi if z.predmet == predmet and z.odeljenja == (grupa,))


def cas(z, blok=1, dan='понедељак', soba='KM-8', red=2):
    return Cas(dan, blok, z.predmet, z.odeljenja, z.nastavnik, z.korepetitor, soba, red)


def test_svih_60_dozvola_i_sve_kolone_odgovaraju_ulazima(stvarni):
    u, sobe, _ = stvarni
    assert len(u.dozvole_km8) == 60
    assert {d.red_excel for d in u.dozvole_km8} == set(range(2, 62))
    for d in u.dozvole_km8:
        z = zahtev(u, d.predmet, d.odeljenje)
        assert u.odeljenja[d.odeljenje].skola is d.skola
        assert z.nastavnik == d.nastavnik
        assert z.korepetitor == d.korepetitor
        assert z.fond == (3 if d.najvise_casova == 1 else d.fond)
        assert z.fond_korepeticije == (3 if d.najvise_casova == 1 else d.fond_korepeticije)
        assert 'KM-8' in {p.oznaka for p in _moguce_prostorije(z, u, sobe, 1)}
    assert u.ukupno_casova == 863


@pytest.mark.parametrize('predmet,grupa', [
    ('Савремена игра', '31'), ('Савремена игра', '33'),
    ('Сценско народне игре', 'III3'),
    ('Класичан балет – главни предмет', 'I1'),
    ('Народна игра – главни предмет', 'I5'),
    ('Класичан балет', '32'), ('Примењена гимнастика', 'I1'),
    ('Карактерне игре', 'II5'), ('Карактерне игре', 'III1'),
])
def test_nenavedene_kombinacije_su_zabranjene(stvarni, predmet, grupa):
    u, _, _ = stvarni
    assert dozvola_za(u, predmet, grupa) is None
    assert proveri_km8(u, [Cas('понедељак', 1, predmet, (grupa,), 'Н', None, 'KM-8', 2)], Smena.CRVENA)


def test_pogresan_nivo_i_prazna_lista_ne_dozvoljavaju_pg(stvarni):
    u, sobe, _ = stvarni
    z = zahtev(u, 'Примењена гимнастика', '11')
    pogresan = replace(u, odeljenja={**u.odeljenja, '11': replace(u.odeljenja['11'], skola=Skola.SREDNJA)})
    for ulaz in (pogresan, replace(u, dozvole_km8=())):
        assert not dozvoljen_km8(ulaz, z, 1)
        assert 'KM-8' not in {p.oznaka for p in _moguce_prostorije(z, ulaz, sobe, 1)}


@pytest.mark.parametrize('grupa', ['41', '42', '43'])
def test_stvarna_smena_zasebno_za_obe_nedelje(stvarni, grupa):
    u, _, _ = stvarni
    z = zahtev(u, 'Сценско народне игре', grupa)
    for jutarnja in (Smena.CRVENA, Smena.PLAVA):
        jutro = z.smena is jutarnja
        assert dozvoljen_km8(u, z, 2, jutarnja, 1) == jutro
        assert not dozvoljen_km8(u, z, 2, jutarnja, 9)
        assert bool(proveri_km8(u, [cas(z)], jutarnja)) == (not jutro)
        assert proveri_km8(u, [cas(z, 9)], jutarnja)


@pytest.mark.parametrize('grupa', ['I1', 'I2', 'II1', 'II2'])
def test_karakterne_limit_i_zabrana_podele_dvocasa(stvarni, grupa):
    u, sobe, _ = stvarni
    z = zahtev(u, 'Карактерне игре', grupa)
    assert z.fond == 3
    assert dozvoljen_km8(u, z, 1)
    assert not dozvoljen_km8(u, z, 2)
    assert 'KM-8' not in {p.oznaka for p in _moguce_prostorije(z, u, sobe, 2)}
    assert not proveri_km8(u, [cas(z)], Smena.CRVENA)
    assert proveri_km8(u, [cas(z), cas(z, dan='уторак', red=3)], Smena.CRVENA)
    assert proveri_km8(u, [cas(z), cas(z, 2, soba='KM-2', red=3)], Smena.CRVENA)
    # Three separate singles cannot evade the existing 2+1 rule either.
    singles = [cas(z, dan=d, soba='KM-8' if i == 0 else 'KM-2', red=i+2)
               for i, d in enumerate(('понедељак', 'уторак', 'среда'))]
    report = proveri(replace(u, zahtevi=(z,)), sobe, (), singles)
    assert any('двочаса' in e for e in report.greske)


@pytest.mark.parametrize('grupa', ['II5А','II5Б','III5А','III5Б','IV5А','IV5Б'])
def test_ogranicenje_nije_preneto_na_druge_polugrupe(stvarni, grupa):
    u, _, _ = stvarni
    z = zahtev(u, 'Карактерне игре', grupa)
    assert dozvoljen_km8(u, z, 2)
    assert not proveri_km8(u, [cas(z), cas(z, 2, red=3)], Smena.CRVENA)
    other = 'II5Б' if grupa == 'II5А' else 'II5А'
    dozvola = dozvola_za(u, z.predmet, grupa)
    samo_jedna = replace(u, dozvole_km8=(dozvola,))
    assert dozvola_za(samo_jedna, z.predmet, other) is None


@pytest.mark.parametrize('samo_lokacije', [False, True])
def test_solver_i_naknadna_dodela_postuju_smenu(stvarni, samo_lokacije):
    u, sobe, _ = stvarni
    z = zahtev(u, 'Сценско народне игре', '41')
    u = replace(u, zahtevi=(z,))
    sobe = tuple(p for p in sobe if p.oznaka in ('KM-1','KM-8'))
    model, jedinice, promenljive = napravi_model(u, sobe, (), Smena.CRVENA,
        sa_nedeljom_b=True, samo_lokacije=samo_lokacije, sa_ciljem=False)
    p = promenljive[jedinice[0].indeks]
    jutro_a = z.smena is Smena.CRVENA
    model.add(p.start == (1 if jutro_a else 9))
    model.add(p.start_b == (9 if jutro_a else 1))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    assert solver.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    if samo_lokacije:
        d = _dodeli_prostorije_obe(solver, u, sobe, jedinice, promenljive)
        assert d is not None
        assert set(d[1 if jutro_a else 0].values()) == {'KM-1'}
    else:
        popodne = p.prostorije_b if jutro_a else p.prostorije
        assert not solver.boolean_value(popodne['KM-8'])
        model.add(popodne['KM-8'] == 1)
        assert solver.solve(model) == cp_model.INFEASIBLE


def test_nepoznata_napomena_i_neslaganje_uslova_su_greska(tmp_path):
    text = Path('ulazi/dozvole_km8.csv').read_text()
    for old, new in [('Само у преподневној смени', 'можда'),
                     ('Само у преподневној смени,1,,', 'Само у преподневној смени,0,,')]:
        p = tmp_path / 'dozvole.csv'
        p.write_text(text.replace(old, new))
        with pytest.raises(UlazGreska):
            ucitaj_dozvole_km8(p)
