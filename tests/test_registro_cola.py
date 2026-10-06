from datetime import datetime

import pytest

from allocation import cola, registro

COLS = ["Código hotel", "Hotel", "Allocation (código)", "Descripción exacta en Tourplan",
        "Habitación linkeada (código)", "Descripción de la habitación", "Cierra tarifa",
        "Tarifas a cerrar", "Vigente hasta", "Notas"]


def fila(i, *vals):
    d = dict(zip(COLS, vals))
    d["__row_idx__"] = i
    return d


FILAS = [
    fila(2, "6RABA1", "Ramada Buenos Aires Centro", "Standard", "Standard CIERRA DATABASE",
         "BUEHT6RABA1ST", "", "SI", "LINKEADA", "2027-03-31", ""),
    fila(3, "1EDE01", "NH Edelweiss", "1EDE01 CL", "STANDARD", "BRCHT1EDE01CL", "", "NO", "", "2027-01-10", ""),
    fila(4, "1EDE01", "NH Edelweiss", "SPWV", "SUPERIOR VISTA", "BRCHT1EDE01SV", "", "NO", "", "", "n"),
    fila(5, "", "Novotel", "SIN FS-CIERRA D", "CERRAR DATABASE", "", "", "SI", "TODAS", "", ""),
]


def test_columnas_por_encabezado_aunque_cambie_el_orden():
    cols = list(reversed(COLS))
    allocs = registro.construir_allocations(FILAS, cols)
    assert allocs[0].codigo_hotel == "6RABA1" and allocs[0].cierra_tarifa


def test_falta_columna_obligatoria():
    with pytest.raises(registro.RegistroInvalido):
        registro.construir_allocations(FILAS, [c for c in COLS if c != "Tarifas a cerrar"])


def test_hoteles_busqueda_y_vacias():
    allocs = registro.construir_allocations(FILAS, COLS)
    hoteles = registro.agrupar_hoteles(allocs)
    assert [h.nombre for h in hoteles] == ["NH Edelweiss", "Novotel", "Ramada Buenos Aires Centro"]
    assert len(registro.buscar(hoteles, "edelweiss")) == 1
    assert registro.buscar(hoteles, "6raba1")[0].nombre.startswith("Ramada")
    assert registro.buscar(hoteles, "ramada centro")
    assert registro.buscar(hoteles, "inexistente") == []
    novotel = registro.buscar(hoteles, "novotel")[0]
    assert not novotel.procesable and novotel.allocations[0].vacia
    assert registro.duplicados(allocs) == []


def test_pedido_todas_y_lista():
    from datetime import date
    ahora = datetime(2026, 10, 5, 10, 0, 0)
    v = cola.armar_pedido(codigo_hotel="1EDE01", allocations=["1EDE01 CL", "SPWV"], todas=False,
                          fechas=[date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 8)],
                          cargado_por="Ana", ahora=ahora)
    assert v[cola.C_ALLOCS] == "1EDE01 CL; SPWV"
    assert v[cola.C_FECHAS] == "2026-10-08; 2026-10-20..2026-10-21" and v[cola.C_CANT] == 3
    assert v[cola.C_MODO] == "lectura"
    assert v[cola.C_EST_ALLOT] == v[cola.C_EST_TARIFA] == "PENDIENTE"
    t = cola.armar_pedido(codigo_hotel="1EDE01", allocations=[], todas=True,
                          fechas=[date(2026, 10, 8)], cargado_por="Ana")
    assert t[cola.C_ALLOCS] == "TODAS"


def test_pedido_invalido():
    from datetime import date
    base = dict(allocations=["A"], todas=False, fechas=[date(2026, 10, 8)], cargado_por="x")
    with pytest.raises(cola.PedidoInvalido):
        cola.armar_pedido(codigo_hotel="", **base)
    with pytest.raises(cola.PedidoInvalido):
        cola.armar_pedido(codigo_hotel="H", **{**base, "fechas": []})
    with pytest.raises(cola.PedidoInvalido):
        cola.armar_pedido(codigo_hotel="H", **{**base, "allocations": ["A;B"]})
    with pytest.raises(cola.PedidoInvalido):
        cola.armar_pedido(codigo_hotel="H", **{**base, "allocations": []})


