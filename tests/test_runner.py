from datetime import date

import pytest

import runner
from allocation import cola, plan, rates_plan, registro
from allocation.plan import DiaAllocation
from common.abort import AbortadoPorUsuario
from tests.test_registro_cola import COLS, FILAS, FakeWS
from tourplan_flujos import allocations as fl
from tourplan_flujos import rates as rt

HOY = date(2026, 10, 5)
ALLOCS = registro.construir_allocations(FILAS, COLS)


def _ws(**valores):
    ws = FakeWS(cola.COLUMNAS_COLA)
    fila = {c: "" for c in cola.COLUMNAS_COLA}
    fila.update({cola.C_ID: "P-1", cola.C_HOTEL_COD: "6RABA1", cola.C_ALLOCS: "Standard",
                 cola.C_FECHAS: "2026-10-04; 2026-10-08", cola.C_CANT: 2, cola.C_MODO: "aplicar",
                 cola.C_EST_ALLOT: "PENDIENTE", cola.C_EST_TARIFA: "PENDIENTE"})
    fila.update(valores)
    ws.filas.append([fila[c] for c in cola.COLUMNAS_COLA])
    return ws


def _fila(ws):
    d = dict(zip(cola.COLUMNAS_COLA, ws.filas[1]))
    d["__row_idx__"] = 2
    return d


def _estado(ws):
    d = _fila(ws)
    return d


@pytest.fixture()
def flujo(monkeypatch):
    """Selenium simulado: registra qué se llamó y con qué modo."""
    import common.tourplan as tp
    monkeypatch.setattr(tp, "ss", lambda *a, **k: None)
    llamadas = []
    monkeypatch.setattr(fl, "preparar_hotel", lambda d, c, h=None: llamadas.append(("hotel", c)))

    def cerrar_allocation(driver, a, codigo_hotel, fechas, aplicar=False, hoy=None):
        llamadas.append(("allocation", a.codigo, aplicar, list(fechas)))
        d = date(2026, 10, 8)
        return plan.planear({d: DiaAllocation(d, 0, 4, 0)}, fechas), ""
    monkeypatch.setattr(fl, "cerrar_allocation", cerrar_allocation)

    def procesar_habitacion(driver, codigo_hotel, hab, rangos, aplicar=False, **k):
        llamadas.append(("habitacion", hab, aplicar, rangos))
        return rates_plan.Plan(), f"{hab}: ok", 2
    monkeypatch.setattr(rt, "procesar_habitacion", procesar_habitacion)
    return llamadas


def test_lectura_deja_el_plan_en_observaciones_y_no_toca_estados(flujo):
    ws = _ws(MODO="lectura")
    runner.ejecutar_pedido(object(), ws, _fila(ws), ALLOCS, HOY, aplicar=False)
    f = _fila(ws)
    assert f[cola.C_EST_ALLOT] == f[cola.C_EST_TARIFA] == "PENDIENTE" and not f[cola.C_TOMADO_POR]
    assert f[cola.C_OBS_ALLOT].startswith("[LECTURA") and "cerraría 1" in f[cola.C_OBS_ALLOT]
    assert "1 fecha(s) ya pasada(s)" in f[cola.C_OBS_ALLOT]
    assert f[cola.C_OBS_TARIFA].startswith("[LECTURA") and "BUEHT6RABA1ST" in f[cola.C_OBS_TARIFA]
    assert all(c[2] is False for c in flujo if c[0] in ("allocation", "habitacion"))     # nunca aplicar


def test_aplicar_completa_las_dos_fases_y_es_idempotente(flujo):
    ws = _ws()
    fila0 = _fila(ws)
    assert cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    f = _fila(ws)
    assert (f[cola.C_EST_ALLOT], f[cola.C_EST_TARIFA]) == ("OK", "OK")
    assert f[cola.C_TOMADO_POR] == "Ana"
    assert ("allocation", "Standard", True, [date(2026, 10, 8)]) in flujo        # fechas pasadas descartadas
    assert any(c[0] == "habitacion" and c[1] == "BUEHT6RABA1ST" and c[2] is True for c in flujo)
    # segunda corrida: ya no hay nada pendiente
    runner.SOLO_PEDIDO = ""
    assert runner.seleccionar_pedidos([_fila(ws)]) == []


def test_resumible_si_allotment_ya_esta_ok_solo_hace_tarifa(flujo):
    ws = _ws(ESTADO_CIERRE_ALLOTMENT="OK")
    fila0 = _fila(ws)
    cola.tomar_pedido(ws, 2, "Ana", fases=("tarifa",), dormir=lambda s: None)
    runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    assert not any(c[0] == "allocation" for c in flujo)
    assert _fila(ws)[cola.C_EST_TARIFA] == "OK"


