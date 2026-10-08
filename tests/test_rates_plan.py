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


def test_provisional_se_procesa_como_confirmed():
    assert r.decidir_status("Provisional", "TR") == "Manual"
    assert r.decidir_status("Provisional", "ND") == "Manual"
    assert r.decidir_status("Provisional", "EM") == "Manual"
    assert r.decidir_status("Provisional", "RACK") == "Closed"


def test_terminal_pasa_al_objetivo_del_price_code():
    for pc in ("TR", "ND", "EM", "tr", "em"):
        assert r.decidir_status("Terminal", pc) == "Manual"
    for pc in ("RACK", "X"):
        assert r.decidir_status("Terminal", pc) == "Closed"


def test_fx_nunca_se_edita():
    for st in ("Confirmed", "Provisional", "Terminal", "Manual", "Closed"):
        assert r.decidir_status(st, "FX") is None
        assert r.decidir_status(st, "fx") is None
    # ni siquiera se valida su status/rate name: no se evalúa
    g = [P(D(2026, 12, 1), D(2026, 12, 25), "FX", "Raro Estado", "Promo"),
         P(D(2026, 12, 1), D(2026, 12, 25), "TR", "Terminal")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert [p.pc for p in plan.intocables] == ["FX"]
    assert plan.ediciones == [] and plan.cortes                               # primero hay que cortar (por TR)


def test_fx_comparte_el_corte_pero_nunca_se_edita():
    """El split con 'Split All Applicable Price Codes' corta también el período de FX (permitido); después
    solo se editan los demás price codes."""
    antes = [P(D(2026, 12, 1), D(2026, 12, 25), "FX", "Confirmed"), P(D(2026, 12, 1), D(2026, 12, 25), "TR", "Confirmed")]
    rangos = [(D(2026, 12, 10), D(2026, 12, 12))]
    plan = r.planear(antes, rangos)
    assert [(c.ini, c.fin, c.fecha) for c in plan.cortes][0] == (D(2026, 12, 1), D(2026, 12, 25), D(2026, 12, 10))
    despues = [P(D(2026, 12, 1), D(2026, 12, 9), "FX", "Confirmed"), P(D(2026, 12, 10), D(2026, 12, 12), "FX", "Confirmed"),
               P(D(2026, 12, 13), D(2026, 12, 25), "FX", "Confirmed"),
               P(D(2026, 12, 1), D(2026, 12, 9), "TR", "Confirmed"), P(D(2026, 12, 10), D(2026, 12, 12), "TR", "Confirmed"),
               P(D(2026, 12, 13), D(2026, 12, 25), "TR", "Confirmed")]
    plan = r.planear(despues, rangos)
    assert plan.cortes == [] and [(e.periodo.pc, e.nuevo_status) for e in plan.ediciones] == [("TR", "Manual")]
    assert [p.pc for p in plan.intocables] == ["FX"]


def test_fx_solo_no_genera_cortes_ni_ediciones():
    g = [P(D(2026, 12, 1), D(2026, 12, 25), "FX", "Confirmed")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.cortes == [] and plan.ediciones == [] and len(plan.intocables) == 1
    assert plan.sin_periodo == []                                           # el período existe aunque no se edite


def test_barrera_fx_antes_de_escribir():
    with pytest.raises(r.PlanRatesError, match="FX"):
        r.verificar_no_es_intocable("FX")
    with pytest.raises(r.PlanRatesError):
        r.verificar_no_es_intocable("fx")
    r.verificar_no_es_intocable("TR")


def test_resumen_informa_fx():
    g = [P(D(2026, 12, 10), D(2026, 12, 12), "FX", "Confirmed"), P(D(2026, 12, 10), D(2026, 12, 12), "TR", "Manual")]
    assert "FX sin editar 1" in r.resumen("HAB", r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))]))


