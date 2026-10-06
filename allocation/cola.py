"""Pedidos en la hoja COLA: crear (la app escribe) y leer/clasificar.

Un pedido es un hotel. Cada fase (allocation, tarifa) tiene su propio estado
para poder retomar si una falla. Estados: PENDIENTE -> EN CURSO -> OK /
SALTEADO / "ERROR: detalle".

La hoja ya no usa la columna "Hotel" (el nombre se resuelve con el registro).
Si todavía existe en el Sheet, la app la ignora y nunca la escribe. Las columnas
se ubican por encabezado y nunca se modifican encabezados.
"""

import secrets
import time
from datetime import datetime

from allocation.constantes import (
    ALLOCATIONS_TODAS, ESTADO_EN_CURSO, ESTADO_ERROR, ESTADO_OK, ESTADO_PENDIENTE,
    ESTADO_SALTEADO, MODO_APLICAR, MODO_LECTURA, SEPARADOR_ALLOCATIONS,
)
from allocation.fechas import a_texto_normalizado, de_texto_normalizado
from allocation.registro import normalizar

C_ID = "ID_PEDIDO"
C_FECHA_CARGA = "Fecha de carga"
C_CARGADO_POR = "Cargado por"
C_HOTEL_COD = "Hotel (código)"
C_ALLOCS = "Allocation(es) (código o TODAS)"
C_FECHAS = "Fechas a cerrar"
C_CANT = "Cant. de fechas"
C_ORIGEN = "Origen (asunto o remitente del mail)"
C_MODO = "MODO"
C_EST_ALLOT = "ESTADO_CIERRE_ALLOTMENT"
C_OBS_ALLOT = "OBSERVACIONES_CIERRE_ALLOTMENT"
C_EST_TARIFA = "ESTADO_CIERRE_TARIFA"
C_OBS_TARIFA = "OBSERVACIONES_CIERRE_TARIFA"
C_TOMADO_POR = "TOMADO_POR"
C_TOMADO_EN = "TOMADO_EN"

COLUMNAS_COLA = [
    C_ID, C_FECHA_CARGA, C_CARGADO_POR, C_HOTEL_COD, C_ALLOCS, C_FECHAS, C_CANT,
    C_ORIGEN, C_MODO, C_EST_ALLOT, C_OBS_ALLOT, C_EST_TARIFA, C_OBS_TARIFA,
    C_TOMADO_POR, C_TOMADO_EN,
]
COLUMNAS_ESCRITAS = list(COLUMNAS_COLA)

FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"


class ColaInvalida(ValueError):
    pass


class PedidoInvalido(ValueError):
    pass


def nuevo_id(ahora=None):
    ahora = ahora or datetime.now()
    return f"P-{ahora:%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def armar_pedido(*, codigo_hotel, allocations, todas, fechas, cargado_por,
                 modo=MODO_LECTURA, origen="", ahora=None):
    """Valores (por nombre de columna) de un pedido nuevo.

    allocations: códigos de allocation elegidos. todas=True -> "TODAS"
    (se carga una sola vez, todas las allocations del hotel en el registro).
    """
    if not (codigo_hotel or "").strip():
        raise PedidoInvalido("El hotel no tiene código de supplier: no se puede procesar.")
    if modo not in (MODO_LECTURA, MODO_APLICAR):
        raise PedidoInvalido(f"Modo inválido: {modo!r}")
    fechas = sorted(set(fechas))
    if not fechas:
        raise PedidoInvalido("No hay fechas vigentes para cerrar.")
    if todas:
        alloc_txt = ALLOCATIONS_TODAS
    else:
        codigos = [c.strip() for c in allocations if c and c.strip()]
        if not codigos:
            raise PedidoInvalido("No se eligió ninguna allocation.")
        if any(SEPARADOR_ALLOCATIONS in c for c in codigos):
            raise PedidoInvalido(
                f"Un código de allocation contiene {SEPARADOR_ALLOCATIONS!r}: no se puede guardar en la cola.")
        if normalizar(ALLOCATIONS_TODAS) in {normalizar(c) for c in codigos}:
            raise PedidoInvalido(f"Hay una allocation llamada {ALLOCATIONS_TODAS!r}: ambigua con 'Todas'.")
        alloc_txt = f"{SEPARADOR_ALLOCATIONS} ".join(codigos)
    ahora = ahora or datetime.now()
    return {
        C_ID: nuevo_id(ahora),
        C_FECHA_CARGA: ahora.strftime(FORMATO_FECHA_HORA),
        C_CARGADO_POR: cargado_por,
        C_HOTEL_COD: codigo_hotel.strip(),
        C_ALLOCS: alloc_txt,
        C_FECHAS: a_texto_normalizado(fechas),
        C_CANT: len(fechas),
        C_ORIGEN: origen,
        C_MODO: modo,
        C_EST_ALLOT: ESTADO_PENDIENTE,
        C_EST_TARIFA: ESTADO_PENDIENTE,
    }


