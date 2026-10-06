"""Flujo Selenium de Rates (spec sección 6): ir a la habitación, leer la grilla de períodos,
cortar (split) y editar (tarifa en 0 + status). Las decisiones salen de allocation/rates_plan.py.

Escribe en Tourplan SOLO si aplicar=True. En lectura solo navega y lee.
Reglas duras: nunca se hace clic en Delete Date Range, Copy Date Range, Insert Rate Set ni
Delete Rate Set; solo se elige por coincidencia exacta; un período Closed nunca pasa a Manual;
antes de escribir se verifica el título del diálogo y después se relee el valor.
"""

import os
import re
import time
from datetime import timedelta

from selenium.webdriver.common.by import By

from allocation import rates_plan as rp
from allocation.constantes import CLOSEABLE_SERVICE_TYPES, EXCLUDED_OPTIONS
from common import tourplan as tp
from tourplan_flujos.allocations import (
    FlujoError, SEL_DIALOGO, _JS_DLG, _esperar, _fecha_tp, _norm, abrir_supplier, cerrar_dialogo,
)

SEL_MODAL_PRODUCTOS = ".tpmodal-productlistnext"
_RE_RANGO = re.compile(r"(\d{1,2}/\w+/\d{4})\s*[-–]\s*(\d{1,2}/\w+/\d{4})")
_RE_TITULO_PERIODO = re.compile(r'^(\S+)\s+(\d{1,2}/\w+/\d{4})\s*/\s*(\d{1,2}/\w+/\d{4})\s+"([^"]+)"\s*$')


def codigo_largo(location, servicio, supplier, opcion):
    return f"{location}{servicio}{supplier}{opcion}".replace(" ", "").upper()


# ── 6.2: ir a la habitación (Product Find) ──────────────────────────────────

def _abrir_product_find(driver):
    lupa = driver.find_elements(By.CSS_SELECTOR, "#searchWrapper tp-button.lookupproduct button.tplookupproduct")
    if not lupa:
        raise FlujoError("No encontré la lupa del Product (#searchWrapper tp-button.lookupproduct).")
    tp.jc(driver, lupa[0])
    if not _esperar(driver, lambda: driver.find_elements(By.CSS_SELECTOR, SEL_MODAL_PRODUCTOS), timeout=15):
        raise FlujoError("No se abrió el modal Product Find.")
    time.sleep(1.2 * tp.VELOCIDAD)


_JS_FILAS_MODAL = """
    var tabla = document.querySelector('.tpmodal-productlistnext tp-grid[tpid="modalsNextprevproductMaingrid"]');
    if (!tabla) return null;
    var t = function(tr, c){ var e = tr.querySelector('td.tpcol-' + c); return e ? e.textContent.trim() : ''; };
    return Array.from(tabla.querySelectorAll('tbody tr')).map(function(tr){
        return {loc: t(tr,'locationcode'), srv: t(tr,'servicecode'), sup: t(tr,'suppliercode'),
                opt: t(tr,'optioncode'), desc: t(tr,'optiondescription')}; });
"""


def _leer_pagina_modal(driver):
    filas = driver.execute_script(_JS_FILAS_MODAL)
    if filas is None:
        raise FlujoError("No encontré la grilla del modal Product Find.")
    return filas


