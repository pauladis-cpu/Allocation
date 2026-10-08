"""Proceso hijo que ejecuta los pedidos de la cola en Tourplan (lo lanza la app con variables
de entorno TOURPLAN_*, igual que en Drive-TP-NX-App).

El MODO sale de cada fila de la cola:
  - lectura: no escribe nada en Tourplan, no toma el pedido ni cambia ningún ESTADO. Deja el plan
    (qué cerraría, qué saltearía y por qué) en OBSERVACIONES_CIERRE_ALLOTMENT / _TARIFA.
  - aplicar: toma el pedido (EN CURSO / TOMADO_POR / TOMADO_EN, con relectura para varias PCs),
    cierra las fechas en la allocation y después las tarifas, y deja OK / SALTEADO / NO APLICA / ERROR por fase.

Todo es resumible e idempotente: solo se ejecutan las fases PENDIENTE; volver a correr un pedido
terminado no cambia nada. Un error en un pedido no frena el lote. Nunca se reabre una fecha.

PRODUCCIÓN: el modo aplicar se niega a escribir en Producción salvo que la app lo habilite
explícitamente (TOURPLAN_PERMITIR_PRODUCCION=1).

Variables de entorno opcionales:
  TOURPLAN_SOLO_PEDIDO  ID_PEDIDO: procesa solo ese pedido ("Enviar y ejecutar").
  TOURPLAN_QUIEN        nombre que se escribe en TOMADO_POR.
  TOURPLAN_MODO=lectura fuerza lectura para todas las filas.
  TOURPLAN_LOG_DIR      carpeta donde se guarda el log de cada ejecución (por defecto ~/.tourplan-allocation/logs).

Cada línea del log (pantalla y archivo) lleva la hora [HH:MM:SS]; se conservan los últimos LOGS_A_CONSERVAR archivos.
"""
import os
import re
import sys
import time
import traceback
from datetime import date, datetime

from allocation import cola, plan, rates_plan, registro
from allocation.constantes import (
    ALLOCATIONS_TODAS, EXCLUDED_OPTIONS, HOJA_ALLOCATIONS, HOJA_COLA, MODO_APLICAR, MODO_LECTURA,
    URL_PRODUCCION,
)
from allocation.fechas import agrupar_rangos, de_texto_normalizado
from common.abort import ABORT_EXIT_CODE, AbortadoPorUsuario, chequear_abort
from common.sheets_client import actualizar_fila_sheet, cargar_sheet, conectar_sheets

SHEET_URL = os.environ.get("TOURPLAN_SHEET_URL", "")
CREDENTIALS_PATH = os.environ.get("TOURPLAN_CREDENTIALS_PATH", "")
TOKEN_PATH = os.environ.get("TOURPLAN_TOKEN_PATH", "")
SOLO_PEDIDO = os.environ.get("TOURPLAN_SOLO_PEDIDO", "").strip()
QUIEN = os.environ.get("TOURPLAN_QUIEN", "").strip() or "app"
FORZAR_LECTURA = os.environ.get("TOURPLAN_MODO", "") == MODO_LECTURA
PERMITIR_PRODUCCION = os.environ.get("TOURPLAN_PERMITIR_PRODUCCION", "") == "1"

ALLOT, TARIFA = "allotment", "tarifa"

LOG_DIR = os.environ.get("TOURPLAN_LOG_DIR", "").strip() or os.path.join(
    os.path.expanduser("~"), ".tourplan-allocation", "logs")
LOGS_A_CONSERVAR = 30