def test_fuera_del_rango_no_frena():
    g = [P(D(2026, 1, 1), D(2026, 1, 31), "TR", "Provisional")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.ediciones == [] and plan.sin_periodo[0] == D(2026, 12, 10)


def test_status_ambiguo_o_desconocido_frena():
    with pytest.raises(r.PlanRatesError):
        r.normalizar_status("Confirmed Manual")
    with pytest.raises(r.PlanRatesError):
        r.normalizar_status("Algo")


def test_el_rate_name_no_influye_en_el_cierre():
    for nombre in ("Standard", "Promo", "", "Cualquier cosa"):
        g = [P(D(2026, 12, 1), D(2026, 12, 25), "TR", "Confirmed", nombre)]
        plan = r.planear(g, [(D(2026, 12, 1), D(2026, 12, 25))])
        assert [(e.periodo.pc, e.nuevo_status) for e in plan.ediciones] == [("TR", "Manual")]


def test_idempotente_todo_cerrado():
    g = [P(D(2026, 12, 10), D(2026, 12, 12), "TR", "Manual"), P(D(2026, 12, 10), D(2026, 12, 12), "RACK", "Closed")]
    plan = r.planear(g, [(D(2026, 12, 10), D(2026, 12, 12))])
    assert plan.cortes == [] and plan.ediciones == [] and len(plan.ya_cerrados) == 2


def test_periodo_que_cubre_dos_rangos_disjuntos():
    g = [P(D(2026, 12, 1), D(2026, 12, 31), "TR", "Confirmed")]
    plan = r.planear(g, [(D(2026, 12, 5), D(2026, 12, 6)), (D(2026, 12, 10), D(2026, 12, 11))])
    assert [c.fecha for c in plan.cortes] == [D(2026, 12, 5), D(2026, 12, 7), D(2026, 12, 10), D(2026, 12, 12)]


def test_restar_meses():
    assert r.restar_meses(D(2026, 10, 1), 5) == D(2026, 5, 1)
    assert r.restar_meses(D(2026, 3, 31), 1) == D(2026, 2, 28)         # el día no existe: último día del mes
    assert r.restar_meses(D(2026, 2, 15), 5) == D(2025, 9, 15)         # cruza el año


def test_limite_de_lectura_es_la_mas_antigua_entre_el_rango_y_el_margen():
    assert r.limite_de_lectura([(D(2026, 10, 1), D(2026, 10, 1))]) == D(2026, 5, 1)            # el ejemplo: mayo 2026
    assert r.limite_de_lectura([(D(2026, 1, 10), D(2026, 10, 1))]) == D(2026, 1, 10)           # el rango pedido llega más atrás


def test_corta_cuando_aparece_un_periodo_de_cinco_meses_antes():
    rangos = [(D(2026, 10, 1), D(2026, 10, 1))]
    # grilla de más lejana a más reciente (desc): 2027 ... hacia 2026
    desc = [P(D(2027, 4, 1), D(2027, 4, 30), "TR", "Confirmed"), P(D(2026, 12, 1), D(2026, 12, 31), "TR", "Confirmed"),
            P(D(2026, 10, 1), D(2026, 10, 31), "TR", "Confirmed"), P(D(2026, 8, 1), D(2026, 8, 31), "TR", "Confirmed")]
    assert not r.ya_paso_el_objetivo(desc, rangos)                       # llegó a agosto: todavía falta (mayo)
    desc.append(P(D(2026, 5, 1), D(2026, 5, 31), "TR", "Confirmed"))
    assert r.ya_paso_el_objetivo(desc, rangos)                           # apareció un período de mayo 2026
    assert not r.ya_paso_el_objetivo(desc, [])


def test_price_codes_con_cortes_distintos_no_cortan_antes_de_tiempo():
    rangos = [(D(2026, 10, 1), D(2026, 10, 1))]
    # TR corta por mes y ND por trimestre: aparecen fuera de orden entre sí, pero ninguno llegó a mayo
    filas = [P(D(2027, 1, 1), D(2027, 3, 31), "ND", "Confirmed"), P(D(2027, 3, 1), D(2027, 3, 31), "TR", "Confirmed"),
             P(D(2026, 10, 1), D(2026, 12, 31), "ND", "Confirmed"), P(D(2026, 11, 1), D(2026, 11, 30), "TR", "Confirmed"),
             P(D(2026, 7, 1), D(2026, 9, 30), "ND", "Confirmed")]
    assert not r.ya_paso_el_objetivo(filas, rangos)


def test_si_la_grilla_viene_ascendente_no_corta():
    asc = [P(D(2026, 1, 1), D(2026, 1, 31), "TR", "Confirmed"), P(D(2026, 5, 1), D(2026, 5, 31), "TR", "Confirmed"),
           P(D(2026, 9, 1), D(2026, 9, 30), "TR", "Confirmed")]
    assert not r.ya_paso_el_objetivo(asc, [(D(2026, 10, 1), D(2026, 10, 1))])


def test_varios_rate_sets_se_deciden_cada_uno_con_las_mismas_reglas():
    assert r.statuses_de("Confirmed, Manual") == ["Confirmed", "Manual"]
    assert r.statuses_de("Manual") == ["Manual"]
    assert r.decidir_statuses("Confirmed, Confirmed", "TR") == ("Manual", "Manual")
    assert r.decidir_statuses("Confirmed, Manual", "RACK") == ("Closed", "Closed")
    assert r.decidir_statuses("Manual, Closed, Terminal", "TR") == ("Closed", None, "Closed")      # no pueden quedar mezclados
    assert r.decidir_statuses("Closed, Closed", "RACK") == (None, None)
    with pytest.raises(r.PlanRatesError):
        r.statuses_de("Confirmed, Raro")


def test_el_plan_marca_la_edicion_si_algun_rate_set_necesita_cambio():
    rango = [(D(2026, 12, 1), D(2026, 12, 25))]
    p = [P(D(2026, 12, 1), D(2026, 12, 25), "TR", "Manual, Confirmed"), P(D(2026, 12, 1), D(2026, 12, 25), "ND", "Manual, Manual")]
    plan = r.planear(p, rango)
    assert [(e.periodo.pc, e.por_set) for e in plan.ediciones] == [("TR", (None, "Manual"))]
    assert [x.pc for x in plan.ya_cerrados] == ["ND"]


def test_los_rate_sets_nunca_quedan_con_status_distintos():
    assert r.decidir_statuses("Manual, Confirmed", "TR") == (None, "Manual")            # ya procesado a medias: se completa
    assert r.decidir_statuses("Confirmed, Manual", "EM") == ("Manual", None)
    assert r.decidir_statuses("Manual, Closed", "TR") == ("Closed", None)               # Closed no se reabre: el otro se cierra
    assert r.decidir_statuses("Closed, Confirmed", "TR") == (None, "Closed")
    assert r.decidir_statuses("Closed, Confirmed", "RACK") == (None, "Closed")
    assert r.decidir_statuses("Manual, Manual", "TR") == (None, None)
    for txt, pc in (("Manual, Confirmed", "TR"), ("Manual, Closed", "TR"), ("Closed, Terminal", "ND"), ("Provisional, Manual", "RACK")):
        actuales = r.statuses_de(txt)
        finales = {d or a for d, a in zip(r.decidir_statuses(txt, pc), actuales)}
        assert len(finales) == 1
