"""Flujo Selenium de Allocations (spec sección 5) — ETAPA 2: SOLO LECTURA.

Este módulo no tiene ninguna función que escriba Max/Release ni que haga Save:
solo navega, filtra, abre la allocation, verifica y lee los días. Lo único que
se "escribe" en pantalla es la fecha "hasta" del filtro de la grilla.

Convenciones (sección 8): selectores por clases de componente, tpid y texto
visible; nunca _ngcontent-*, ids con GUID ni nth-of-type; los botones se eligen
dentro del diálogo activo (el último body > tp-dialog); las filas de la grilla
virtual se releen por su etiqueta de fecha, nunca por índice ni referencia.
"""

import re
import time
from datetime import date, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from allocation.constantes import WINDOW_YEARS
from allocation.plan import DiaAllocation
from common import tourplan as tp

ALTO_FILA = 35  # px por fila de la grilla de días
SEL_DIALOGO = "body > tp-dialog"

# JS: último diálogo abierto (el activo). Todo selector va acotado a él.
_JS_DLG = "var dlg = Array.from(document.querySelectorAll('body > tp-dialog')).pop(); if (!dlg) return null;"


class FlujoError(Exception):
    """Algo no coincide o no se pudo leer: se frena y se informa (no se escribe nada)."""


def _norm(txt):
    return " ".join(str(txt or "").split()).casefold()


def _esperar(driver, condicion, timeout=15, intervalo=0.4):
    """Poll hasta que condicion() sea verdadero; devuelve su valor o None."""
    fin = time.time() + timeout * tp.VELOCIDAD
    while time.time() < fin:
        valor = condicion()
        if valor:
            return valor
        time.sleep(intervalo)
    return None


def _fecha_tp(txt):
    """'05/Oct/2026' -> date (por valor, nunca por texto). None si no se entiende."""
    dt = tp.parsear_fecha(txt)
    return dt.date() if dt else None


# ── Pasos 1-2: hotel (supplier) ─────────────────────────────────────────────

def abrir_supplier(driver, codigo_hotel):
    """Navega #/home -> #/product y elige el supplier por coincidencia EXACTA de td.code.
    Nunca Enter ni Tab (aceptan la primera sugerencia)."""
    codigo = codigo_hotel.strip()
    driver.get(f"{tp.BASE_URL}/#/home")
    time.sleep(2 * tp.VELOCIDAD)
    driver.get(f"{tp.BASE_URL}/#/product")
    time.sleep(4 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)

    inp = tp.wait(driver, "#searchSupplier input")
    inp.click()
    tp.set_val(driver, inp, codigo)

    def filas_coinciden():
        filas = driver.execute_script("""
            return Array.from(document.querySelectorAll('#searchSupplier .tpcombo table tbody tr'))
                .map(function(tr){ var c = tr.querySelector('td.code');
                                   return c ? c.textContent.trim() : null; });
        """)
        return filas if filas else None

    codes = _esperar(driver, filas_coinciden, timeout=10)
    if not codes:
        raise FlujoError(f"El supplier {codigo!r} no devolvió resultados en Tourplan.")
    exactas = [i for i, c in enumerate(codes) if c and c.upper() == codigo.upper()]
    if len(exactas) != 1:
        raise FlujoError(
            f"Supplier {codigo!r}: {len(exactas)} coincidencias exactas (sugerencias: {codes[:8]}).")
    clic = driver.execute_script("""
        var tr = document.querySelectorAll('#searchSupplier .tpcombo table tbody tr')[arguments[0]];
        var c = tr && tr.querySelector('td.code');
        if (!c || c.textContent.trim().toUpperCase() !== arguments[1].toUpperCase()) return false;
        tr.click(); return true;
    """, exactas[0], codigo)
    if not clic:
        raise FlujoError(f"La lista de sugerencias cambió antes de elegir {codigo!r}.")
    time.sleep(1.5 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)

    valor = driver.execute_script(
        "var i = document.querySelector('#searchSupplier input'); return i ? i.value : '';")
    if not valor.strip().upper().startswith(codigo.upper()):
        raise FlujoError(f"El campo Supplier quedó en {valor!r}, se esperaba que empiece con {codigo!r}.")