class _LogConHora:
    """Envuelve stdout/stderr: antepone la hora a cada línea y la copia también a un archivo."""

    def __init__(self, destino, archivo):
        self._destino, self._archivo, self._resto = destino, archivo, ""

    def write(self, texto):
        self._resto += texto
        while "\n" in self._resto:
            linea, self._resto = self._resto.split("\n", 1)
            self._emitir(linea)
        return len(texto)

    def _emitir(self, linea):
        salida = f"[{datetime.now():%H:%M:%S}] {linea}" if linea.strip() else ""
        for d in (self._destino, self._archivo):
            try:
                d.write(salida + "\n")
                d.flush()
            except Exception:
                pass            # un problema con el log nunca debe frenar la ejecución

    def flush(self):
        for d in (self._destino, self._archivo):
            try:
                d.flush()
            except Exception:
                pass

    def cerrar(self):
        if self._resto.strip():
            self._emitir(self._resto)
        self._resto = ""
        try:
            self._archivo.close()
        except Exception:
            pass

    def __getattr__(self, nombre):
        return getattr(self._destino, nombre)


def activar_log_a_archivo(ahora=None, directorio=None):
    """Redirige stdout y stderr a una versión con hora que además se guarda en un archivo del directorio de logs.
    Devuelve (tee, ruta) o (None, None) si no se pudo crear el archivo (la ejecución sigue igual)."""
    directorio = directorio or LOG_DIR
    ahora = ahora or datetime.now()
    try:
        os.makedirs(directorio, exist_ok=True)
        ruta = os.path.join(directorio, f"ejecucion_{ahora:%Y%m%d_%H%M%S}.log")
        archivo = open(ruta, "w", encoding="utf-8")
        viejos = sorted(f for f in os.listdir(directorio) if f.startswith("ejecucion_") and f.endswith(".log"))
        for f in viejos[:-LOGS_A_CONSERVAR]:
            try:
                os.remove(os.path.join(directorio, f))
            except OSError:
                pass
    except OSError:
        return None, None
    tee = _LogConHora(sys.stdout, archivo)
    sys.stdout = tee
    sys.stderr = tee            # el traceback también queda en el archivo (la app ya junta stderr con stdout)
    return tee, ruta


def log(msg):
    print(msg, flush=True)


class PedidoError(Exception):
    """El pedido no se puede procesar tal como está cargado (se informa, no se escribe nada)."""


# ── Armado del pedido ──────────────────────────────────────────────────────

def resolver_pedido(fila, allocs_registro, hoy):
    """(codigo_hotel, allocations elegidas, fechas vigentes, avisos). Levanta PedidoError."""
    codigo_hotel = (fila.get(cola.C_HOTEL_COD) or "").strip()
    del_hotel = [a for a in allocs_registro if a.codigo_hotel.upper() == codigo_hotel.upper()]
    if not del_hotel:
        raise PedidoError(f"el hotel {codigo_hotel!r} no figura en el registro.")
    elegidas, faltantes = registro.resolver_allocations(fila.get(cola.C_ALLOCS), del_hotel)
    if faltantes:
        raise PedidoError(f"allocation(es) no encontrada(s) en el registro: {faltantes}")
    if not elegidas:
        raise PedidoError("el pedido no indica ninguna allocation.")
    try:
        todas = de_texto_normalizado(fila.get(cola.C_FECHAS))
    except ValueError as e:
        raise PedidoError(f"fechas ilegibles: {e}")
    fechas = [f for f in todas if f >= hoy]
    avisos = []
    if len(fechas) < len(todas):
        avisos.append(f"{len(todas) - len(fechas)} fecha(s) ya pasada(s): no se consideran")
    if not fechas:
        raise PedidoError("no quedan fechas vigentes para cerrar.")
    return codigo_hotel, elegidas, fechas, avisos


def validar_habitacion(cod, codigo_hotel):
    """Nunca se cierran 600HTL ni ROOMS, y solo service type HT. Si el Sheet lo pidiera, se frena."""
    cod = cod.replace(" ", "").upper()
    i = cod.find(codigo_hotel.upper())
    if i < 2 or cod[i - 2:i] != "HT":
        raise PedidoError(f"la habitación {cod} no es service type HT: no se cierra.")
    if cod[i + len(codigo_hotel):] in EXCLUDED_OPTIONS:
        raise PedidoError(f"la habitación {cod} está excluida ({', '.join(sorted(EXCLUDED_OPTIONS))}): no se cierra.")
    return cod


# ── Fase 1: allocation ─────────────────────────────────────────────────────