def recorrer_product_find(driver, objetivo=None, max_paginas=60):
    """Pagina el modal (la última fila de una página se repite como primera de la siguiente:
    se deduplica por código largo). Con objetivo: hace clic en la fila de coincidencia EXACTA y
    devuelve True. Sin objetivo: devuelve el dict {codigo_largo: fila} de todas las opciones."""
    vistas = {}
    for _ in range(max_paginas):
        filas = _leer_pagina_modal(driver)
        nuevas = 0
        for f in filas:
            c = codigo_largo(f["loc"], f["srv"], f["sup"], f["opt"])
            if c not in vistas:
                vistas[c] = f
                nuevas += 1
        if objetivo is not None and objetivo.upper() in vistas:
            clic = driver.execute_script("""
                var obj = arguments[0];
                var tabla = document.querySelector('.tpmodal-productlistnext tp-grid[tpid="modalsNextprevproductMaingrid"]');
                var t = function(tr, c){ var e = tr.querySelector('td.tpcol-' + c); return e ? e.textContent.trim() : ''; };
                var ok = Array.from(tabla.querySelectorAll('tbody tr')).filter(function(tr){
                    return (t(tr,'locationcode') + t(tr,'servicecode') + t(tr,'suppliercode') + t(tr,'optioncode'))
                        .replace(/ /g,'').toUpperCase() === obj; });
                if (ok.length !== 1) return ok.length;
                var td = ok[0].querySelector('td.tpcol-optiondescription') || ok[0].querySelector('td');
                td.click(); return 1;""", objetivo.upper())
            if clic == 1:
                time.sleep(1.5 * tp.VELOCIDAD)
                tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)
                return True
            if clic > 1:
                raise FlujoError(f"La habitación {objetivo} aparece {clic} veces en la misma página del Product Find.")
        if nuevas == 0:
            break
        siguiente = driver.find_elements(By.CSS_SELECTOR, f"{SEL_MODAL_PRODUCTOS} tp-button.next button")
        if not siguiente or not siguiente[0].is_enabled():
            break
        tp.jc(driver, siguiente[0])
        time.sleep(1.0 * tp.VELOCIDAD)
    if objetivo is not None:
        raise FlujoError(f"No encontré la habitación {objetivo} en el Product Find del hotel.")
    return vistas


def listar_habitaciones_ht(driver, codigo_hotel):
    """TODAS: todas las opciones HT del hotel excepto 600HTL y ROOMS (se lee de Tourplan)."""
    abrir_supplier(driver, codigo_hotel)
    _abrir_product_find(driver)
    try:
        todas = recorrer_product_find(driver)
    finally:
        cerrar_modal_productos(driver)
    return sorted(c for c, f in todas.items()
                  if f["srv"].upper() in CLOSEABLE_SERVICE_TYPES and f["opt"].upper() not in EXCLUDED_OPTIONS)


def cerrar_modal_productos(driver):
    """Cierra el modal Product Find sin elegir nada (Exit/Cancel/cerrar)."""
    try:
        driver.execute_script("""
            var m = document.querySelector('.tpmodal-productlistnext');
            if (!m) return; var b = m.querySelector('tp-button.cancel button, tp-button.exit button, tp-button.close button');
            if (b) b.click();""")
        time.sleep(0.8 * tp.VELOCIDAD)
    except Exception:
        pass


def abrir_habitacion(driver, codigo_hotel, codigo_hab):
    """Supplier -> lupa del Product -> habitación exacta -> menú Rates -> grilla de períodos."""
    codigo_hab = codigo_hab.replace(" ", "").upper()
    print(f"    → habitación {codigo_hab}: Product Find", flush=True)
    abrir_supplier(driver, codigo_hotel)
    _abrir_product_find(driver)
    recorrer_product_find(driver, objetivo=codigo_hab)
    abrir_menu_rates(driver)


def abrir_menu_rates(driver):
    print("    → menú Rates", flush=True)
    img = tp.wait(driver, "nav img")
    tp.jc(driver, img)
    tp.wait(driver, ".nav-menu")
    time.sleep(1.5 * tp.VELOCIDAD)
    res = driver.execute_script("""
        var items = Array.from(document.querySelectorAll('.nav-menu .menu-heading > label'));
        var l = items.find(function(x){ return x.textContent.trim().toLowerCase() === 'rates'; });
        if (!l) return {ok: false, items: items.map(function(x){ return x.textContent.trim(); })};
        var raiz = l.closest('li') || l.parentElement;
        var c = (raiz && raiz.querySelector('.click-area')) || l.parentElement.querySelector('.click-area') || l;
        c.click(); return {ok: true};""")
    if not res["ok"]:
        raise FlujoError(f"No encontré 'Rates' en el menú. Ítems: {res['items']}")
    time.sleep(2 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)
    tp.cerrar_nav_backdrop(driver, velocidad=tp.VELOCIDAD)
    if not _esperar(driver, lambda: driver.find_elements(By.CSS_SELECTOR, "th.tpcol-RatePeriod"), timeout=15):
        raise FlujoError("No apareció la grilla de Rates (th.tpcol-RatePeriod).")


# ── 6.3: grilla de períodos ─────────────────────────────────────────────────