# ── Paso 3: menú -> Allocations ─────────────────────────────────────────────

def abrir_menu_allocations(driver):
    """Hamburguesa -> ítem 'Allocations' elegido por TEXTO (no por posición)."""
    img = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "nav img")))
    tp.jc(driver, img)
    tp.wait(driver, ".nav-menu")
    time.sleep(1.5 * tp.VELOCIDAD)
    res = driver.execute_script("""
        var labels = Array.from(document.querySelectorAll('.nav-menu li label'));
        var el = labels.find(function(l){ return l.innerText.trim().toLowerCase() === 'allocations'; });
        if (!el) return {ok: false, items: labels.map(function(l){ return l.innerText.trim(); })};
        el.click(); return {ok: true};
    """)
    if not res["ok"]:
        raise FlujoError(f"No encontré el ítem 'Allocations' en el menú. Ítems: {res['items']}")
    time.sleep(2 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)
    tp.cerrar_nav_backdrop(driver, velocidad=tp.VELOCIDAD)


# ── Paso 4: filtro ──────────────────────────────────────────────────────────

_GRUPO_FILTRO = "tp-supplier-allocations tp-group.tpgroup-allocationsfilter"


def filtrar_hasta(driver, hoy):
    """Abre el filtro, pone 'hasta' = hoy + 2 años (verificando el valor real que entendió
    Tourplan), deja Show Archived sin tildar y filtra."""
    grupo = tp.wait(driver, _GRUPO_FILTRO)
    if "tpcollapsed" in (grupo.get_attribute("class") or ""):
        tp.jc(driver, grupo.find_element(By.CSS_SELECTOR, ".legend i"))  # es un interruptor
        if not _esperar(driver, lambda: "tpexpanded" in (grupo.get_attribute("class") or ""), timeout=5):
            raise FlujoError("No pude abrir el filtro de Allocations.")

    try:
        hasta = hoy.replace(year=hoy.year + WINDOW_YEARS)
    except ValueError:
        hasta = hoy.replace(year=hoy.year + WINDOW_YEARS, day=28)
    inp = grupo.find_element(By.CSS_SELECTOR, "input.tpdate-dateto")
    tp.set_val_con_blur(driver, inp, f"{hasta.day:02d}/{hasta.month:02d}/{hasta.year % 100:02d}")
    time.sleep(0.8 * tp.VELOCIDAD)
    oculto = driver.execute_script("""
        var el = arguments[0];
        for (var i = 0; i < 4 && el; i++, el = el.parentElement) {
            var h = el.querySelector('input.tphidden'); if (h) return h.value;
        }
        return null;
    """, inp)
    if _fecha_tp(oculto) != hasta:
        raise FlujoError(f"Tourplan entendió la fecha 'hasta' como {oculto!r}, se esperaba {hasta:%d/%m/%Y}.")

    tildado = driver.execute_script("var c = document.querySelector('#deleted'); return c ? c.checked : null;")
    if tildado:
        raise FlujoError("'Show Archived' está tildado: no se toca, destildalo a mano y reintentá.")

    boton = grupo.find_elements(By.CSS_SELECTOR, "tp-button.filter button") or \
        driver.find_elements(By.CSS_SELECTOR, "tp-button.filter button")
    if not boton:
        raise FlujoError("No encontré el botón Filter.")
    tp.jc(driver, boton[0])
    time.sleep(1.5 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)


# ── Pasos 5-6: elegir la allocation y verificar el diálogo ──────────────────