def fase_allotment(driver, codigo_hotel, elegidas, fechas, aplicar, hoy):
    """Devuelve (estado, observaciones). El estado solo se escribe en modo aplicar."""
    from common import tourplan as tp
    from tourplan_flujos import allocations as fl
    lineas, errores = [], []
    cerrar = sin_fila = reales = 0
    log(f"  ▶ Fase allocation · {len(elegidas)} allocation(es) · {len(fechas)} fecha(s) · "
        f"{'APLICAR' if aplicar else 'lectura'}")
    try:
        fl.preparar_hotel(driver, codigo_hotel, hoy)
    except fl.FlujoError as e:
        log(f"    ✖ no se pudo abrir el hotel {codigo_hotel}: {e}")
        return cola.formato_error(str(e)), ""
    for a in elegidas:
        chequear_abort()
        log(f"    · allocation {a.codigo} ({a.descripcion})")
        try:
            acciones, obs = fl.cerrar_allocation(driver, a, codigo_hotel, fechas, aplicar=aplicar, hoy=hoy)
        except fl.FlujoError as e:
            tp.ss(driver, f"error_{a.codigo}")
            errores.append(f"{a.codigo}: {e}")
            log(f"    ✖ {a.codigo}: {e}")
            continue
        if acciones is None:
            lineas.append(f"{a.codigo}: allocation vacía, nada que cerrar en allocation")
            log(f"    ○ {a.codigo}: allocation vacía")
            continue
        reales += 1
        cerrar += sum(1 for x in acciones if x.tipo == plan.CERRAR)
        sin_fila += sum(1 for x in acciones if x.tipo == plan.SIN_FILA)
        lineas.append(plan.resumen(a.codigo, acciones, lectura=not aplicar) + (f" ({obs})" if obs else ""))
        log(f"    ✔ {lineas[-1]}")
    texto = " | ".join(lineas)
    if errores:
        return cola.formato_error(" | ".join(errores)), texto
    if reales == 0:
        return cola.ESTADO_SALTEADO, texto or "allocation vacía"
    if cerrar == 0 and sin_fila == 0:
        return cola.ESTADO_SALTEADO, "ya estaba todo cerrado · " + texto
    return cola.ESTADO_OK, texto


# ── Fase 2: tarifas ────────────────────────────────────────────────────────

def codigos_de(texto):
    """Códigos largos de una celda, separados por coma, punto y coma o salto de línea."""
    return [c.strip().replace(" ", "").upper() for c in re.split(r"[,;\n]+", texto or "") if c.strip()]


def habitaciones_a_cerrar(driver, codigo_hotel, elegidas):
    """None si ninguna allocation del pedido cierra tarifa; si no, la lista (sin repetir) de
    habitaciones: LINKEADA, TODAS (se lee de Tourplan) o la lista de códigos del registro."""
    from tourplan_flujos import rates as rt
    con = [a for a in elegidas if a.cierra_tarifa]
    if not con:
        return None
    por_definir = [a.codigo for a in con if a.tarifas.strip().upper() in ("REVISAR", "")]
    if por_definir:
        raise PedidoError(f"alcance de tarifas por definir (REVISAR) en: {', '.join(por_definir)}")
    sin_habitaciones = [a.codigo for a in con if a.tarifas.strip().upper() == "OTRO" and not codigos_de(a.habitaciones_a_cerrar)]
    if sin_habitaciones:
        raise PedidoError("Tarifas a cerrar = OTRO pero la columna «Habitaciones a cerrar» está vacía en: "
                          + ", ".join(sin_habitaciones))
    habs, usa_todas = [], False
    for a in con:
        t = a.tarifas.strip().upper()
        if t == "LINKEADA":
            h = a.habitacion.replace(" ", "").upper()
            if not h or h == "MULTIPLEOPTIONS":
                raise PedidoError(f"{a.codigo}: tarifa LINKEADA pero la habitación linkeada es {a.habitacion!r}.")
            habs.append(h)
        elif t == "TODAS":
            usa_todas = True
        elif t == "OTRO":
            habs += codigos_de(a.habitaciones_a_cerrar)          # códigos de la columna «Habitaciones a cerrar»
        else:
            habs += codigos_de(a.tarifas)                        # lista de códigos directamente en «Tarifas a cerrar»
    if usa_todas:
        habs += rt.listar_habitaciones_ht(driver, codigo_hotel)
    return [validar_habitacion(h, codigo_hotel) for h in dict.fromkeys(habs)]