def test_error_en_allotment_no_sigue_y_tarifa_vuelve_a_pendiente(flujo, monkeypatch):
    def falla(*a, **k):
        raise fl.FlujoError("Habitación linkeada: registro='X', Tourplan=['Y'].")
    monkeypatch.setattr(fl, "cerrar_allocation", falla)
    ws = _ws()
    fila0 = _fila(ws)
    cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    f = _fila(ws)
    assert f[cola.C_EST_ALLOT].startswith("ERROR: Standard: Habitación linkeada")
    assert f[cola.C_EST_TARIFA] == "PENDIENTE" and "falló" in f[cola.C_OBS_TARIFA]
    assert not any(c[0] == "habitacion" for c in flujo)


def test_ya_todo_cerrado_es_salteado(flujo, monkeypatch):
    monkeypatch.setattr(fl, "cerrar_allocation", lambda *a, **k: (plan.planear(
        {date(2026, 10, 8): DiaAllocation(date(2026, 10, 8), 0, 0, 0)}, [date(2026, 10, 8)]), ""))
    monkeypatch.setattr(rt, "procesar_habitacion", lambda *a, **k: (rates_plan.Plan(), "x: ya cerrados 3", 0))
    ws = _ws()
    fila0 = _fila(ws)
    cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    f = _fila(ws)
    assert (f[cola.C_EST_ALLOT], f[cola.C_EST_TARIFA]) == ("SALTEADO", "SALTEADO")


def test_abortar_devuelve_las_fases_a_pendiente(flujo, monkeypatch):
    def aborta(*a, **k):
        raise AbortadoPorUsuario()
    monkeypatch.setattr(fl, "cerrar_allocation", aborta)
    ws = _ws()
    fila0 = _fila(ws)
    cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    with pytest.raises(AbortadoPorUsuario):
        runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    f = _fila(ws)
    assert (f[cola.C_EST_ALLOT], f[cola.C_EST_TARIFA]) == ("PENDIENTE", "PENDIENTE")


def test_pedido_invalido_no_abre_tourplan(flujo):
    ws = _ws(**{cola.C_HOTEL_COD: "NOEXISTE"})
    fila0 = _fila(ws)
    cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    assert _fila(ws)[cola.C_EST_ALLOT].startswith("ERROR: el hotel 'NOEXISTE' no figura")
    assert flujo == []


def test_pedido_con_hotel_que_no_cierra_tarifa(flujo):
    ws = _ws(**{cola.C_HOTEL_COD: "1EDE01", cola.C_ALLOCS: "TODAS"})
    fila0 = _fila(ws)
    cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    runner.ejecutar_pedido(object(), ws, fila0, ALLOCS, HOY, aplicar=True)
    f = _fila(ws)
    assert f[cola.C_EST_TARIFA] == "SALTEADO" and f[cola.C_OBS_TARIFA].endswith("no cierra tarifa")
    assert [c[1] for c in flujo if c[0] == "allocation"] == ["1EDE01 CL", "SPWV"]


def test_habitaciones_prohibidas_y_union_sin_repetir(monkeypatch):
    with pytest.raises(runner.PedidoError):
        runner.validar_habitacion("BUEHT6RABA1600HTL", "6RABA1")
    with pytest.raises(runner.PedidoError):
        runner.validar_habitacion("BUEHT6RABA1ROOMS", "6RABA1")
    with pytest.raises(runner.PedidoError):
        runner.validar_habitacion("BUEHX6RABA1600HTX", "6RABA1")          # service HX
    assert runner.validar_habitacion("bueht6raba1st", "6RABA1") == "BUEHT6RABA1ST"
    monkeypatch.setattr(rt, "listar_habitaciones_ht", lambda d, c: ["BUEHT6RABA1ST", "BUEHT6RABA1SU"])
    ra = [a for a in ALLOCS if a.codigo_hotel == "6RABA1"][0]
    from dataclasses import replace
    a2 = replace(ra, codigo="OTRA", tarifas="TODAS")
    assert runner.habitaciones_a_cerrar(None, "6RABA1", [ra, a2]) == ["BUEHT6RABA1ST", "BUEHT6RABA1SU"]
    with pytest.raises(runner.PedidoError, match="REVISAR"):
        runner.habitaciones_a_cerrar(None, "6RABA1", [replace(ra, tarifas="REVISAR")])
    assert runner.habitaciones_a_cerrar(None, "6RABA1", [replace(ra, cierra_tarifa=False)]) is None


def test_produccion_y_modo_por_fila(monkeypatch):
    assert runner._es_produccion("https://tourplannx.eurotur.com.ar/tourplannx/")
    assert not runner._es_produccion("https://tourplannx.eurotur.com.ar/TourplanNX_Test")
    assert runner.modo_de({cola.C_MODO: "aplicar"}) == "aplicar" and runner.modo_de({cola.C_MODO: ""}) == "lectura"
    monkeypatch.setattr(runner, "FORZAR_LECTURA", True)
    assert runner.modo_de({cola.C_MODO: "aplicar"}) == "lectura"