def abrir_allocation(driver, codigo, descripcion):
    """Clic en la fila cuyo Name y Description coinciden EXACTO con el registro
    (recortando y normalizando espacios, sin distinguir mayúsculas). 0 o >1 = error."""
    cantidad = driver.execute_script("""
        var nombre = arguments[0], desc = arguments[1];
        var norm = function(s){ return (s || '').replace(/\\s+/g, ' ').trim().toLowerCase(); };
        var filas = Array.from(document.querySelectorAll('tp-grid[tpid="allocations-grid"] tbody tr'));
        var ok = filas.filter(function(tr){
            var n = tr.querySelector('td.tpcol-name'), d = tr.querySelector('td.tpcol-description');
            return n && d && norm(n.textContent) === nombre && norm(d.textContent) === desc;
        });
        if (ok.length === 1) { ok[0].querySelector('td.tpcol-description').click(); }
        return ok.length;
    """, _norm(codigo), _norm(descripcion))
    if cantidad != 1:
        raise FlujoError(
            f"Allocation {codigo!r} / {descripcion!r}: {cantidad} coincidencias exactas en la grilla.")
    if not _esperar(driver, lambda: driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO), timeout=15):
        raise FlujoError("No se abrió el diálogo de la allocation.")
    time.sleep(1.5 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)

    titulo = driver.execute_script(_JS_DLG + """
        var h = dlg.querySelector('.tpmodal-allocation h3'); return h ? h.textContent : null;""")
    if _norm(titulo) != _norm(f"Allocation Detail - {codigo}"):
        cerrar_dialogo(driver)
        raise FlujoError(f"El título del diálogo es {titulo!r}, se esperaba 'Allocation Detail - {codigo}'.")


# ── Paso 7-8: habitación linkeada / allocation vacía ────────────────────────

def leer_habitaciones(driver, codigo_hotel):
    """'Services Included' (pestaña Setup, está en el DOM aunque esté oculta) ->
    lista de códigos largos location+service+hotel+option."""
    datos = driver.execute_script(_JS_DLG + """
        var tabla = dlg.querySelector('#setup-tab .tpdestination');
        if (!tabla) return null;
        var heads = Array.from(tabla.querySelectorAll('thead th')).map(function(t){ return t.textContent.trim(); });
        var filas = Array.from(tabla.querySelectorAll('tbody tr')).map(function(tr){
            return Array.from(tr.querySelectorAll('td')).map(function(td){ return td.textContent.trim(); });
        }).filter(function(r){ return r.some(function(c){ return c; }); });
        return {heads: heads, filas: filas};
    """)
    if datos is None:
        raise FlujoError("No encontré la tabla 'Services Included' (#setup-tab .tpdestination).")

    def col(nombre, defecto):
        for i, h in enumerate(datos["heads"]):
            if nombre in h.casefold():
                return i
        return defecto
    i_loc, i_srv, i_opt = col("location", 0), col("service", 1), col("option", 2)
    codigos = []
    for f in datos["filas"]:
        try:
            codigos.append((f[i_loc] + f[i_srv] + codigo_hotel + f[i_opt]).replace(" ", "").upper())
        except IndexError:
            raise FlujoError(f"Fila de 'Services Included' con columnas inesperadas: {f}")
    return codigos


def cantidad_filas_dias(driver):
    return driver.execute_script(_JS_DLG + "return dlg.querySelectorAll('#days-tab .tpbodyrow').length;")


def verificar_habitacion(habitacion_registro, habitaciones_tp):
    """Compara contra el registro. Devuelve (ok, observación). Si no coincide NO se escribe nada."""
    reg = (habitacion_registro or "").replace(" ", "").upper()
    if reg == "MULTIPLEOPTIONS":
        return True, f"Registro dice 'Multiple Options': no se comparó la habitación (Tourplan: {habitaciones_tp})."
    if len(habitaciones_tp) == 1 and habitaciones_tp[0] == reg:
        return True, ""
    return False, f"Habitación linkeada: registro={reg!r}, Tourplan={habitaciones_tp}."


