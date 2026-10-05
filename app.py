"""Cierre de allotment y tarifas convenio — Tourplan NX.

App local (Streamlit) que corre en la PC de cada persona. Etapa 1: esqueleto
sin Selenium — busca el hotel en el registro (hoja ALLOCATIONS), arma el pedido
(fechas + allocations) y lo escribe en la cola (hoja COLA) del Google Sheet.

Pantallas: 1 Buscar hotel · 2 Fechas y alcance · 3 Revisar y enviar · 4 Cola.
La configuración (credenciales de Tourplan, URL del Sheet, entorno) se guarda
por PC en ~/.tourplan-allocation (ver common/user_config.py).
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from common.abort import ABORT_EXIT_CODE
from allocation import cola, fechas as fch, registro
from allocation.constantes import (
    ALLOCATIONS_TODAS, EXCLUDED_OPTIONS, HOJA_ALLOCATIONS, HOJA_COLA, MODO_APLICAR,
    MODO_LECTURA, URLS_ENTORNO, URL_PRODUCCION,
)
from common import user_config
from common.sheets_client import conectar_sheets

REPO_ROOT = Path(__file__).resolve().parent

_calendario = components.declare_component(
    "calendario_fechas", path=str(REPO_ROOT / "components" / "calendario"))

PAGINAS = [
    ("buscar", "1 · Buscar hotel"),
    ("fechas", "2 · Fechas y alcance"),
    ("revisar", "3 · Revisar y enviar"),
    ("cola", "4 · Cola"),
]
MODOS = [
    ("Lectura (no escribe nada en Tourplan)", MODO_LECTURA),
    ("Aplicar (ejecuta los cierres)", MODO_APLICAR),
]


def hoy():
    return date.today()


def fmt_fecha(f):
    return f.strftime("%d/%m/%Y")


def fmt_rangos(fechas):
    partes = []
    for a, b in fch.agrupar_rangos(fechas):
        partes.append(fmt_fecha(a) if a == b else f"{fmt_fecha(a)} al {fmt_fecha(b)}")
    return partes


# ── Acceso al Sheet ───────────────────────────────────────────────────────

def _conectar(hoja):
    cfg = user_config.cargar()
    if not cfg["sheet_url"]:
        raise ValueError("Falta la URL del Google Sheet en ⚙️ Configuración.")
    return conectar_sheets(cfg["sheet_url"], hoja, user_config.CREDENTIALS_PATH, user_config.TOKEN_PATH)


def _cargar_registro(forzar=False):
    """Lee ALLOCATIONS una vez por sesión (botón "Recargar" para refrescar)."""
    if forzar or "registro" not in st.session_state:
        try:
            with st.spinner("Leyendo el registro de allocations..."):
                allocs, hoteles = registro.cargar_registro(_conectar(HOJA_ALLOCATIONS))
            st.session_state["registro"] = {"allocs": allocs, "hoteles": hoteles, "error": None}
        except Exception as e:  # se muestra en pantalla, no se rompe la app
            st.session_state["registro"] = {"allocs": [], "hoteles": [], "error": str(e)}
    return st.session_state["registro"]


def _hotel_elegido():
    clave = st.session_state.get("hotel_clave")
    if clave is None:
        return None
    for h in st.session_state.get("registro", {}).get("hoteles", []):
        if (h.codigo or h.nombre) == clave:
            return h
    return None


def _ir(pagina):
    st.session_state["pagina"] = pagina
    st.rerun()


# ── Pantalla 1: buscar hotel ──────────────────────────────────────────────

def render_buscar():
    st.subheader("Buscar hotel")
    col_q, col_r = st.columns([4, 1])
    with col_q:
        consulta = st.text_input("Nombre o código del hotel", key="consulta")
    with col_r:
        st.markdown("<div style='height: 1.9em'></div>", unsafe_allow_html=True)
        if st.button("🔄 Recargar", use_container_width=True,
                     help="Vuelve a leer la hoja ALLOCATIONS del Sheet."):
            _cargar_registro(forzar=True)

    reg = _cargar_registro()
    if reg["error"]:
        st.error(f"No pude leer el registro: {reg['error']}")
        return
    dups = registro.duplicados(reg["allocs"])
    if dups:
        st.warning("Hay allocations repetidas en el registro (mismo hotel y código): "
                   + ", ".join(f"{h} / {c}" for h, c in dups))
    if not consulta.strip():
        st.caption(f"{len(reg['hoteles'])} hoteles en el registro. Escribí un nombre o código para buscar.")
        return

    resultados = registro.buscar(reg["hoteles"], consulta)
    if not resultados:
        st.info(
            "Este hotel no figura en el registro: se entiende que **no tiene allocation**. "
            "Si hay dudas, verificalo directamente en Tourplan (esta app no consulta Tourplan).")
        return

    etiquetas = {(h.codigo or h.nombre): f"{h.nombre} ({h.codigo or 'sin código'})" for h in resultados}
    claves = list(etiquetas)
    actual = st.session_state.get("hotel_clave")
    elegido = st.selectbox(
        "Hoteles encontrados", claves, format_func=etiquetas.get,
        index=claves.index(actual) if actual in claves else 0)
    hotel = next(h for h in resultados if (h.codigo or h.nombre) == elegido)

    _render_ficha(hotel)
    if not hotel.procesable:
        st.error("Este hotel no tiene código de supplier en el registro: no se puede procesar. "
                 "Completá la columna «Código hotel» en el Sheet y recargá.")
        return
    if st.button("Elegir este hotel y continuar ➜", type="primary"):
        if st.session_state.get("hotel_clave") != elegido:
            _resetear_pedido()
        st.session_state["hotel_clave"] = elegido
        _ir("fechas")


def _render_ficha(hotel):
    st.markdown(f"### {hotel.nombre}  ·  `{hotel.codigo or 'sin código'}`")
    filas = [{
        "Allocation": a.codigo,
        "Descripción": a.descripcion,
        "Habitación linkeada": a.habitacion or "(allocation vacía)",
        "Cierra tarifa": "SI" if a.cierra_tarifa else "NO",
        "Vigente hasta": a.vigente_hasta_txt or "—",
    } for a in hotel.allocations]
    st.dataframe(filas, use_container_width=True, hide_index=True)
    notas = [f"**{a.codigo}**: {a.notas}" for a in hotel.allocations if a.notas]
    if notas:
        st.caption("Notas — " + " · ".join(notas))


# ── Pantalla 2: fechas y alcance ──────────────────────────────────────────

def _resetear_pedido():
    for k in ("sel_fechas", "texto_fechas", "_nuevo_texto", "cal_last", "todas", "revisado", "origen"):
        st.session_state.pop(k, None)
    for k in [k for k in st.session_state if k.startswith("alloc_")]:
        del st.session_state[k]


def _texto_cambio():
    res = fch.interpretar(st.session_state.get("texto_fechas", ""), hoy())
    st.session_state["sel_fechas"] = res.fechas
    st.session_state["avisos_texto"] = res


def render_fechas():
    hotel = _hotel_elegido()
    if hotel is None:
        st.info("Primero elegí un hotel en «1 · Buscar hotel».")
        return
    st.subheader("Fechas y alcance")
    st.markdown(f"**{hotel.nombre}** · `{hotel.codigo}`")

    # Un cambio hecho desde el calendario se aplica al campo de texto ANTES de
    # crearlo (Streamlit no deja escribir un widget ya instanciado en esta corrida).
    if "_nuevo_texto" in st.session_state:
        st.session_state["texto_fechas"] = st.session_state.pop("_nuevo_texto")
    st.session_state.setdefault("sel_fechas", [])

    st.text_input(
        "Fechas (atajos)", key="texto_fechas", on_change=_texto_cambio,
        placeholder="20-23/10, 5/11, 18-19/11",
        help="Días sueltos o rangos, separados por coma. Se sincroniza con el calendario. "
             "Sin año: este año, o el próximo si el mes ya pasó.")

    sel = st.session_state["sel_fechas"]
    val = _calendario(
        seleccion=[f.isoformat() for f in sel], hoy=hoy().isoformat(),
        tope=fch.limite_futuro(hoy()).isoformat(), key="calendario", default=None)
    if val is not None and val != st.session_state.get("cal_last"):
        st.session_state["cal_last"] = val
        nuevas = [date.fromisoformat(s) for s in val["sel"]]
        st.session_state["sel_fechas"] = fch.clasificar(nuevas, hoy())[0]
        st.session_state["_nuevo_texto"] = fch.a_atajos(st.session_state["sel_fechas"], hoy())
        st.session_state.pop("avisos_texto", None)
        st.rerun()

    avisos = st.session_state.get("avisos_texto")
    if avisos:
        if avisos.errores:
            st.error("No entendí: " + ", ".join(avisos.errores))
        if avisos.descartadas_pasadas:
            st.warning(f"Se descartaron {len(avisos.descartadas_pasadas)} fecha(s) pasada(s) "
                       f"(hoy cuenta como vigente): {', '.join(fmt_rangos(avisos.descartadas_pasadas))}")
        if avisos.rechazadas_lejanas:
            st.warning(f"Se rechazaron {len(avisos.rechazadas_lejanas)} fecha(s) a más de 2 años de hoy: "
                       f"{', '.join(fmt_rangos(avisos.rechazadas_lejanas))}")

    if sel:
        st.success(f"**{len(sel)} día(s)**: " + " · ".join(fmt_rangos(sel)))
    else:
        st.caption("Todavía no hay fechas elegidas.")

    st.markdown("#### Allocations")
    todas = st.checkbox("Todas las allocations del hotel", key="todas",
                        help="Se carga una sola vez para todas las del registro.")
    elegidas = []
    for a in hotel.allocations:
        habitacion = a.habitacion or "allocation vacía"
        vig = a.vigente_hasta_txt or "sin dato"
        if todas:
            marcada = st.checkbox(f"**{a.codigo}** — {a.descripcion}", value=True, disabled=True,
                                  key=f"alloc_todas_{a.codigo}")
        else:
            marcada = st.checkbox(f"**{a.codigo}** — {a.descripcion}", key=f"alloc_{a.codigo}")
        st.caption(f"Habitación: {habitacion} · Vigente hasta: {vig}"
                   + (" · Cierra tarifa" if a.cierra_tarifa else ""))
        if todas or marcada:
            elegidas.append(a)
    st.session_state["alloc_elegidas"] = [a.codigo for a in elegidas]

    for a in elegidas:
        if a.vigente_hasta and not a.vacia:
            despues = [f for f in sel if f > a.vigente_hasta]
            if despues:
                st.info(f"**{a.codigo}**: {len(despues)} fecha(s) posterior(es) a «Vigente hasta» "
                        f"({fmt_fecha(a.vigente_hasta)}): en allocation no se tocan"
                        + ("; en tarifas sí se cierran." if a.cierra_tarifa else "."))

    puede = bool(sel) and bool(elegidas) and not _por_definir(elegidas)
    if _por_definir(elegidas):
        st.error("No se puede continuar: " + ", ".join(a.codigo for a in _por_definir(elegidas))
                 + " cierra tarifa pero su alcance está en REVISAR (falta definir qué habitaciones). "
                 "Completá «Tarifas a cerrar» en el registro y recargá.")
    if st.button("Continuar ➜", type="primary", disabled=not puede):
        _ir("revisar")
    if not puede:
        st.caption("Elegí al menos una fecha y una allocation para continuar.")


# ── Pantalla 3: revisar y enviar ──────────────────────────────────────────

def _por_definir(elegidas):
    """Allocations que cierran tarifa pero cuyo alcance sigue en REVISAR: no se pueden enviar."""
    return [a for a in elegidas if a.cierra_tarifa and a.tarifas.strip().upper() == "REVISAR"]


def _plan_texto(hotel, elegidas):
    """Qué va a hacer el script, en lenguaje llano."""
    lineas = []
    for a in elegidas:
        if a.vacia:
            lineas.append(f"**{a.codigo}**: allocation vacía, no hay nada que cerrar en allocation (solo tarifas).")
        else:
            lineas.append(f"**{a.codigo}** ({a.habitacion}): cierra las fechas en la allocation (Max / Release).")
    con_tarifa = [a for a in elegidas if a.cierra_tarifa]
    if not con_tarifa:
        lineas.append("**Tarifas**: este alcance no cierra tarifa.")
    else:
        alcance = set()
        for a in con_tarifa:
            t = a.tarifas.strip().upper()
            alcance.add("las habitaciones HT del hotel, excepto " + ", ".join(sorted(EXCLUDED_OPTIONS))
                        if t == "TODAS" else
                        "la habitación linkeada" if t == "LINKEADA" else a.tarifas)
        lineas.append("**Tarifas**: cierra períodos en Rates (Manual/Closed y tarifa en 0) de: "
                      + " + ".join(sorted(alcance)) + ".")
    return lineas


def render_revisar():
    hotel = _hotel_elegido()
    sel = st.session_state.get("sel_fechas", [])
    cods = st.session_state.get("alloc_elegidas", [])
    if hotel is None or not sel or not cods:
        st.info("Completá antes «Fechas y alcance».")
        return
    elegidas = [a for a in hotel.allocations if a.codigo in cods]
    todas = bool(st.session_state.get("todas"))

    st.subheader("Revisar y enviar")
    st.markdown(f"**Hotel:** {hotel.nombre} · `{hotel.codigo}`")
    st.markdown("**Allocations:** " + (ALLOCATIONS_TODAS.title() + " (" + ", ".join(cods) + ")" if todas else ", ".join(cods)))
    st.markdown(f"**Fechas ({len(sel)} día(s)):**")
    for r in fmt_rangos(sel):
        st.markdown(f"- {r}")
    st.markdown("**Qué va a hacer el script:**")
    for l in _plan_texto(hotel, elegidas):
        st.markdown(f"- {l}")

    modo_label = st.radio("Modo", [l for l, _ in MODOS], index=0, key="modo_pedido")
    modo = dict(MODOS)[modo_label]
    entorno = user_config.cargar()["entorno"]
    if modo == MODO_APLICAR:
        st.warning(f"Modo aplicar: el script va a escribir en Tourplan ({entorno.upper()}). "
                   "Tourplan no permite deshacer fácilmente y el script nunca reabre una fecha.")
    origen = st.text_input("Origen (asunto o remitente del mail, opcional)", key="origen")
    revisado = st.checkbox("Revisé las fechas contra el mail", key="revisado")

    cfg = user_config.cargar()
    nombre = cfg["nombre"] or cfg["tp_usuario"]
    if not nombre:
        st.warning("Cargá tu nombre en ⚙️ Configuración para que figure en «Cargado por».")

    por_definir = _por_definir(elegidas)
    if por_definir:
        st.error("No se puede enviar: " + ", ".join(a.codigo for a in por_definir)
                 + " tiene el alcance de tarifas en REVISAR. Definilo en el registro y recargá.")
    col_a, col_b = st.columns(2)
    with col_a:
        enviar = st.button("Enviar a la cola", type="primary", use_container_width=True,
                           disabled=not (revisado and nombre) or bool(por_definir))
    with col_b:
        st.button("Enviar y ejecutar", use_container_width=True, disabled=True,
                  help="Disponible en una etapa posterior (todavía no hay ejecución con Selenium).")

    if enviar:
        try:
            valores = cola.armar_pedido(
                codigo_hotel=hotel.codigo, allocations=cods, todas=todas, fechas=sel,
                cargado_por=nombre, modo=modo, origen=origen)
            with st.spinner("Escribiendo en la cola..."):
                fila = cola.enviar_pedido(_conectar(HOJA_COLA), valores)
        except Exception as e:
            st.error(f"No se pudo enviar el pedido: {e}")
            return
        _resetear_pedido()
        st.session_state["ultimo_envio"] = f"Pedido {valores[cola.C_ID]} enviado a la cola (fila {fila})."
        _ir("cola")


# ── Pantalla 4: cola ──────────────────────────────────────────────────────

def _nombre_hotel(codigo):
    """Nombre del hotel según el registro (la hoja COLA ya no trae esa columna)."""
    for h in st.session_state.get("registro", {}).get("hoteles", []):
        if h.codigo and h.codigo.upper() == (codigo or "").upper():
            return f"{h.nombre} ({codigo})"
    return codigo


def render_cola():
    st.subheader("Cola")
    if st.session_state.get("ultimo_envio"):
        st.success(st.session_state.pop("ultimo_envio"))
    col_r, col_e = st.columns(2)
    with col_r:
        refrescar = st.button("🔄 Refrescar", use_container_width=True)
    with col_e:
        st.button("Ejecutar pendientes", type="primary", use_container_width=True, disabled=True,
                  help="Disponible en una etapa posterior (todavía no hay ejecución con Selenium).")
    render_lectura_tourplan()
    st.divider()
    if refrescar or "cola_datos" not in st.session_state:
        try:
            with st.spinner("Leyendo la cola..."):
                st.session_state["cola_datos"] = cola.leer_cola(
                    _conectar(HOJA_COLA), user_config.cargar()["minutos_abandono"])
            st.session_state["cola_error"] = None
        except Exception as e:
            st.session_state["cola_error"] = str(e)
    if st.session_state.get("cola_error"):
        st.error(f"No pude leer la cola: {st.session_state['cola_error']}")
        return
    pedidos = st.session_state.get("cola_datos", [])
    if not pedidos:
        st.caption("La cola está vacía.")
        return
    conteo = {}
    for p in pedidos:
        conteo[p["estado"]] = conteo.get(p["estado"], 0) + 1
    cols = st.columns(max(len(conteo), 1))
    for c, (k, n) in zip(cols, sorted(conteo.items())):
        c.metric(k, n)
    st.dataframe([{
        "Pedido": p["id"], "Cargado": p["cargado"], "Por": p["cargado_por"],
        "Hotel": _nombre_hotel(p["hotel_codigo"]), "Allocations": p["allocations"],
        "Fechas": p["fechas"], "Modo": p["modo"], "Estado": p["estado"],
        "Allotment": (p["est_allotment"] + " " + p["obs_allotment"]).strip(),
        "Tarifa": (p["est_tarifa"] + " " + p["obs_tarifa"]).strip(),
        "En curso por": (p["tomado_por"] + " desde " + p["tomado_en"]
                         + (" ⚠️ ¿abandonado?" if p["abandonado"] else "")) if p["tomado_por"] else "",
    } for p in pedidos], use_container_width=True, hide_index=True)


# ── Lectura del plan en Tourplan (proceso hijo, etapa 2) ─────────────────

def _leer_proceso(proc, state):
    """Hilo aparte: lee el stdout del subproceso sin bloquear a Streamlit."""
    for line in proc.stdout:
        state["log_lines"].append(line)
    proc.wait()
    state["returncode"] = proc.returncode
    state["finished"] = True


def render_lectura_tourplan():
    st.markdown("#### Leer plan en Tourplan (solo lectura)")
    st.caption("Abre Tourplan, lee cada allocation de los pedidos PENDIENTE y deja el plan en "
               "OBSERVACIONES_CIERRE_ALLOTMENT. No escribe nada en Tourplan ni cambia el estado del pedido.")
    cfg = user_config.cargar()
    state = st.session_state.setdefault("_lectura", {
        "running": False, "finished": False, "log_lines": [], "returncode": None,
        "proc": None, "stop_file": None, "abort_requested": False})
    base_url = URLS_ENTORNO[cfg["entorno"]]
    if cfg["entorno"] == "produccion":
        st.warning("Entorno PRODUCCIÓN configurado. La lectura no escribe, pero ocupa una licencia real.")
    faltan = not (cfg["tp_usuario"] and cfg["tp_password"] and cfg["sheet_url"])
    if faltan:
        st.caption("Completá usuario/password de Tourplan y URL del Sheet en ⚙️ Configuración.")

    c1, c2 = st.columns(2)
    with c1:
        correr = st.button("Leer plan (lectura)", use_container_width=True,
                           disabled=state["running"] or faltan)
    with c2:
        abortar = st.button("⏹ Abortar", use_container_width=True,
                            disabled=not state["running"] or state["abort_requested"])
    if correr:
        run_dir = Path(tempfile.mkdtemp(prefix="allocation_"))
        (run_dir / "screenshots").mkdir()
        stop_file = run_dir / "ABORTAR.flag"
        env = os.environ.copy()
        env.update({
            "TOURPLAN_USERNAME": cfg["tp_usuario"], "TOURPLAN_PASSWORD": cfg["tp_password"],
            "TOURPLAN_BASE_URL": base_url, "TOURPLAN_SHEET_URL": cfg["sheet_url"],
            "TOURPLAN_CREDENTIALS_PATH": user_config.CREDENTIALS_PATH,
            "TOURPLAN_TOKEN_PATH": user_config.TOKEN_PATH,
            "TOURPLAN_HEADLESS": "1" if cfg["headless"] else "0",
            "TOURPLAN_VELOCIDAD": "1.5" if base_url == URL_PRODUCCION else "1.0",
            "TOURPLAN_SS_DIR": str(run_dir / "screenshots"), "TOURPLAN_STOP_FILE": str(stop_file),
            "TOURPLAN_MODO": MODO_LECTURA, "PYTHONPATH": str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", ""),
            "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"})
        proc = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "runner.py")], cwd=str(REPO_ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1)
        state.update({"running": True, "finished": False, "log_lines": [], "returncode": None,
                      "proc": proc, "stop_file": stop_file, "abort_requested": False})
        threading.Thread(target=_leer_proceso, args=(proc, state), daemon=True).start()
        st.rerun()
    if abortar:
        state["abort_requested"] = True
        try:
            state["stop_file"].touch()
        except Exception:
            pass
    if state["log_lines"]:
        st.code("".join(state["log_lines"][-300:]), language=None)
    if state["running"] and state["finished"]:
        state["running"] = False
        rc = state["returncode"]
        st.session_state.pop("cola_datos", None)  # fuerza releer la cola con las observaciones nuevas
        if rc == 0:
            st.success("Terminó OK. Refrescá la cola para ver el plan en OBSERVACIONES.")
        elif rc == ABORT_EXIT_CODE:
            st.info("⏸️ Abortado.")
        else:
            st.error(f"El proceso terminó con error (código {rc}). Revisá el log.")
    if state["running"]:
        time.sleep(1)
        st.rerun()


# ── Configuración ─────────────────────────────────────────────────────────

def render_configuracion():
    st.header("Configuración")
    st.caption("Se guarda en esta computadora (no se sube al repositorio ni se comparte).")
    cfg = user_config.cargar()
    with st.form("form_configuracion"):
        nombre = st.text_input("Tu nombre (aparece en «Cargado por» y «Tomado por»)", value=cfg["nombre"])
        sheet_url = st.text_input("URL del Google Sheet", value=cfg["sheet_url"])
        entorno = st.radio(
            "Entorno de Tourplan", ["test", "produccion"],
            index=0 if cfg["entorno"] == "test" else 1, horizontal=True,
            format_func=lambda e: f"{e.title()} — {URLS_ENTORNO[e]}")
        c1, c2 = st.columns(2)
        with c1:
            tp_usuario = st.text_input("Usuario Tourplan", value=cfg["tp_usuario"])
        with c2:
            tp_password = st.text_input("Password Tourplan", value=cfg["tp_password"], type="password")
        headless = st.checkbox("Correr Chrome sin ventana visible (headless)", value=bool(cfg["headless"]))
        minutos = st.number_input("Minutos para considerar un pedido EN CURSO como abandonado",
                                  min_value=1, value=int(cfg["minutos_abandono"]))
        if st.form_submit_button("Guardar", type="primary", use_container_width=True):
            user_config.guardar({
                "nombre": nombre, "sheet_url": sheet_url, "entorno": entorno,
                "tp_usuario": tp_usuario, "tp_password": tp_password,
                "headless": headless, "minutos_abandono": int(minutos)})
            st.success("Configuración guardada.")
    ruta = Path(user_config.CREDENTIALS_PATH)
    if ruta.exists():
        st.caption(f"Credenciales de Google (OAuth): `{ruta}`")
    else:
        st.warning(f"Falta el archivo de credenciales OAuth de Google: copialo a `{ruta}` (ver README).")


# ── Navegación ────────────────────────────────────────────────────────────

def render_sidebar():
    st.session_state.setdefault("pagina", "buscar")
    for clave, etiqueta in PAGINAS:
        if st.sidebar.button(etiqueta, key=f"nav_{clave}", use_container_width=True,
                             type="primary" if st.session_state["pagina"] == clave else "secondary"):
            _ir(clave)
    st.sidebar.divider()
    if st.sidebar.button("⚙️ Configuración", key="nav_config", use_container_width=True,
                         type="primary" if st.session_state["pagina"] == "config" else "secondary"):
        _ir("config")
    hotel = _hotel_elegido()
    if hotel:
        st.sidebar.caption(f"Hotel elegido: **{hotel.nombre}** ({hotel.codigo})")


def main():
    st.set_page_config(page_title="Cierre de allotment — Tourplan NX", layout="centered")
    st.title("Cierre de allotment y tarifas")
    entorno = user_config.cargar()["entorno"]
    if entorno == "produccion":
        st.error("Entorno configurado: PRODUCCIÓN")
    else:
        st.caption("Entorno configurado: Test")
    render_sidebar()
    {"buscar": render_buscar, "fechas": render_fechas, "revisar": render_revisar,
     "cola": render_cola, "config": render_configuracion}[st.session_state["pagina"]]()


if __name__ == "__main__":
    main()