_JS_GRILLA = """
    var th = document.querySelector('th.tpcol-RatePeriod'); if (!th) return null;
    var tabla = th.closest('table'); if (!tabla) return null;
    var t = function(tr, c){ var e = tr.querySelector('td.tpcol-' + c); return e ? e.textContent.replace(/\\s+/g,' ').trim() : ''; };
    return Array.from(tabla.querySelectorAll('tbody tr')).map(function(tr){
        return {rango: t(tr,'rateperiod'), pc: t(tr,'pricecodecode'), status: t(tr,'ratestatuses'), nombre: t(tr,'ratenames')}; })
        .filter(function(f){ return f.rango; });
"""


def parsear_rango(txt):
    m = _RE_RANGO.search(txt or "")
    if not m:
        raise FlujoError(f"No entiendo el período de la grilla: {txt!r}")
    a, b = _fecha_tp(m.group(1)), _fecha_tp(m.group(2))
    if not a or not b:
        raise FlujoError(f"No entiendo las fechas del período: {txt!r}")
    return a, b


# La grilla de períodos puede tener scroll interno (CDK virtual scroll: solo las filas cercanas a la
# pantalla existen en el DOM). Se detecta el contenedor y se recorre en pasos, deduplicando por
# CONTENIDO (rango + price code), nunca por índice ni por referencias guardadas.
_JS_CONTENEDOR = """
    function contenedor(){
        var th = document.querySelector('th.tpcol-RatePeriod'), tabla = th ? th.closest('table') : null;
        if (tabla) {
            var c = tabla.closest('cdk-virtual-scroll-viewport'); if (c) return c;
            var el = tabla.parentElement;
            while (el && el !== document.body) {
                var st = getComputedStyle(el);
                var puede = st.overflowY === 'auto' || st.overflowY === 'scroll' || st.overflow === 'auto' || st.overflow === 'scroll';
                if (puede && el.scrollHeight > el.clientHeight + 10) return el;
                el = el.parentElement;
            }
        }
        return document.scrollingElement || document.body;
    }
"""
PASO_MINIMO = 100


def _info_scroll(driver):
    return driver.execute_script(_JS_CONTENEDOR + "var c = contenedor(); return {top: c.scrollTop, alto: c.clientHeight, total: c.scrollHeight};")


def _scroll_a(driver, pos):
    """Mueve el contenedor Y la ventana (según el componente scrollea uno u otro)."""
    driver.execute_script(_JS_CONTENEDOR + "var c = contenedor(); c.scrollTop = arguments[0]; window.scrollTo(0, arguments[0]);", int(pos))
    time.sleep(0.4 * tp.VELOCIDAD)