# ── Paso 9: grilla de días (virtual) ────────────────────────────────────────

_JS_LEER_FILAS = _JS_DLG + """
    var vp = dlg.querySelector('#days-tab cdk-virtual-scroll-viewport');
    if (!vp) return null;
    var val = function(row, sel){ var i = row.querySelector(sel); return i ? i.value : null; };
    var filas = Array.from(vp.querySelectorAll('div.tpbodyrow')).map(function(row){
        var l = row.querySelector('.datecol.date label');
        return {f: l ? l.textContent.trim() : null, used: val(row, 'span.used input'),
                max: val(row, 'span.max input'), rel: val(row, 'span.release input')};
    });
    return {top: vp.scrollTop, alto: vp.clientHeight, total: vp.scrollHeight, filas: filas};
"""


def _entero(v):
    """Max/Used/Release como enteros; Release viene con separador de miles ('9,999')."""
    s = re.sub(r"[^\d-]", "", str(v if v is not None else ""))
    return int(s) if s not in ("", "-") else None


def verificar_columnas_dias(driver):
    """Frena si hay grupos de columnas distintos de GENERAL o 'Show Release As Date' tildado."""
    info = driver.execute_script(_JS_DLG + """
        var grupos = Array.from(dlg.querySelectorAll('#days-tab .tpheaderrow.top .splitcol'))
            .map(function(e){ return e.textContent.trim(); }).filter(function(t){ return t; });
        var rel = null;
        Array.from(dlg.querySelectorAll('label')).forEach(function(l){
            if (/show release as date/i.test(l.textContent)) {
                var c = (l.htmlFor && dlg.querySelector('#' + CSS.escape(l.htmlFor))) ||
                        l.querySelector('input[type=checkbox]') ||
                        (l.parentElement && l.parentElement.querySelector('input[type=checkbox]'));
                if (c) rel = c.checked;
            }
        });
        return {grupos: grupos, rel: rel};
    """)
    otros = sorted({g for g in info["grupos"] if g.upper() != "GENERAL"})
    if otros:
        raise FlujoError(f"La grilla de días tiene grupos de columnas distintos de GENERAL: {otros}.")
    if info["rel"]:
        raise FlujoError("'Show Release As Date' está tildado: Release se muestra como fecha.")
    if info["rel"] is None:
        print("    ⚠ No pude ubicar la casilla 'Show Release As Date' (no se verificó).")


