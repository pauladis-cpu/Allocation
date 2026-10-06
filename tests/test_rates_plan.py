from datetime import date

import pytest

from allocation import rates_plan as r
from allocation.rates_plan import Periodo as P

D = date


def grilla_nov(status_tail="Confirmed"):
    """Ejemplo de la spec 6.4: 17/11-23/11, 24/11 y 25/11-27/11 en Manual; 28/11-30/11 en Confirmed."""
    filas = []
    for pc in ("TR", "ND"):
        filas += [P(D(2026, 11, 17), D(2026, 11, 23), pc, "Manual"), P(D(2026, 11, 24), D(2026, 11, 24), pc, "Manual"),
                  P(D(2026, 11, 25), D(2026, 11, 27), pc, "Manual"), P(D(2026, 11, 28), D(2026, 11, 30), pc, status_tail)]
    return filas


def test_sin_splits_se_editan_los_periodos_confirmed():
    plan = r.planear(grilla_nov(), [(D(2026, 11, 20), D(2026, 11, 30))])
    assert plan.cortes == []
    assert [(e.periodo.ini, e.periodo.fin, e.periodo.pc, e.nuevo_status) for e in plan.ediciones] == [
        (D(2026, 11, 28), D(2026, 11, 30), "TR", "Manual"), (D(2026, 11, 28), D(2026, 11, 30), "ND", "Manual")]
    assert len(plan.ya_cerrados) == 6      # TR/ND en Manual ya están cerrados


def test_un_corte():
    g = [P(D(2026, 12, 29), D(2027, 6, 30), "TR", "Confirmed")]
    plan = r.planear(g, [(D(2026, 12, 29), D(2027, 1, 5))])
    assert plan.cortes == [r.Corte(D(2026, 12, 29), D(2027, 6, 30), D(2027, 1, 6))]
    assert plan.ediciones == []


def test_dos_cortes():
    g = [P(D(2026, 12, 1), D(2026, 12, 25), "TR", "Confirmed"), P(D(2026, 12, 1), D(2026, 12, 25), "ND", "Confirmed")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.cortes == [r.Corte(D(2026, 12, 1), D(2026, 12, 25), D(2026, 12, 10)),
                           r.Corte(D(2026, 12, 1), D(2026, 12, 25), D(2026, 12, 13))]


def test_tras_cortar_se_edita_el_periodo_exacto():
    g = [P(D(2026, 12, 1), D(2026, 12, 9), "TR", "Confirmed"), P(D(2026, 12, 10), D(2026, 12, 12), "TR", "Confirmed"),
         P(D(2026, 12, 13), D(2026, 12, 25), "TR", "Confirmed")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.cortes == [] and [(e.periodo.ini, e.periodo.fin) for e in plan.ediciones] == [(D(2026, 12, 10), D(2026, 12, 12))]


def test_statuses_por_price_code():
    assert r.decidir_status("Confirmed", "TR") == "Manual"
    assert r.decidir_status("Confirmed", "nd") == "Manual"
    assert r.decidir_status("Confirmed", "EM") == "Manual"
    assert r.decidir_status("Confirmed", "RACK") == "Closed"
    assert r.decidir_status("Manual", "TR") is None
    assert r.decidir_status("Manual", "RACK") == "Closed"
    assert r.decidir_status("Closed", "TR") is None
    assert r.decidir_status("Closed", "RACK") is None


def test_closed_nunca_pasa_a_manual():
    for pc in ("TR", "ND", "EM", "RACK", "X"):
        assert r.decidir_status("Closed", pc) is None
    with pytest.raises(r.PlanRatesError):
        r.verificar_no_pasa_de_closed_a_manual("Closed", "Manual")
    r.verificar_no_pasa_de_closed_a_manual("Manual", "Closed")


@pytest.mark.parametrize("st", ["Provisional", "Terminal"])
def test_provisional_y_terminal_frenan(st):
    g = [P(D(2026, 12, 1), D(2026, 12, 25), "TR", st)]
    with pytest.raises(r.PlanRatesError):
        r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])


def test_fuera_del_rango_no_frena():
    g = [P(D(2026, 1, 1), D(2026, 1, 31), "TR", "Provisional")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.ediciones == [] and plan.sin_periodo[0] == D(2026, 12, 10)


def test_rate_name_o_status_raros_frenan():
    with pytest.raises(r.PlanRatesError):
        r.planear([P(D(2026, 12, 1), D(2026, 12, 25), "TR", "Confirmed", "Promo")], [(D(2026, 12, 10), D(2026, 12, 12))])
    with pytest.raises(r.PlanRatesError):
        r.normalizar_status("Confirmed Manual")
    with pytest.raises(r.PlanRatesError):
        r.normalizar_status("Algo")


def test_idempotente_todo_cerrado():
    g = [P(D(2026, 12, 10), D(2026, 12, 12), "TR", "Manual"), P(D(2026, 12, 10), D(2026, 12, 12), "RACK", "Closed")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.cortes == [] and plan.ediciones == [] and len(plan.ya_cerrados) == 2


def test_periodo_que_cubre_dos_rangos_disjuntos():
    g = [P(D(2026, 12, 1), D(2026, 12, 31), "TR", "Confirmed")]
    plan = r.planear(g, [(D(2026, 12, 5), D(2026, 12, 6)), (D(2026, 12, 10), D(2026, 12, 11))])
    assert [c.fecha for c in plan.cortes] == [D(2026, 12, 5), D(2026, 12, 7), D(2026, 12, 10), D(2026, 12, 12)]