def _posiciones(driver):
    """Posiciones de scroll a recorrer, de arriba hacia abajo, en pasos de la mitad del alto visible."""
    info = _info_scroll(driver)
    paso = max(PASO_MINIMO, info["alto"] // 2)
    pos, out = 0, []
    while True:
        out.append(pos)
        if pos + info["alto"] >= info["total"] - 2 or len(out) > 600:
            return out
        pos += paso


def _leer_estable(driver):
    """Lee las filas renderizadas; repite hasta que dos lecturas seguidas coinciden (el re-render
    de la grilla virtual puede tardar tras un scroll)."""
    prev = None
    for _ in range(6):
        filas = driver.execute_script(_JS_GRILLA)
        if filas is None:
            raise FlujoError("No encontré la grilla de períodos de Rates.")
        if filas == prev:
            return filas
        prev = filas
        time.sleep(0.25 * tp.VELOCIDAD)
    return prev


def leer_periodos(driver, rangos=None):
    """Lee la grilla de períodos recorriendo el scroll interno si lo hay. Deduplica por contenido.
    La grilla viene de la fecha más lejana a la más reciente. Con `rangos` (los que hay que cerrar) deja de
    scrollear apenas leyó un período que empieza MESES_MARGEN meses antes de la fecha más reciente pedida
    (margen por si los price codes tienen cortes distintos). Sin rangos, o con
    TOURPLAN_RATES_ESCANEO_COMPLETO=1, lee toda la grilla."""
    completo = os.environ.get("TOURPLAN_RATES_ESCANEO_COMPLETO", "") == "1"
    vistos = {}
    _scroll_a(driver, 0)
    cortado_en = None
    for pos in _posiciones(driver):
        if pos:
            _scroll_a(driver, pos)
        for f in _leer_estable(driver):
            vistos.setdefault((f["rango"].casefold(), f["pc"].upper(), f["status"], f["nombre"]), f)
        if rangos and not completo:
            en_orden = [rp.Periodo(*parsear_rango(f["rango"]), f["pc"], f["status"], f["nombre"]) for f in vistos.values()]
            if rp.ya_paso_el_objetivo(en_orden, rangos):
                cortado_en = (rp.limite_de_lectura(rangos), len(vistos))
                break
    _scroll_a(driver, 0)
    if cortado_en:
        print(f"    ↳ se dejó de leer al llegar a períodos anteriores al {cortado_en[0]:%d/%m/%Y} "
              f"({rp.MESES_MARGEN} meses antes de lo pedido); {cortado_en[1]} fila(s) leídas", flush=True)
    out = []
    for f in vistos.values():
        a, b = parsear_rango(f["rango"])
        out.append(rp.Periodo(a, b, f["pc"], f["status"], f["nombre"]))
    return out


def _intentar_clic(driver, periodo):
    """Clic en td.tpcol-rateperiod de la fila (rango, price code, Rate Name) ENTRE LAS FILAS RENDERIZADAS.
    Atómico: se ubica y se hace clic en la misma ejecución. El Rate Name no decide si se cierra, pero sí
    distingue dos filas con el mismo período y price code. Devuelve cuántas filas coinciden."""
    return driver.execute_script("""
        var a = arguments[0], b = arguments[1], pc = arguments[2], nombre = arguments[3];
        var th = document.querySelector('th.tpcol-RatePeriod'); if (!th) return -1;
        var tabla = th.closest('table'); var norm = function(s){ return (s||'').replace(/\\s+/g,' ').trim(); };
        var ok = Array.from(tabla.querySelectorAll('tbody tr')).filter(function(tr){
            var r = tr.querySelector('td.tpcol-rateperiod'), p = tr.querySelector('td.tpcol-pricecodecode');
            if (!r || !p || norm(p.textContent).toUpperCase() !== pc) return false;
            var n = tr.querySelector('td.tpcol-ratenames');
            if (norm(n ? n.textContent : '').toLowerCase() !== nombre) return false;
            var m = norm(r.textContent).match(/(\\d+\\/\\w+\\/\\d+)\\s*[-–]\\s*(\\d+\\/\\w+\\/\\d+)/);
            return m && m[1].toLowerCase() === a && m[2].toLowerCase() === b; });
        if (ok.length === 1) { ok[0].querySelector('td.tpcol-rateperiod').click(); }
        return ok.length;""", tp.fmt_tp(_dt(periodo.ini)).casefold(), tp.fmt_tp(_dt(periodo.fin)).casefold(),
        periodo.pc.upper(), " ".join((periodo.rate_name or "").split()).lower())


def _clic_fila(driver, periodo):
    """Abre el período (rango, price code). Si la fila no está renderizada, recorre el scroll de la
    grilla hasta encontrarla (se reubica por texto en cada posición, nunca por índice). Debe haber
    EXACTAMENTE una; nunca se hace clic por posición."""
    n = _intentar_clic(driver, periodo)
    if n == 0:
        for pos in _posiciones(driver):
            _scroll_a(driver, pos)
            n = _intentar_clic(driver, periodo)
            if n != 0:
                break
    if n != 1:
        raise FlujoError(f"Período {periodo.ini:%d/%m/%Y}-{periodo.fin:%d/%m/%Y} ({periodo.pc}): {n} filas coinciden.")
    if not _esperar(driver, lambda: driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO), timeout=15):
        raise FlujoError("No se abrió el diálogo del período.")
    time.sleep(1.0 * tp.VELOCIDAD)
    tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)


def _dt(d):
    from datetime import datetime
    return datetime.combine(d, datetime.min.time())