def verificar_columnas(columnas):
    faltan = [c for c in COLUMNAS_ESCRITAS if c not in columnas]
    if faltan:
        raise ColaInvalida(
            f"Faltan columnas en la hoja COLA: {faltan}. No se modificó el Sheet. "
            f"Columnas detectadas: {[c for c in columnas if c]}")


def enviar_pedido(ws, valores, intentos=3):
    """Agrega el pedido al final de COLA y verifica que la fila quedó con nuestro
    ID_PEDIDO (dos PCs podrían escribir la misma fila a la vez; Sheets no tiene
    escritura atómica). Devuelve el número de fila."""
    from common.sheets_client import actualizar_fila_sheet
    columnas = ws.row_values(1)
    verificar_columnas(columnas)
    col_id = columnas.index(C_ID) + 1
    for _ in range(intentos):
        # primera fila libre según ID_PEDIDO
        ids = ws.col_values(col_id)
        row_idx = len(ids) + 1
        actualizar_fila_sheet(ws, row_idx, columnas, valores)
        if ws.cell(row_idx, col_id).value == valores[C_ID]:
            return row_idx
    raise ColaInvalida("No pude escribir el pedido sin pisar a otra persona. Reintentá.")


# ── Lectura / clasificación ────────────────────────────────────────────────

def clasificar_estado(valor):
    v = (valor or "").strip().upper()
    if v == ESTADO_PENDIENTE:
        return ESTADO_PENDIENTE
    if v == ESTADO_EN_CURSO:
        return ESTADO_EN_CURSO
    if v == ESTADO_OK or v.startswith(ESTADO_OK + " "):
        return ESTADO_OK
    if v == ESTADO_SALTEADO or v.startswith(ESTADO_SALTEADO + " "):
        return ESTADO_SALTEADO
    if v.startswith(ESTADO_ERROR):
        return ESTADO_ERROR
    return "OTRO"


def _parse_fecha_hora(txt):
    try:
        return datetime.strptime((txt or "").strip(), FORMATO_FECHA_HORA)
    except ValueError:
        return None


def posiblemente_abandonado(fila, minutos, ahora=None):
    """Un pedido EN CURSO tomado hace más de N minutos."""
    ahora = ahora or datetime.now()
    if _en_curso(fila):
        t = _parse_fecha_hora(fila.get(C_TOMADO_EN))
        return t is None or (ahora - t).total_seconds() > minutos * 60
    return False


def _en_curso(fila):
    return ESTADO_EN_CURSO in (clasificar_estado(fila.get(C_EST_ALLOT)),
                               clasificar_estado(fila.get(C_EST_TARIFA)))


def estado_global(fila):
    """Un resumen por pedido: EN CURSO > ERROR > PENDIENTE > OK/SALTEADO."""
    est = [clasificar_estado(fila.get(C_EST_ALLOT)), clasificar_estado(fila.get(C_EST_TARIFA))]
    for prioridad in (ESTADO_EN_CURSO, ESTADO_ERROR, ESTADO_PENDIENTE):
        if prioridad in est:
            return prioridad
    if all(e in (ESTADO_OK, ESTADO_SALTEADO) for e in est):
        return ESTADO_OK
    return "OTRO"