def leer_dias(driver, fechas):
    """Lee Used/Max/Release de las fechas pedidas recorriendo la grilla virtual.
    Calcula el scroll por diferencia de días y SIEMPRE verifica leyendo la etiqueta;
    si no está, recorre de a pasos. Devuelve {date: DiaAllocation} (solo las que existen)."""
    verificar_columnas_dias(driver)
    cache, ilegibles = {}, set()

    def scroll(px):
        driver.execute_script(_JS_DLG + """
            var vp = dlg.querySelector('#days-tab cdk-virtual-scroll-viewport');
            vp.scrollTop = Math.max(0, arguments[0]);""", int(px))
        time.sleep(0.5 * tp.VELOCIDAD)

    def leer_una_vez():
        r = driver.execute_script(_JS_LEER_FILAS)
        if r is None:
            raise FlujoError("No encontré la grilla de días (#days-tab cdk-virtual-scroll-viewport).")
        return r

    def absorber():
        """Lee las filas renderizadas. La grilla es virtual y tarda en repintar tras un
        scroll: se repite hasta que dos lecturas seguidas coinciden (pantalla estable)."""
        r = leer_una_vez()
        for _ in range(8):
            time.sleep(0.25 * tp.VELOCIDAD)
            r2 = leer_una_vez()
            estable = r2["top"] == r["top"] and [f["f"] for f in r2["filas"]] == [f["f"] for f in r["filas"]]
            r = r2
            if estable:
                break
        visibles = []
        for fila in r["filas"]:
            f = _fecha_tp(fila["f"])
            if f is None:
                continue
            visibles.append(f)
            u, m, rel = _entero(fila["used"]), _entero(fila["max"]), _entero(fila["rel"])
            if None in (u, m, rel):
                ilegibles.add(f)
            else:
                cache[f] = DiaAllocation(f, u, m, rel)
        return r, visibles

    scroll(0)
    r, visibles = absorber()
    if not visibles:
        return {}
    base = min(visibles)  # primera fila = "Fecha desde" (hoy); días consecutivos, 35 px cada uno

    for f in sorted(set(fechas)):
        if f in cache or f in ilegibles:
            continue
        if f < base:
            continue
        pos = (f - base).days * ALTO_FILA - r["alto"] // 2
        scroll(pos)
        for _ in range(60):
            r, visibles = absorber()
            if f in cache or f in ilegibles or not visibles:
                break
            if f > max(visibles):
                if r["top"] + r["alto"] >= r["total"] - 2:
                    break  # llegó al final de lo cargado: la fecha no tiene fila
                scroll(r["top"] + int(r["alto"] * 0.8))
            elif f < min(visibles):
                if r["top"] <= 0:
                    break
                scroll(r["top"] - int(r["alto"] * 0.8))
            else:
                break  # está dentro del rango visible pero sin fila
    bad = sorted(f for f in set(fechas) if f in ilegibles)
    if bad:
        raise FlujoError("No pude leer Used/Max/Release de: " + ", ".join(f"{f:%d/%m/%Y}" for f in bad))
    return {f: d for f, d in cache.items() if f in set(fechas)}


# ── Cerrar el diálogo (Exit) ────────────────────────────────────────────────

def cerrar_dialogo(driver):
    """Exit (tp-button.cancel > button) del diálogo ACTIVO. En Allocations el diálogo
    no se cierra solo, así que siempre se sale a mano. Espera a que desaparezca."""
    antes = len(driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO))
    if antes == 0:
        return
    ok = driver.execute_script(_JS_DLG + """
        var b = dlg.querySelector('tp-button.cancel > button, tp-button.cancel button');
        if (!b) return false; b.click(); return true;""")
    if not ok:
        raise FlujoError("No encontré el botón Exit del diálogo.")
    if not _esperar(driver, lambda: len(driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO)) < antes, timeout=10):
        raise FlujoError("El diálogo no se cerró tras Exit.")
    time.sleep(0.8 * tp.VELOCIDAD)


# ── Una allocation completa, en modo lectura ────────────────────────────────

def leer_allocation(driver, alloc, codigo_hotel, fechas):
    """Abre la allocation, verifica código/descripción/habitación, lee los días y
    SIEMPRE sale con Exit. Devuelve (dias_por_fecha | None, observaciones).
    dias_por_fecha = None => no hay nada que cerrar en allocation (allocation vacía)."""
    abrir_allocation(driver, alloc.codigo, alloc.descripcion)
    try:
        habitaciones = leer_habitaciones(driver, codigo_hotel)
        if alloc.vacia:
            if habitaciones or cantidad_filas_dias(driver) > 0:
                raise FlujoError(
                    "El registro dice 'allocation vacía' pero Tourplan tiene "
                    f"{len(habitaciones)} habitación(es) y {cantidad_filas_dias(driver)} día(s) cargados.")
            return None, "allocation vacía"
        ok, obs = verificar_habitacion(alloc.habitacion, habitaciones)
        if not ok:
            raise FlujoError(obs)
        return leer_dias(driver, fechas), obs
    finally:
        cerrar_dialogo(driver)


def preparar_hotel(driver, codigo_hotel, hoy=None):
    """Supplier -> menú Allocations -> filtro. Se hace UNA vez por pedido."""
    abrir_supplier(driver, codigo_hotel)
    abrir_menu_allocations(driver)
    filtrar_hasta(driver, hoy or date.today())