def verificar_titulo_periodo(driver, cod_largo, periodo):
    """Título del diálogo: `BUEHT1ESP06CPNV   24/Nov/2026/24/Nov/2026 "TR"`."""
    titulo = driver.execute_script(_JS_DLG + """
        var h = dlg.querySelector('.tpmodal-productcosts h3, h3'); return h ? h.textContent : null;""")
    m = _RE_TITULO_PERIODO.match(" ".join((titulo or "").split()))
    ok = (m and m.group(1).upper() == cod_largo.upper() and _fecha_tp(m.group(2)) == periodo.ini
          and _fecha_tp(m.group(3)) == periodo.fin and m.group(4).upper() == periodo.pc.upper())
    if not ok:
        raise FlujoError(f"Título del diálogo {titulo!r}: se esperaba {cod_largo} "
                         f"{periodo.ini:%d/%b/%Y}/{periodo.fin:%d/%b/%Y} \"{periodo.pc}\".")


# ── 6.5: un corte (split) ───────────────────────────────────────────────────

def hacer_corte(driver, cod_largo, periodo, fecha_corte):
    """Abre el período, abre Split Date y corta en fecha_corte. Un solo corte por diálogo.
    Si aparece la casilla 'Split All Applicable Price Codes' (solo cuando más de un price code comparte
    exactamente el período) la deja tildada: corta todos esos price codes (FX incluido: su período puede
    cortarse, lo único que nunca se hace con FX es editarlo). Si no aparece, corta sin ella."""
    _clic_fila(driver, periodo)
    try:
        verificar_titulo_periodo(driver, cod_largo, periodo)
        ok = driver.execute_script(_JS_DLG + """
            var b = dlg.querySelector('tp-button.splitdaterange > button'); if (!b) return false; b.click(); return true;""")
        if not ok:
            raise FlujoError("No encontré el botón Split Date Range.")
        if not _esperar(driver, lambda: driver.execute_script(
                "var d = Array.from(document.querySelectorAll('body > tp-dialog')).pop();"
                "return !!(d && d.querySelector('.split-content-panel'));"), timeout=10):
            raise FlujoError("No se abrió el diálogo de Split.")
        time.sleep(0.8 * tp.VELOCIDAD)
        titulo = driver.execute_script(_JS_DLG + "var h = dlg.querySelector('h3'); return h ? h.textContent : '';")
        m = _RE_RANGO.search(titulo or "")
        if not m or (_fecha_tp(m.group(1)), _fecha_tp(m.group(2))) != (periodo.ini, periodo.fin):
            raise FlujoError(f"El diálogo de Split dice {titulo!r}, se esperaba {periodo.ini:%d/%m/%Y}-{periodo.fin:%d/%m/%Y}.")
        marcado = driver.execute_script(_JS_DLG + """
            var c = dlg.querySelector('#split-applicable');
            if (!c || !(c.offsetWidth || c.offsetHeight || c.getClientRects().length)) return null;   // no existe o está oculta
            var i = c.tagName === 'INPUT' ? c : c.querySelector('input'); return i ? !!i.checked : null;""")
        if marcado is None:
            # Tourplan solo muestra la casilla cuando más de un price code comparte exactamente el período.
            # Si no aparece no hay nada que tildar: el split se hace sin ella.
            print("    ↳ no hay casilla 'Split All Applicable Price Codes' (un solo price code con ese período): "
                  "se corta sin ella", flush=True)
        elif not marcado:
            driver.execute_script(_JS_DLG + """
                var l = dlg.querySelector('label[for="split-applicable"]');
                if (l) { l.click(); } else { var c = dlg.querySelector('#split-applicable'); c.click(); }""")
            time.sleep(0.5 * tp.VELOCIDAD)
            if not driver.execute_script(_JS_DLG + """
                var c = dlg.querySelector('#split-applicable');
                var i = c.tagName === 'INPUT' ? c : c.querySelector('input'); return !!(i && i.checked);"""):
                raise FlujoError("No pude tildar 'Split All Applicable Price Codes'.")
        inp = driver.execute_script(_JS_DLG + "return dlg.querySelector('input.tpdate-productdatesplitpoint');")
        if inp is None:
            raise FlujoError("No encontré el campo de fecha de corte.")
        tp.set_val_con_blur(driver, inp, f"{fecha_corte.day:02d}/{fecha_corte.month:02d}/{fecha_corte.year % 100:02d}")
        time.sleep(0.8 * tp.VELOCIDAD)
        oculto = driver.execute_script("""
            var el = arguments[0];
            for (var i = 0; i < 4 && el; i++, el = el.parentElement) { var h = el.querySelector('input.tphidden'); if (h) return h.value; }
            return null;""", inp)
        if _fecha_tp(oculto) != fecha_corte:
            raise FlujoError(f"Tourplan entendió la fecha de corte como {oculto!r}, se esperaba {fecha_corte:%d/%m/%Y}.")
        habil = _esperar(driver, lambda: driver.execute_script(
            _JS_DLG + "var b = dlg.querySelector('button.tpbutton-addsplit'); return !!(b && !b.disabled);"), timeout=8)
        if not habil:
            raise FlujoError("El botón Add Split no se habilitó: la fecha de corte no es válida.")
        driver.execute_script(_JS_DLG + "dlg.querySelector('button.tpbutton-addsplit').click();")
        time.sleep(0.8 * tp.VELOCIDAD)
        rangos = driver.execute_script(_JS_DLG + """
            return Array.from(dlg.querySelectorAll('ul.dateranges span.date-range-display')).map(function(s){ return s.textContent.trim(); });""")
        parseados = []
        for r in rangos:
            mm = re.search(r"(\d{1,2}/\w+/\d{4})\s*[-–]\s*\w+\s+(\d{1,2}/\w+/\d{4})", r)
            if not mm:
                raise FlujoError(f"No entiendo el rango resultante del split: {r!r}")
            parseados.append((_fecha_tp(mm.group(1)), _fecha_tp(mm.group(2))))
        esperado = [(periodo.ini, fecha_corte - timedelta(days=1)), (fecha_corte, periodo.fin)]
        if parseados != esperado:
            raise FlujoError(f"El split dejó {parseados}, se esperaba {esperado}.")
        driver.execute_script(_JS_DLG + "dlg.querySelector('tp-button.ok button').click();")   # un solo corte por diálogo
        time.sleep(1.2 * tp.VELOCIDAD)
        tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)
        _guardar_o_salir_periodo(driver)
    except Exception:
        _salir_de_todos_los_dialogos(driver)
        raise


