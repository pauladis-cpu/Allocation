from datetime import date

import runner
from allocation import cola, registro
from allocation.plan import DiaAllocation
from tests.test_registro_cola import COLS, FILAS
from tourplan_flujos import allocations as fl

HOY = date(2026, 10, 5)


def _pedido(allocs_txt, fechas_txt, hotel="1EDE01"):
    return {cola.C_ID: "P-1", cola.C_HOTEL_COD: hotel, cola.C_ALLOCS: allocs_txt, cola.C_FECHAS: fechas_txt}


def test_lectura_arma_observaciones_y_no_escribe(monkeypatch):
    allocs = registro.construir_allocations(FILAS, COLS)
    llamadas = []
    monkeypatch.setattr(fl, "preparar_hotel", lambda d, c, h=None: llamadas.append(("hotel", c)))

    def leer(driver, a, codigo_hotel, fechas):
        llamadas.append(("alloc", a.codigo))
        if a.codigo == "SPWV":
            raise fl.FlujoError("Habitación linkeada: registro='X', Tourplan=['Y'].")
        return {date(2026, 10, 8): DiaAllocation(date(2026, 10, 8), 0, 4, 0)}, ""

    monkeypatch.setattr(fl, "leer_allocation", leer)
    import common.tourplan as tp
    monkeypatch.setattr(tp, "ss", lambda *a, **k: None)
    obs = runner.procesar_pedido_lectura(
        object(), _pedido("TODAS", "2026-10-04; 2026-10-08; 2026-10-09"), allocs, HOY)
    assert ("hotel", "1EDE01") in llamadas
    assert "1 fecha(s) ya pasada(s)" in obs
    assert "1EDE01 CL: cerraría 1 (08/10/26)" in obs and "SIN FILA" in obs      # el 9/10 no tiene fila
    assert "SPWV: NO SE ESCRIBIRÍA NADA" in obs


def test_hotel_o_allocation_inexistente(monkeypatch):
    allocs = registro.construir_allocations(FILAS, COLS)
    assert runner.procesar_pedido_lectura(object(), _pedido("X", "2026-10-08", hotel="NOEXISTE"), allocs, HOY).startswith("ERROR")
    monkeypatch.setattr(fl, "preparar_hotel", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe abrir Tourplan")))
    obs = runner.procesar_pedido_lectura(object(), _pedido("NOPE", "2026-10-08"), allocs, HOY)
    assert "no encontrada" in obs and "nada para leer" in obs
