"""Proceso hijo que ejecuta los pedidos de la cola en Tourplan (la app lo lanza
con variables de entorno TOURPLAN_*, igual que en Drive-TP-NX-App).

ETAPA 2: SOLO MODO LECTURA. No escribe nada en Tourplan, no cambia ESTADO ni toma
el pedido: lee la allocation y deja en OBSERVACIONES_CIERRE_ALLOTMENT el plan
(qué cerraría, qué saltearía y por qué). Las tarifas (Rates) todavía no se evalúan.
"""
import os
import sys
import time
import traceback
from datetime import date, datetime

from allocation import cola, plan, registro
from allocation.constantes import (
    ESTADO_PENDIENTE, HOJA_ALLOCATIONS, HOJA_COLA, MODO_LECTURA,
)
from allocation.fechas import de_texto_normalizado
from common.abort import ABORT_EXIT_CODE, AbortadoPorUsuario, chequear_abort
from common.sheets_client import actualizar_fila_sheet, cargar_sheet, conectar_sheets

MODO = os.environ.get("TOURPLAN_MODO", MODO_LECTURA)
SHEET_URL = os.environ.get("TOURPLAN_SHEET_URL", "")
CREDENTIALS_PATH = os.environ.get("TOURPLAN_CREDENTIALS_PATH", "")
TOKEN_PATH = os.environ.get("TOURPLAN_TOKEN_PATH", "")


def procesar_pedido_lectura(driver, fila, allocs_registro, hoy):
    """Devuelve el texto de OBSERVACIONES_CIERRE_ALLOTMENT de un pedido."""
    from common import tourplan as tp
    from tourplan_flujos import allocations as fl

    codigo_hotel = (fila.get(cola.C_HOTEL_COD) or "").strip()
    del_hotel = [a for a in allocs_registro if a.codigo_hotel.upper() == codigo_hotel.upper()]
    if not del_hotel:
        return f"ERROR: el hotel {codigo_hotel!r} no figura en el registro."
    elegidas, faltantes = registro.resolver_allocations(fila.get(cola.C_ALLOCS), del_hotel)
    todas_fechas = de_texto_normalizado(fila.get(cola.C_FECHAS))
    fechas = [f for f in todas_fechas if f >= hoy]
    lineas = []
    if len(fechas) < len(todas_fechas):
        lineas.append(f"{len(todas_fechas) - len(fechas)} fecha(s) ya pasada(s): no se consideran")
    if faltantes:
        lineas.append(f"Allocation(es) no encontrada(s) en el registro: {faltantes}")
    if not elegidas or not fechas:
        return " | ".join(lineas + ["nada para leer"])

    fl.preparar_hotel(driver, codigo_hotel, hoy)
    for a in elegidas:
        chequear_abort()
        try:
            dias, obs = fl.leer_allocation(driver, a, codigo_hotel, fechas)
            if dias is None:
                lineas.append(f"{a.codigo}: allocation vacía, no hay nada que cerrar en allocation (SALTEADO)")
            else:
                lineas.append(plan.resumen(a.codigo, plan.planear(dias, fechas), lectura=True)
                              + (f" ({obs})" if obs else ""))
        except fl.FlujoError as e:
            tp.ss(driver, f"error_{a.codigo}")
            lineas.append(f"{a.codigo}: NO SE ESCRIBIRÍA NADA — {e}")
    return " | ".join(lineas)


def main():
    if MODO != MODO_LECTURA:
        print(f"⛔ Modo {MODO!r}: en esta etapa solo existe el modo lectura. No se hizo nada.")
        sys.exit(2)
    if not SHEET_URL:
        raise ValueError("No se indicó la URL del Google Sheet (TOURPLAN_SHEET_URL).")

    from common import tourplan as tp
    hoy = date.today()
    print("=" * 70)
    print(f"  Lectura de plan de cierre · entorno {tp.BASE_URL}")
    print("  Modo LECTURA: no se escribe nada en Tourplan ni se cambia el ESTADO.")
    print("=" * 70)

    allocs, _ = registro.cargar_registro(
        conectar_sheets(SHEET_URL, HOJA_ALLOCATIONS, CREDENTIALS_PATH, TOKEN_PATH))
    ws = conectar_sheets(SHEET_URL, HOJA_COLA, CREDENTIALS_PATH, TOKEN_PATH)
    filas, columnas = cargar_sheet(ws)
    cola.verificar_columnas(columnas)
    pendientes = [f for f in filas if (f.get(cola.C_ID) or "").strip()
                  and cola.clasificar_estado(f.get(cola.C_EST_ALLOT)) == ESTADO_PENDIENTE]
    print(f"Pedidos con allotment PENDIENTE: {len(pendientes)}")
    if not pendientes:
        return

    t0 = time.time()
    driver = tp.crear_driver()
    abortado = False
    try:
        tp.login(driver)
        for fila in pendientes:
            chequear_abort()
            print(f"\n{'─' * 70}\nPedido {fila[cola.C_ID]} (fila {fila['__row_idx__']}): "
                  f"{fila.get(cola.C_HOTEL_COD)} · {fila.get(cola.C_ALLOCS)} · {fila.get(cola.C_FECHAS)}")
            try:
                obs = procesar_pedido_lectura(driver, fila, allocs, hoy)
            except AbortadoPorUsuario:
                raise
            except Exception as e:
                tp.ss(driver, "error_pedido")
                obs = f"ERROR: {e}"
                traceback.print_exc()
            texto = f"[LECTURA {datetime.now():%d/%m %H:%M}] {obs}"
            print(f"  → {texto}")
            actualizar_fila_sheet(ws, fila["__row_idx__"], columnas, {cola.C_OBS_ALLOT: texto})
    except AbortadoPorUsuario:
        abortado = True
        print("\n⏸️  Corrida abortada por el usuario.")
    finally:
        tp.logout(driver)
        driver.quit()
        m, s = divmod(int(time.time() - t0), 60)
        print(f"\n🏁 Fin. Duración: {m}m {s:02d}s")
    if abortado:
        sys.exit(ABORT_EXIT_CODE)


if __name__ == "__main__":
    main()