def _guardar_o_salir_periodo(driver):
    """Después de OK del split puede quedar abierto el diálogo del período: se guarda si hay
    cambios pendientes (Save habilitado) y si no se sale con Exit."""
    for _ in range(3):
        if not driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO):
            return
        estado = driver.execute_script(_JS_DLG + """
            var s = dlg.querySelector('tp-button.save > button, tp-button.save button');
            return s ? !s.disabled : null;""")
        if estado:
            driver.execute_script(_JS_DLG + "dlg.querySelector('tp-button.save button').click();")
            if not _esperar(driver, lambda: not driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO), timeout=20):
                raise FlujoError("El diálogo del período no se cerró tras guardar el corte.")
            tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)
            return
        cerrar_dialogo(driver)
        return


def _salir_de_todos_los_dialogos(driver):
    for _ in range(3):
        if not driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO):
            return
        try:
            cerrar_dialogo(driver)
        except Exception:
            break


# ── 6.6: editar un período (tarifa en 0 + status) ───────────────────────────

def _numero(txt):
    s = re.sub(r"[^\d.,-]", "", txt or "").replace(",", "")
    try:
        return float(s) if s not in ("", "-") else None
    except ValueError:
        return None


def poner_tarifas_en_cero(driver):
    """Pestaña Rates: en cada fila, Group Cost (primer td.tpcol-cost) con valor distinto de 0 -> 0.
    No toca filas vacías ni las que ya valen 0. Después relee las demás columnas de esa fila: si
    Tourplan no las actualizó, frena. Nunca escribe en ellas. Devuelve cuántas filas puso en 0."""
    filas = driver.execute_script(_JS_DLG + """
        var tabla = dlg.querySelector('#tabs-rates #costs-panel table'); if (!tabla) return null;
        return Array.from(tabla.querySelectorAll('tbody tr')).map(function(tr){
            return Array.from(tr.querySelectorAll('td.tpcol-cost input')).map(function(i){ return i.value; }); });""")
    if filas is None:
        raise FlujoError("No encontré la grilla de tarifas (#tabs-rates #costs-panel).")
    cambiadas = 0
    for i, valores in enumerate(filas):
        group = _numero(valores[0]) if valores else None
        if group is None or group == 0:
            continue
        campo = driver.execute_script(_JS_DLG + """
            var tr = dlg.querySelectorAll('#tabs-rates #costs-panel table tbody tr')[arguments[0]];
            return tr ? tr.querySelector('td.tpcol-cost input.tpnumber-ratecostamount') : null;""", i)
        if campo is None:
            raise FlujoError(f"No encontré el campo Group Cost de la fila {i + 1} de tarifas.")
        tp.set_val_con_blur(driver, campo, "0")
        time.sleep(0.4 * tp.VELOCIDAD)
        despues = driver.execute_script(_JS_DLG + """
            var tr = dlg.querySelectorAll('#tabs-rates #costs-panel table tbody tr')[arguments[0]];
            return Array.from(tr.querySelectorAll('td.tpcol-cost input')).map(function(x){ return x.value; });""", i)
        if any((_numero(v) or 0) != 0 for v in despues):
            raise FlujoError(f"Fila {i + 1} de tarifas: tras poner Group Cost en 0 las demás columnas quedaron {despues}. Se frena.")
        cambiadas += 1
    return cambiadas