class FakeWS:
    """Hoja en memoria con la interfaz mínima de gspread que usa enviar_pedido."""
    def __init__(self, columnas, rivales=0):
        self.filas = [list(columnas)]
        self.row_count = 1000
        self.rivales = rivales  # veces que "otra PC" gana la carrera

    def row_values(self, r):
        return list(self.filas[r - 1])

    def col_values(self, c):
        return [f[c - 1] if len(f) >= c else "" for f in self.filas]

    def cell(self, r, c):
        class C: pass
        o = C(); o.value = self.filas[r - 1][c - 1] if r <= len(self.filas) else None
        return o

    def batch_update(self, updates):
        from gspread.utils import a1_to_rowcol
        for u in updates:
            r, c = a1_to_rowcol(u["range"])
            while len(self.filas) < r:
                self.filas.append([""] * len(self.filas[0]))
            if self.rivales and r == len(self.filas):
                self.rivales -= 1
                self.filas[r - 1][0] = "P-OTRA-PC"   # la otra PC pisa la fila
                continue
            self.filas[r - 1][c - 1] = u["values"][0][0]

    def add_rows(self, n):
        self.row_count += n


def test_enviar_pedido_y_verifica():
    from datetime import date
    ws = FakeWS(cola.COLUMNAS_COLA)
    v = cola.armar_pedido(codigo_hotel="1EDE01", allocations=["SPWV"], todas=False,
                          fechas=[date(2026, 10, 8)], cargado_por="Ana")
    fila_n = cola.enviar_pedido(ws, v)
    assert fila_n == 2
    assert ws.filas[1][0] == v[cola.C_ID]


def test_enviar_pedido_reintenta_si_otra_pc_pisa_la_fila():
    from datetime import date
    ws = FakeWS(cola.COLUMNAS_COLA, rivales=1)
    v = cola.armar_pedido(codigo_hotel="H", allocations=["A"], todas=False,
                          fechas=[date(2026, 10, 8)], cargado_por="Ana")
    assert cola.enviar_pedido(ws, v) == 3
    assert ws.filas[1][0] == "P-OTRA-PC" and ws.filas[2][0] == v[cola.C_ID]


def test_cola_columnas_faltantes_no_modifica_el_sheet():
    ws = FakeWS([c for c in cola.COLUMNAS_COLA if c != cola.C_TOMADO_POR])
    with pytest.raises(cola.ColaInvalida):
        cola.enviar_pedido(ws, {cola.C_ID: "x"})
    assert len(ws.filas) == 1


def test_estados_y_abandono():
    ahora = datetime(2026, 10, 5, 12, 0, 0)
    f = {cola.C_EST_ALLOT: "EN CURSO", cola.C_EST_TARIFA: "PENDIENTE",
         cola.C_TOMADO_EN: "2026-10-05 11:00:00"}
    assert cola.estado_global(f) == "EN CURSO"
    assert cola.posiblemente_abandonado(f, 30, ahora)
    f[cola.C_TOMADO_EN] = "2026-10-05 11:50:00"
    assert not cola.posiblemente_abandonado(f, 30, ahora)
    assert cola.estado_global({cola.C_EST_ALLOT: "OK", cola.C_EST_TARIFA: "SALTEADO"}) == "OK"
    assert cola.estado_global({cola.C_EST_ALLOT: "OK", cola.C_EST_TARIFA: "ERROR: x"}) == "ERROR"
    assert cola.clasificar_estado("OK (3 cerradas)") == "OK"


def test_encabezados_reales_de_cola():
    # tal como figuran en Registro_de_Allocation_v3.xlsx
    assert cola.C_ORIGEN == "Origen (asunto o remitente del mail)"