def es_hg(a):
    """Allocation de descripción «HG - …»: sus tarifas se cierran solo mientras la allocation está vigente."""
    return re.match(r"^HG(?![A-Z0-9])", (a.descripcion or "").strip().upper()) is not None


def fechas_de_tarifa(a, fechas):
    """Fechas en que esta allocation pide cerrar tarifas: las HG, solo hasta «Vigente hasta» (inclusive);
    el resto, todas las indicadas."""
    if not es_hg(a):
        return list(fechas)
    if not a.vigente_hasta:
        raise PedidoError(f"{a.codigo}: la descripción empieza con HG pero «Vigente hasta» no tiene una fecha válida "
                          f"({a.vigente_hasta_txt!r}): no se sabe hasta cuándo cerrar tarifas.")
    return [f for f in fechas if f <= a.vigente_hasta]


def fechas_por_habitacion(habs, elegidas, fechas):
    """{habitación: fechas}. Una habitación pedida por varias allocations toma la unión de sus fechas
    (si alguna no es HG, son todas)."""
    con = [a for a in elegidas if a.cierra_tarifa]
    out = {}
    for h in habs:
        propias = set()
        for a in con:
            t = a.tarifas.strip().upper()
            if t == "LINKEADA":
                pide = a.habitacion.replace(" ", "").upper() == h
            elif t == "TODAS":
                pide = True
            elif t == "OTRO":
                pide = h in codigos_de(a.habitaciones_a_cerrar)
            else:
                pide = h in codigos_de(a.tarifas)
            if pide:
                propias.update(fechas_de_tarifa(a, fechas))
        out[h] = sorted(propias)
    return out


def fase_tarifa(driver, codigo_hotel, elegidas, fechas, aplicar):
    """Devuelve (estado, observaciones)."""
    from common import tourplan as tp
    from tourplan_flujos import allocations as fl
    from tourplan_flujos import rates as rt
    log(f"  ▶ Fase tarifa · {'APLICAR' if aplicar else 'lectura'}")
    try:
        habs = habitaciones_a_cerrar(driver, codigo_hotel, elegidas)
    except (PedidoError, fl.FlujoError) as e:
        log(f"    ✖ no se pudo definir qué habitaciones cerrar: {e}")
        return cola.formato_error(str(e)), ""
    if habs is None:
        log("    ○ ninguna allocation del pedido cierra tarifa")
        return cola.ESTADO_NO_APLICA, "no cierra tarifa"
    log(f"    habitaciones a cerrar ({len(habs)}): {', '.join(habs)}")
    try:
        fechas_hab = fechas_por_habitacion(habs, elegidas, fechas)
    except PedidoError as e:
        log(f"    ✖ {e}")
        return cola.formato_error(str(e)), ""
    lineas, errores, trabajo = [], [], 0
    for h in habs:
        chequear_abort()
        log(f"    · habitación {h}")
        if not fechas_hab[h]:
            lineas.append(f"{h}: ninguna fecha dentro de la vigencia (HG): no se cierran tarifas")
            log(f"    ○ {lineas[-1]}")
            continue
        if len(fechas_hab[h]) < len(fechas):
            log(f"    ℹ allocation HG: tarifas solo hasta la vigencia ({len(fechas_hab[h])} de {len(fechas)} fecha(s))")
        rangos = agrupar_rangos(fechas_hab[h])
        try:
            _, texto, n = rt.procesar_habitacion(driver, codigo_hotel, h, rangos, aplicar=aplicar)
        except (fl.FlujoError, rates_plan.PlanRatesError) as e:
            tp.ss(driver, f"error_{h}")
            errores.append(f"{h}: {e}")
            log(f"    ✖ {h}: {e}")
            continue
        lineas.append(texto)
        log(f"    ✔ {texto}")
        trabajo += n
    texto = " | ".join(lineas)
    if errores:
        return cola.formato_error(" | ".join(errores)), texto
    if trabajo == 0:
        return cola.ESTADO_SALTEADO, "ya estaba todo cerrado · " + texto
    return cola.ESTADO_OK, texto