_JS_RADIOS = _JS_DLG + """
    var g = dlg.querySelector('tp-group.tpgroup-ratestatus'); if (!g) return null;
    return Array.from(g.querySelectorAll('input[type=button], input[type=radio]')).map(function(inp){
        var l = inp.id ? g.querySelector('label[for="' + inp.id + '"]') : null;
        var raiz = inp.closest('tp-radio') || inp;
        return {id: inp.id, texto: l ? l.textContent.trim() : '',
                marcado: inp.classList.contains('checked') || raiz.classList.contains('checked') || !!inp.checked}; });
"""


def leer_status_dialogo(driver):
    radios = driver.execute_script(_JS_RADIOS)
    if radios is None:
        raise FlujoError("No encontré el grupo de status (tp-group.tpgroup-ratestatus).")
    marcados = [r["texto"] for r in radios if r["marcado"]]
    if len(marcados) != 1:
        raise FlujoError(f"Status del período no claro: radios {radios}.")
    return rp.normalizar_status(marcados[0])


def elegir_status(driver, actual, nuevo):
    """Elige el radio por el TEXTO de su etiqueta (no por id) y verifica que quedó el correcto.
    Segunda barrera: se vuelve a leer el radio seleccionado justo antes del clic."""
    ahora = leer_status_dialogo(driver)
    rp.verificar_no_pasa_de_closed_a_manual(ahora, nuevo)
    if ahora != actual:
        raise FlujoError(f"El status cambió desde la lectura ({actual} -> {ahora}).")
    radios = driver.execute_script(_JS_RADIOS)
    cand = [r for r in radios if r["texto"].strip().casefold() == nuevo.casefold()]
    if len(cand) != 1:
        raise FlujoError(f"No encontré un único radio {nuevo!r}: {radios}.")
    driver.execute_script(_JS_DLG + """
        var i = dlg.querySelector('tp-group.tpgroup-ratestatus #' + CSS.escape(arguments[0]));
        if (!i) { var g = dlg.querySelector('tp-group.tpgroup-ratestatus'); i = g.querySelector('[id="' + arguments[0] + '"]'); }
        i.click();""", cand[0]["id"])
    time.sleep(0.5 * tp.VELOCIDAD)
    if leer_status_dialogo(driver) != nuevo:
        raise FlujoError(f"Tras el clic el status no quedó en {nuevo}.")