def test_columna_hotel_vieja_en_el_sheet_se_ignora():
    # si el Sheet todavía tiene la columna "Hotel" (fórmula), no se pisa
    ws = FakeWS(cola.COLUMNAS_COLA[:4] + ["Hotel"] + cola.COLUMNAS_COLA[4:])
    from datetime import date
    v = cola.armar_pedido(codigo_hotel="H", allocations=["A"], todas=False,
                          fechas=[date(2026, 10, 8)], cargado_por="Ana")
    n = cola.enviar_pedido(ws, v)
    assert ws.filas[n - 1][4] == ""


def test_resolver_allocations():
    allocs = registro.construir_allocations(FILAS, COLS)
    ede = [a for a in allocs if a.codigo_hotel == "1EDE01"]
    enc, falta = registro.resolver_allocations("TODAS", ede)
    assert len(enc) == 2 and not falta
    enc, falta = registro.resolver_allocations("spwv; NO-EXISTE", ede)
    assert [a.codigo for a in enc] == ["SPWV"] and falta == ["NO-EXISTE"]


def _ws_con_pedido(**estados):
    ws = FakeWS(cola.COLUMNAS_COLA)
    fila = {c: "" for c in cola.COLUMNAS_COLA}
    fila.update({cola.C_ID: "P-1", cola.C_EST_ALLOT: "PENDIENTE", cola.C_EST_TARIFA: "PENDIENTE"})
    fila.update(estados)
    ws.filas.append([fila[c] for c in cola.COLUMNAS_COLA])
    return ws


def test_tomar_pedido_ok_y_queda_en_curso():
    ws = _ws_con_pedido()
    assert cola.tomar_pedido(ws, 2, "Ana", dormir=lambda s: None)
    f = dict(zip(cola.COLUMNAS_COLA, ws.filas[1]))
    assert (f[cola.C_TOMADO_POR], f[cola.C_EST_ALLOT], f[cola.C_EST_TARIFA]) == ("Ana", "EN CURSO", "EN CURSO")
    assert f[cola.C_TOMADO_EN]


def test_no_toma_si_ya_lo_tiene_otro_o_no_esta_pendiente():
    assert not cola.tomar_pedido(_ws_con_pedido(TOMADO_POR="Luis"), 2, "Ana", dormir=lambda s: None)
    assert not cola.tomar_pedido(_ws_con_pedido(ESTADO_CIERRE_ALLOTMENT="OK"), 2, "Ana", dormir=lambda s: None)
    # fase concreta: tarifa PENDIENTE y allotment OK -> se puede tomar solo la tarifa
    ws = _ws_con_pedido(ESTADO_CIERRE_ALLOTMENT="OK")
    assert cola.tomar_pedido(ws, 2, "Ana", fases=("tarifa",), dormir=lambda s: None)
    assert dict(zip(cola.COLUMNAS_COLA, ws.filas[1]))[cola.C_EST_ALLOT] == "OK"


def test_dos_pcs_nadie_procesa_el_mismo_pedido_dos_veces():
    ws = _ws_con_pedido()
    resultados = {}

    def otra_pc_pisa(segundos):               # durante la espera de Ana, Luis escribe encima
        fila = ws.filas[1]
        fila[cola.COLUMNAS_COLA.index(cola.C_TOMADO_POR)] = "Luis"
    resultados["ana"] = cola.tomar_pedido(ws, 2, "Ana", dormir=otra_pc_pisa)
    assert resultados["ana"] is False                                     # Ana suelta
    assert dict(zip(cola.COLUMNAS_COLA, ws.filas[1]))[cola.C_TOMADO_POR] == "Luis"   # la fila queda de Luis
    assert not cola.tomar_pedido(ws, 2, "Pedro", dormir=lambda s: None)  # y nadie más la toma


def test_escribir_fase():
    ws = _ws_con_pedido()
    cola.escribir_fase(ws, 2, "tarifa", "SALTEADO", "no cierra tarifa")
    f = dict(zip(cola.COLUMNAS_COLA, ws.filas[1]))
    assert (f[cola.C_EST_TARIFA], f[cola.C_OBS_TARIFA], f[cola.C_EST_ALLOT]) == ("SALTEADO", "no cierra tarifa", "PENDIENTE")