# ── Un pedido ──────────────────────────────────────────────────────────────

def ejecutar_pedido(driver, ws, fila, allocs_registro, hoy, aplicar):
    """Ejecuta las fases PENDIENTE de un pedido. En aplicar el pedido ya está tomado (EN CURSO)."""
    row = fila["__row_idx__"]
    fases = [f for f, col in ((ALLOT, cola.C_EST_ALLOT), (TARIFA, cola.C_EST_TARIFA))
             if cola.clasificar_estado(fila.get(col)) == cola.ESTADO_PENDIENTE]
    sello = f"[LECTURA {datetime.now():%d/%m %H:%M}] "
    en_curso = set(fases) if aplicar else set()

    def cerrar_fase(fase, estado, obs):
        if aplicar and estado.startswith(cola.ESTADO_ERROR):
            accion = cola.sugerencia(estado)
            log(f"  ▸ {accion}")
            obs = f"{obs} ▸ {accion}" if obs else accion
        log(f"  ■ Fase {fase}: {estado or '(lectura: solo observaciones)'}"
            + (f" — {obs[:500]}" if obs else ""))
        if aplicar:
            cola.escribir_fase(ws, row, fase, estado, obs)
            en_curso.discard(fase)
        else:
            col = cola.C_OBS_ALLOT if fase == ALLOT else cola.C_OBS_TARIFA
            actualizar_fila_sheet(ws, row, ws.row_values(1), {col: sello + obs})

    try:
        try:
            codigo_hotel, elegidas, fechas, avisos = resolver_pedido(fila, allocs_registro, hoy)
        except PedidoError as e:
            log(f"  ✖ pedido inválido: {e}")
            for f in fases:
                cerrar_fase(f, cola.formato_error(str(e)), str(e))
            return
        prefijo = (" | ".join(avisos) + " | ") if avisos else ""
        resultado_allot = None
        if ALLOT in fases:
            estado, obs = fase_allotment(driver, codigo_hotel, elegidas, fechas, aplicar, hoy)
            resultado_allot = estado
            cerrar_fase(ALLOT, estado, prefijo + (obs if aplicar or not estado.startswith(cola.ESTADO_ERROR)
                                                  else f"{estado} | {obs}"))
        if TARIFA in fases:
            if resultado_allot and resultado_allot.startswith(cola.ESTADO_ERROR) and aplicar:
                # no se avanza a tarifas si falló allotment: queda PENDIENTE para retomar
                log("  ■ Fase tarifa: no se evalúa porque falló la fase de allocation (queda PENDIENTE)")
                cola.escribir_fase(ws, row, TARIFA, cola.ESTADO_PENDIENTE, "no se evaluó: falló la fase de allocation")
                en_curso.discard(TARIFA)
            else:
                estado, obs = fase_tarifa(driver, codigo_hotel, elegidas, fechas, aplicar)
                cerrar_fase(TARIFA, estado, prefijo + (obs if aplicar or not estado.startswith(cola.ESTADO_ERROR)
                                                       else f"{estado} | {obs}"))
    except AbortadoPorUsuario:
        for f in sorted(en_curso):                               # lo que quedó EN CURSO vuelve a PENDIENTE
            cola.escribir_fase(ws, row, f, cola.ESTADO_PENDIENTE, "abortado por el usuario: se puede retomar")
        raise
    except Exception as e:
        log(f"  ✖ error inesperado: {e}")
        traceback.print_exc()
        for f in sorted(en_curso):
            cola.escribir_fase(ws, row, f, cola.formato_error(str(e)), "")
        if not aplicar:
            for f in fases:
                cerrar_fase(f, "", f"ERROR: {e}")