def leer_cola(ws, minutos_abandono=30, ahora=None):
    """Lee COLA fresca y devuelve una lista de dicts listos para mostrar, más recientes primero."""
    from common.sheets_client import cargar_sheet
    filas, columnas = cargar_sheet(ws)
    if not columnas:
        raise ColaInvalida("La hoja COLA está vacía.")
    verificar_columnas(columnas)
    pedidos = []
    for f in filas:
        if not (f.get(C_ID) or "").strip():
            continue
        try:
            n_fechas = len(de_texto_normalizado(f.get(C_FECHAS)))
        except ValueError:
            n_fechas = None
        pedidos.append({
            "fila": f["__row_idx__"],
            "id": f.get(C_ID, ""),
            "cargado": f.get(C_FECHA_CARGA, ""),
            "cargado_por": f.get(C_CARGADO_POR, ""),
            "hotel_codigo": f.get(C_HOTEL_COD, ""),
            "allocations": f.get(C_ALLOCS, ""),
            "fechas": f.get(C_FECHAS, ""),
            "cant": f.get(C_CANT, "") or n_fechas,
            "modo": f.get(C_MODO, ""),
            "estado": estado_global(f),
            "est_allotment": f.get(C_EST_ALLOT, ""),
            "obs_allotment": f.get(C_OBS_ALLOT, ""),
            "est_tarifa": f.get(C_EST_TARIFA, ""),
            "obs_tarifa": f.get(C_OBS_TARIFA, ""),
            "tomado_por": f.get(C_TOMADO_POR, ""),
            "tomado_en": f.get(C_TOMADO_EN, ""),
            "abandonado": posiblemente_abandonado(f, minutos_abandono, ahora),
        })
    pedidos.reverse()
    return pedidos


# ── Toma de pedidos (varias PCs a la vez) ──────────────────────────────────

def _valores_fila(ws, row_idx, columnas):
    vals = ws.row_values(row_idx)
    vals += [""] * (len(columnas) - len(vals))
    return dict(zip(columnas, vals))


def tomar_pedido(ws, row_idx, quien, fases=("allotment", "tarifa"), espera=2.0, ahora=None, dormir=time.sleep):
    """Intenta tomar el pedido de la fila row_idx. Google Sheets no tiene escritura atómica, por eso:
      1) se relee la fila justo antes (debe seguir PENDIENTE y sin TOMADO_POR);
      2) se escribe TOMADO_POR/TOMADO_EN y las fases a ejecutar pasan a EN CURSO;
      3) se espera unos segundos y se RELEE: si TOMADO_POR sigue siendo uno mismo, es suyo;
         si no, se suelta (sin tocar nada más: la fila es de quien ganó).
    Devuelve True si el pedido quedó tomado."""
    from common.sheets_client import actualizar_fila_sheet
    columnas = ws.row_values(1)
    verificar_columnas(columnas)
    campos = {"allotment": C_EST_ALLOT, "tarifa": C_EST_TARIFA}
    antes = _valores_fila(ws, row_idx, columnas)
    if (antes.get(C_TOMADO_POR) or "").strip():
        return False
    if any(clasificar_estado(antes.get(campos[f])) != ESTADO_PENDIENTE for f in fases):
        return False
    ahora = ahora or datetime.now()
    escribir = {C_TOMADO_POR: quien, C_TOMADO_EN: ahora.strftime(FORMATO_FECHA_HORA)}
    escribir.update({campos[f]: ESTADO_EN_CURSO for f in fases})
    actualizar_fila_sheet(ws, row_idx, columnas, escribir)
    dormir(espera)
    despues = _valores_fila(ws, row_idx, columnas)
    return ((despues.get(C_TOMADO_POR) or "").strip() == quien
            and all(clasificar_estado(despues.get(campos[f])) == ESTADO_EN_CURSO for f in fases))


def escribir_fase(ws, row_idx, fase, estado, observaciones=None):
    """Escribe el estado (y opcionalmente las observaciones) de UNA fase de UNA fila."""
    from common.sheets_client import actualizar_fila_sheet
    columnas = ws.row_values(1)
    est, obs = (C_EST_ALLOT, C_OBS_ALLOT) if fase == "allotment" else (C_EST_TARIFA, C_OBS_TARIFA)
    valores = {est: estado}
    if observaciones is not None:
        valores[obs] = observaciones
    actualizar_fila_sheet(ws, row_idx, columnas, valores)


def formato_error(detalle):
    return f"{ESTADO_ERROR}: {detalle}"