def editar_periodo(driver, cod_largo, ed):
    """Abre el período, verifica el título, pone la tarifa en 0, cambia el status y guarda.
    En Rates el diálogo se cierra solo al guardar."""
    p, nuevo = ed.periodo, ed.nuevo_status
    rp.verificar_no_es_intocable(p.pc)          # FX: nunca se pone la tarifa en 0 ni se cambia el status
    actual = rp.normalizar_status(p.status)
    rp.verificar_no_pasa_de_closed_a_manual(actual, nuevo)
    _clic_fila(driver, p)
    try:
        verificar_titulo_periodo(driver, cod_largo, p)
        poner_tarifas_en_cero(driver)
        driver.execute_script(_JS_DLG + "var t = dlg.querySelector('#tptablabel-tabs-rateset'); if (t) t.click();")
        if not _esperar(driver, lambda: driver.execute_script(
                _JS_DLG + "return !!dlg.querySelector('tp-group.tpgroup-ratestatus');"), timeout=8):
            raise FlujoError("No apareció la pestaña Rate Set.")
        elegir_status(driver, actual, nuevo)
        if not _esperar(driver, lambda: driver.execute_script(
                _JS_DLG + "var b = dlg.querySelector('tp-button.save button'); return !!(b && !b.disabled);"), timeout=10):
            raise FlujoError("El botón Save no se habilitó.")
        driver.execute_script(_JS_DLG + "dlg.querySelector('tp-button.save button').click();")
        if not _esperar(driver, lambda: not driver.find_elements(By.CSS_SELECTOR, SEL_DIALOGO), timeout=20):
            raise FlujoError("El diálogo del período no se cerró tras guardar.")
        tp.esperar_fin_carga(driver, velocidad=tp.VELOCIDAD)
    except Exception:
        _salir_de_todos_los_dialogos(driver)
        raise


# ── Una habitación completa ─────────────────────────────────────────────────

def procesar_habitacion(driver, codigo_hotel, cod_hab, rangos, aplicar=False, max_iteraciones=60):
    """Abre la habitación y cierra sus tarifas para los rangos de fechas.
    Devuelve (plan_final, texto, cantidad_a_cerrar_o_cerrados). En lectura solo planea. Si hace falta cortar, en lectura se
    informa el corte sin hacerlo; en aplicar se corta, se relee y se replanea."""
    abrir_habitacion(driver, codigo_hotel, cod_hab)
    hechas = cortes = 0
    for _ in range(max_iteraciones):
        periodos = leer_periodos(driver, rangos)
        plan = rp.planear(periodos, rangos)
        print(f"    → grilla de Rates: {len(periodos)} fila(s); a editar {len(plan.ediciones)}, "
              f"cortes pendientes {len(plan.cortes)}, ya cerradas {len(plan.ya_cerrados)}", flush=True)
        if plan.cortes and not aplicar:
            return plan, rp.resumen(cod_hab, plan, lectura=True), len(plan.cortes)
        if plan.cortes:
            c = plan.cortes[0]
            candidato = next((p for p in periodos if (p.ini, p.fin) == (c.ini, c.fin)
                              and rp.decidir_status(rp.normalizar_status(p.status), p.pc) is not None), None)
            if candidato is None:
                raise FlujoError(f"No encontré la fila del período {c.ini:%d/%m/%Y}-{c.fin:%d/%m/%Y} para cortarlo.")
            print(f"    → corte del período {c.ini:%d/%m/%Y}-{c.fin:%d/%m/%Y} en {c.fecha:%d/%m/%Y}", flush=True)
            hacer_corte(driver, cod_hab, candidato, c.fecha)
            cortes += 1
            continue
        if not aplicar:
            return plan, rp.resumen(cod_hab, plan, lectura=True), len(plan.ediciones)
        if not plan.ediciones:
            break
        e = plan.ediciones[0]
        print(f"    → editando {e.periodo.ini:%d/%m/%Y}-{e.periodo.fin:%d/%m/%Y} {e.periodo.pc}: "
              f"{e.periodo.status} → {e.nuevo_status}", flush=True)
        editar_periodo(driver, cod_hab, e)      # uno por vez: se relee la grilla después de cada guardado
        hechas += 1
    else:
        raise FlujoError("Demasiadas iteraciones cortando/editando: se frena.")
    final = rp.planear(leer_periodos(driver, rangos), rangos)
    if final.ediciones or final.cortes:
        raise FlujoError("Después de cerrar todavía quedan períodos sin cerrar: " + rp.resumen(cod_hab, final, lectura=True))
    texto = f"{cod_hab}: cerró {hechas} período(s)/price code(s)" + (f" ({cortes} corte(s))" if cortes else "") \
        + f" · ya cerrados {len(final.ya_cerrados)}"
    if final.sin_periodo:
        from allocation.plan import _rangos_txt
        texto += f" · SIN PERÍODO en Rates: {_rangos_txt(final.sin_periodo)}"
    return final, texto, hechas + cortes