# ── Programa principal ─────────────────────────────────────────────────────

def _es_produccion(url):
    return url.rstrip("/").lower() == URL_PRODUCCION.rstrip("/").lower()


def seleccionar_pedidos(filas):
    """Pedidos a procesar: con alguna fase PENDIENTE (y, si se pidió uno solo, ese)."""
    out = []
    for f in filas:
        if not (f.get(cola.C_ID) or "").strip():
            continue
        if SOLO_PEDIDO and f[cola.C_ID].strip() != SOLO_PEDIDO:
            continue
        if cola.ESTADO_PENDIENTE in (cola.clasificar_estado(f.get(cola.C_EST_ALLOT)),
                                     cola.clasificar_estado(f.get(cola.C_EST_TARIFA))):
            out.append(f)
    return out


def modo_de(fila):
    if FORZAR_LECTURA:
        return MODO_LECTURA
    return MODO_APLICAR if (fila.get(cola.C_MODO) or "").strip().lower() == MODO_APLICAR else MODO_LECTURA


def main():
    if not SHEET_URL:
        raise ValueError("No se indicó la URL del Google Sheet (TOURPLAN_SHEET_URL).")
    from common import tourplan as tp
    hoy = date.today()
    produccion = _es_produccion(tp.BASE_URL)
    print("=" * 70)
    print(f"  Ejecución de pedidos · {tp.BASE_URL}{'  (PRODUCCIÓN)' if produccion else '  (Test)'}")
    print("=" * 70)

    allocs, _ = registro.cargar_registro(conectar_sheets(SHEET_URL, HOJA_ALLOCATIONS, CREDENTIALS_PATH, TOKEN_PATH))
    ws = conectar_sheets(SHEET_URL, HOJA_COLA, CREDENTIALS_PATH, TOKEN_PATH)
    filas, columnas = cargar_sheet(ws)
    cola.verificar_columnas(columnas)
    pedidos = seleccionar_pedidos(filas)
    if produccion and not PERMITIR_PRODUCCION:
        bloqueados = [f for f in pedidos if modo_de(f) == MODO_APLICAR]
        for f in bloqueados:
            print(f"⛔ {f[cola.C_ID]}: modo aplicar en PRODUCCIÓN sin habilitación explícita: no se toca.")
        pedidos = [f for f in pedidos if f not in bloqueados]
    print(f"Pedidos a procesar: {len(pedidos)}")
    if not pedidos:
        return

    t0 = time.time()
    driver = tp.crear_driver()
    abortado = False
    try:
        tp.login(driver)
        for fila in pedidos:
            chequear_abort()
            aplicar = modo_de(fila) == MODO_APLICAR
            print(f"\n{'─' * 70}\nPedido {fila[cola.C_ID]} (fila {fila['__row_idx__']}) · {modo_de(fila)} · "
                  f"{fila.get(cola.C_HOTEL_COD)} · {fila.get(cola.C_ALLOCS)} · {fila.get(cola.C_FECHAS)}")
            if aplicar:
                fases = tuple(f for f, col in ((ALLOT, cola.C_EST_ALLOT), (TARIFA, cola.C_EST_TARIFA))
                              if cola.clasificar_estado(fila.get(col)) == cola.ESTADO_PENDIENTE)
                if not cola.tomar_pedido(ws, fila["__row_idx__"], QUIEN, fases=fases):
                    print("  ↪ lo tiene otra PC (o ya no está pendiente): se salta.")
                    continue
            ejecutar_pedido(driver, ws, fila, allocs, hoy, aplicar)
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
    _tee, _ruta_log = activar_log_a_archivo()
    if _ruta_log:
        print(f"📝 Log de esta ejecución: {_ruta_log}")
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()       # antes de cerrar el archivo, para que el error también quede en el log
        sys.exit(1)
    finally:
        if _tee:
            _tee.cerrar()
