from datetime import date

import pytest

from allocation import plan as p
from allocation.plan import DiaAllocation as D

F = date(2026, 10, 8)


def test_used_cero_pone_max_cero_sin_tocar_release():
    a = p.planear_dia(D(F, 0, 5, 3))
    assert (a.tipo, a.nuevo_max, a.nuevo_release) == (p.CERRAR, 0, None)


def test_used_mayor_cero_max_used_y_release_9999():
    a = p.planear_dia(D(F, 2, 5, 3))
    assert (a.tipo, a.nuevo_max, a.nuevo_release) == (p.CERRAR, 2, 9999)


def test_max_menor_que_used_sube_a_used():
    a = p.planear_dia(D(F, 4, 1, 0))
    assert (a.nuevo_max, a.nuevo_release) == (4, 9999)


def test_ya_cerradas():
    assert p.planear_dia(D(F, 0, 0, 0)).tipo == p.YA_CERRADA
    assert p.planear_dia(D(F, 0, 0, 9999)).tipo == p.YA_CERRADA
    assert p.planear_dia(D(F, 3, 3, 9999)).tipo == p.YA_CERRADA


def test_falta_solo_el_release():
    a = p.planear_dia(D(F, 3, 3, 0))
    assert (a.tipo, a.nuevo_max, a.nuevo_release) == (p.CERRAR, None, 9999)


def test_idempotente_tras_aplicar():
    for dia in (D(F, 0, 5, 3), D(F, 2, 5, 3), D(F, 4, 1, 0), D(F, 3, 3, 0)):
        a = p.planear_dia(dia)
        despues = D(F, dia.used, a.nuevo_max if a.nuevo_max is not None else dia.max,
                    a.nuevo_release if a.nuevo_release is not None else dia.release)
        assert p.planear_dia(despues).tipo == p.YA_CERRADA


def test_barrera_no_reabre():
    with pytest.raises(p.ReaperturaProhibida):
        p.verificar_no_reabre(D(F, 0, 0, 0), p.Accion(F, p.CERRAR, nuevo_max=2))
    with pytest.raises(p.ReaperturaProhibida):
        p.verificar_no_reabre(D(F, 5, 5, 0), p.Accion(F, p.CERRAR, nuevo_max=9))
    with pytest.raises(p.ReaperturaProhibida):
        p.verificar_no_reabre(D(F, 0, 3, 0), p.Accion(F, p.CERRAR, nuevo_release=9999))


def test_planear_sin_fila_y_resumen():
    dias = {F: D(F, 0, 5, 0), date(2026, 10, 9): D(date(2026, 10, 9), 0, 0, 0)}
    acc = p.planear(dias, [F, date(2026, 10, 9), date(2027, 5, 1)])
    assert [a.tipo for a in acc] == [p.CERRAR, p.YA_CERRADA, p.SIN_FILA]
    txt = p.resumen("ST", acc)
    assert "cerraría 1" in txt and "ya cerradas 1" in txt and "SIN FILA" in txt and "01/05/27" in txt
