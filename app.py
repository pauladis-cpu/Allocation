"""Cierre de allotment y tarifas convenio — Tourplan NX.

App local (Streamlit) que corre en la PC de cada persona. Busca el hotel en el
registro (hoja ALLOCATIONS), arma el pedido (fechas + allocations) y lo escribe
en la cola (hoja COLA) del Google Sheet. «Leer plan (lectura)» abre Tourplan y
deja en OBSERVACIONES lo que se cerraría, sin escribir nada.

Interfaz: barra superior (Nuevo pedido / Cola / usuario) y un flujo de 3 pasos
(1 Hotel, 2 Fechas y alcance, 3 Revisar y enviar), según el esquema de pantallas.
Donde el esquema choca con lo que todavía no está implementado (aplicar en
Tourplan, toma de pedidos), se mantiene el comportamiento original: «Enviar y
ejecutar» y «Ejecutar pendientes» quedan deshabilitados y la lectura se lanza
desde el bloque «Leer plan en Tourplan» de la Cola.

La configuración (credenciales de Tourplan, URL del Sheet, entorno) se guarda por
PC en ~/.tourplan-allocation (ver common/user_config.py).
"""
import html
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
    EXCLUDED_OPTIONS, HOJA_ALLOCATIONS, HOJA_COLA, MODO_APLICAR, MODO_LECTURA,
    URLS_ENTORNO, URL_PRODUCCION,
)
from common import user_config
from common.sheets_client import conectar_sheets

REPO_ROOT = Path(__file__).resolve().parent

_calendario = components.declare_component(
    "calendario_fechas", path=str(REPO_ROOT / "components" / "calendario"))

INTERVALO_COLA = 10  # segundos entre lecturas automáticas de la hoja COLA

# Claves de widgets que deben sobrevivir al cambio de paso (Streamlit descarta el
# estado de los widgets que no se dibujan en una corrida).
_CLAVES_PERSISTENTES = ("texto_fechas", "origen", "revisado", "modo_pedido", "consulta")


def hoy():
    return date.today()


def fmt_fecha(f):
    return f.strftime("%d/%m/%Y")


def fmt_rangos(fechas):
    partes = []
    for a, b in fch.agrupar_rangos(fechas):
        partes.append(fmt_fecha(a) if a == b else f"{fmt_fecha(a)} al {fmt_fecha(b)}")
    return partes


def esc(txt):
    return html.escape(str(txt if txt is not None else ""))


# ── Estilos ───────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root { --acc:#1d5bbf; --acc-bg:#e6edfa; --bd:#e1e4e8; --mut:#6b7280; --ok:#1f7a45; --ok-bg:#e3f4ea; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], header[data-testid="stHeader"],
[data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
.stApp, .stApp p, .stApp label, .stApp input, .stApp button, .stApp textarea,
.stApp [data-testid="stMarkdownContainer"] { font-family:'IBM Plex Sans', system-ui, sans-serif; }
.block-container, [data-testid="stMainBlockContainer"] { max-width:100% !important; padding:0 0 3rem 0 !important; }
.stMain, [data-testid="stMain"], [data-testid="stAppViewContainer"] > section { padding-top:0 !important; }
/* los bloques <style> no ocupan espacio; el HTML crudo recupera el margen que Streamlit le resta */
[data-testid="stElementContainer"]:has(style) { display:none !important; }
[data-testid="stMarkdownContainer"] > div.ayuda, [data-testid="stMarkdownContainer"] > div.aviso-ambar,
[data-testid="stMarkdownContainer"] > div.noreg, [data-testid="stMarkdownContainer"] > div.resumen,
[data-testid="stMarkdownContainer"] > div.alloc-txt, [data-testid="stMarkdownContainer"] > div.res { margin-bottom:1rem; }
.mono, code, .stApp input.mono { font-family:'IBM Plex Mono', ui-monospace, monospace !important; }

/* barra superior */
.st-key-topbar { background:#fff; border-bottom:1px solid var(--bd); padding:0 3vw; min-height:60px; display:flex; flex-direction:column; justify-content:center; }
.st-key-topbar [data-testid="stHorizontalBlock"] { align-items:center; gap:.4rem; }
.st-key-topbar .titulo { font-size:1.2rem; font-weight:600; white-space:nowrap; }
.st-key-topbar button { border-radius:8px; font-weight:500; padding:.35rem 1rem; }
.st-key-topbar [data-testid="stBaseButton-primary"] { background:var(--acc-bg); color:var(--acc); border:none; box-shadow:none; }
.st-key-topbar [data-testid="stBaseButton-tertiary"] { color:#374151; }
.st-key-page { padding:22px 3vw 0 3vw; }
.entorno { font-size:.78rem; font-weight:600; padding:.2rem .6rem; border-radius:999px; background:#eceef1; color:#4b5563; }
.entorno.prod { background:#fde8e8; color:#9b1c1c; }

/* tarjetas */
[class*="st-key-card"] { background:#fff; border:1px solid var(--bd) !important; border-radius:14px; padding:.9rem 1.1rem; }
[class*="st-key-card"] [data-testid="stVerticalBlock"] { gap:.55rem; }
.st-key-card_ficha { min-height:560px; }
.etiqueta-seccion { font-size:.75rem; letter-spacing:.06em; text-transform:uppercase; color:var(--mut); font-weight:600; }
.ayuda { color:var(--mut); font-size:.85rem; line-height:1.35; }
.ayuda code { font-size:.8rem; }

/* indicador de pasos */
.pasos { display:flex; align-items:center; gap:14px; margin:4px 0 22px 0; font-size:1.02rem; }
.pasos .p { display:flex; align-items:center; gap:10px; color:var(--mut); }
.pasos .n { width:34px; height:34px; border-radius:50%; border:1.5px solid #c9ced6; display:flex; align-items:center; justify-content:center; font-weight:600; background:#fff; }
.pasos .p.act { color:var(--acc); font-weight:600; } .pasos .p.act .n { background:var(--acc); color:#fff; border-color:var(--acc); }
.pasos .p.ok { color:var(--ok); font-weight:600; } .pasos .p.ok .n { background:var(--ok); color:#fff; border-color:var(--ok); }
.pasos .linea { width:54px; height:1.5px; background:#c9ced6; }

/* paso 1: resultados y ficha */
[class*="st-key-res_"] { position:relative; }
[class*="st-key-res_"] button { position:absolute; inset:0; opacity:0; width:100%; height:100%; cursor:pointer; }
.res { background:#fff; border:1px solid var(--bd); border-radius:12px; padding:.8rem 1.1rem; display:flex; justify-content:space-between; align-items:center; gap:10px; }
.res.sel { border:2px solid var(--acc); }
.res .nom { font-weight:600; font-size:1.02rem; } .res .met { color:var(--mut); font-size:.88rem; }
.tag { font-size:.82rem; font-weight:600; padding:.18rem .65rem; border-radius:999px; white-space:nowrap; }
.tag.verde { background:var(--ok-bg); color:var(--ok); } .tag.gris { background:#eceef1; color:#4b5563; } .tag.ambar { background:#fdf0d5; color:#8a5a00; }
.noreg { background:#fdeeee; border:1px solid #f3c9c9; border-radius:12px; padding:.9rem 1.1rem; color:#7f1d1d; }
.noreg b { display:block; margin-bottom:.2rem; font-size:1.02rem; }
.ficha-cab { display:flex; justify-content:space-between; align-items:flex-start; border-bottom:1px solid var(--bd); padding-bottom:.8rem; margin-bottom:.4rem; }
.ficha-cab .nom { font-size:1.55rem; font-weight:600; line-height:1.2; }
.ficha-cab .cod { color:var(--mut); font-family:'IBM Plex Mono', monospace; }
.mini { border:1px solid var(--bd); border-radius:12px; padding:.75rem 1rem; margin-bottom:.6rem; line-height:1.55; }
.mini .t { font-weight:600; font-size:1.02rem; }
.mini .m { font-family:'IBM Plex Mono', monospace; color:var(--mut); font-size:.85rem; }

/* paso 2 */
.badge-verde { background:var(--ok-bg); color:var(--ok); font-weight:600; border-radius:10px; padding:.55rem .8rem; text-align:center; white-space:nowrap; }
.st-key-texto_fechas input, .st-key-origen input { font-family:'IBM Plex Mono', monospace; }
.st-key-origen input { font-family:'IBM Plex Sans', sans-serif; }
.alloc-txt .t { font-weight:600; line-height:1.3; } .alloc-txt .m { color:var(--mut); font-size:.88rem; line-height:1.4; }

/* paso 3 */
.resumen { display:grid; grid-template-columns:150px 1fr; row-gap:.75rem; align-items:baseline; }
.resumen .k { color:var(--mut); }
.rango { display:inline-block; background:var(--acc-bg); color:var(--acc); font-family:'IBM Plex Mono', monospace; font-size:.9rem; border-radius:8px; padding:.2rem .6rem; margin:0 .4rem .3rem 0; }
.paso-n { display:flex; gap:.8rem; margin:.6rem 0; line-height:1.5; }
.paso-n .num { flex:0 0 28px; height:28px; border-radius:50%; background:#eceef1; display:flex; align-items:center; justify-content:center; font-weight:600; font-size:.85rem; }
.aviso-ambar { background:#fdf0d5; color:#6b4500; border-radius:10px; padding:.8rem 1rem; }
.st-key-modo_pedido [data-testid="stBaseButton-segmented_control"], .st-key-modo_pedido [data-testid="stBaseButton-segmented_controlActive"] { font-family:'IBM Plex Mono', monospace; }

[class*="st-key-enviar_cola"] button:not(:disabled) { border-color:var(--acc); color:var(--acc); background:#fff; }

/* cola */
.st-key-cola_tabla { margin-top:.9rem; background:#fff; border:1px solid var(--bd); border-radius:14px; overflow-x:auto; }
table.cola { width:100%; border-collapse:collapse; font-size:.93rem; }
table.cola th { background:#f6f7f9; text-align:left; padding:.8rem 1rem; font-weight:600; border-bottom:1px solid var(--bd); white-space:nowrap; }
table.cola td { padding:.8rem 1rem; border-bottom:1px solid #eef0f2; vertical-align:top; }
table.cola tr:last-child td { border-bottom:none; }
table.cola .id, table.cola .modo { font-family:'IBM Plex Mono', monospace; } table.cola .id { color:var(--mut); }
table.cola .hotel { font-weight:600; } table.cola .obs { max-width:420px; color:#374151; } table.cola .na { color:#9ca3af; }
.pill { font-size:.8rem; font-weight:700; padding:.2rem .65rem; border-radius:999px; white-space:nowrap; display:inline-block; }
.pill.PENDIENTE { background:#e8eaee; color:#4b5563; } .pill.EN_CURSO { background:#e0e9fb; color:#1a3f8f; }
.pill.OK { background:var(--ok-bg); color:var(--ok); } .pill.SALTEADO { background:#fdeec8; color:#7a4e00; }
.pill.ERROR { background:#fbe1e1; color:#9b1c1c; } .pill.OTRO { background:#eceef1; color:#4b5563; }
"""


def _inyectar_css(extra=""):
    st.markdown(f"<style>{CSS}{extra}</style>", unsafe_allow_html=True)


def card(clave):
    """Tarjeta blanca con borde fino y esquinas redondeadas."""
    return st.container(border=False, key=f"card_{clave}")


# ── Acceso al Sheet ───────────────────────────────────────────────────────

def _conectar(hoja):
    cfg = user_config.cargar()
    if not cfg["sheet_url"]:
        raise ValueError("Falta la URL del Google Sheet en la Configuración.")
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


def _clave_hotel(h):
    return h.codigo or h.nombre


def _hotel_elegido():
    clave = st.session_state.get("hotel_clave")
    if clave is None:
        return None
    for h in st.session_state.get("registro", {}).get("hoteles", []):
        if _clave_hotel(h) == clave:
            return h
    return None


def _ir_paso(n):
    st.session_state["vista"] = "nuevo"
    st.session_state["paso"] = n


def _set_vista(v):
    st.session_state["vista"] = v


# ── Estado del pedido ─────────────────────────────────────────────────────

def _resetear_pedido():
    for k in ("sel_fechas", "texto_fechas", "_nuevo_texto", "cal_last", "revisado", "origen",
              "avisos_texto", "alloc_elegidas"):
        st.session_state.pop(k, None)
    for k in [k for k in st.session_state if k.startswith("chk_")]:
        del st.session_state[k]


def _elegir_hotel(clave):
    st.session_state["hotel_sel"] = clave


def _continuar_a_fechas(clave, hotel):
    """Confirma el hotel; si cambió, empieza un pedido nuevo con todas las allocations marcadas."""
    if st.session_state.get("hotel_clave") != clave:
        _resetear_pedido()
        st.session_state["hotel_clave"] = clave
        st.session_state["chk_todas"] = True
        for i in range(len(hotel.allocations)):
            st.session_state[f"chk_{i}"] = True
    _ir_paso(2)


def _on_todas(n):
    v = st.session_state["chk_todas"]
    for i in range(n):
        st.session_state[f"chk_{i}"] = v


def _on_alloc(n):
    st.session_state["chk_todas"] = all(st.session_state.get(f"chk_{i}") for i in range(n))


def _texto_cambio():
    res = fch.interpretar(st.session_state.get("texto_fechas", ""), hoy())
    st.session_state["sel_fechas"] = res.fechas
    st.session_state["avisos_texto"] = res


def _por_definir(elegidas):
    """Allocations que cierran tarifa pero cuyo alcance sigue en REVISAR: no se pueden enviar."""
    return [a for a in elegidas if a.cierra_tarifa and a.tarifas.strip().upper() == "REVISAR"]


def _habitacion_txt(a):
    return a.desc_habitacion or a.habitacion or a.codigo


def _tarifa_txt(a):
    return (a.tarifas if a.cierra_tarifa else "no cierra") or "—"


def _vigente_txt(a):
    return fmt_fecha(a.vigente_hasta) if a.vigente_hasta else (a.vigente_hasta_txt or "sin dato")


# ── Barra superior y pasos ────────────────────────────────────────────────

@st.dialog("Configuración")
def dialogo_configuracion():
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
            st.rerun()
    ruta = Path(user_config.CREDENTIALS_PATH)
    if ruta.exists():
        st.caption(f"Credenciales de Google (OAuth): `{ruta}`")
    else:
        st.warning(f"Falta el archivo de credenciales OAuth de Google: copialo a `{ruta}` (ver README).")


def render_topbar():
    cfg = user_config.cargar()
    vista = st.session_state["vista"]
    with st.container(key="topbar"):
        c_tit, c_nuevo, c_cola, c_esp, c_env, c_user = st.columns([2.3, 1.3, 0.8, 5, 1.1, 2.2])
        c_tit.markdown('<span class="titulo">Cierre de allotment</span>', unsafe_allow_html=True)
        c_nuevo.button("Nuevo pedido", key="tab_nuevo", use_container_width=True,
                       type="primary" if vista == "nuevo" else "tertiary",
                       on_click=_set_vista, args=("nuevo",))
        c_cola.button("Cola", key="tab_cola", use_container_width=True,
                      type="primary" if vista == "cola" else "tertiary",
                      on_click=_set_vista, args=("cola",))
        prod = cfg["entorno"] == "produccion"
        c_env.markdown(f'<span class="entorno{" prod" if prod else ""}">{"PRODUCCIÓN" if prod else "TEST"}</span>',
                       unsafe_allow_html=True)
        if c_user.button(f"{cfg['nombre'] or 'Usuario'}  ⚙", key="user_btn", type="tertiary",
                         use_container_width=True, help="Configuración"):
            dialogo_configuracion()
    # primera vez en esta PC: abre la configuración una sola vez
    if not (cfg["nombre"] and cfg["tp_usuario"]) and not st.session_state.get("_cfg_visto"):
        st.session_state["_cfg_visto"] = True
        dialogo_configuracion()


def render_pasos(paso, hotel):
    n = len(st.session_state.get("sel_fechas", []))
    def item(num, texto, estado):
        marca = "✓" if estado == "ok" else num
        return f'<div class="p {estado}"><span class="n">{marca}</span><span>{esc(texto)}</span></div>'
    partes = [
        item(1, hotel.nombre if (paso > 1 and hotel) else "Hotel", "ok" if paso > 1 else "act"),
        item(2, f"{n} fechas" if paso > 2 else "Fechas y alcance", "ok" if paso > 2 else ("act" if paso == 2 else "")),
        item(3, "Revisar y enviar", "act" if paso == 3 else ""),
    ]
    st.markdown('<div class="pasos">' + '<div class="linea"></div>'.join(partes) + "</div>",
                unsafe_allow_html=True)


# ── Paso 1: hotel ─────────────────────────────────────────────────────────

def _etiqueta_hotel(h):
    """(etiqueta, clase, texto secundario) según cómo responde el registro."""
    n = len(h.allocations)
    cod = f"{h.codigo} · {n} allocation{'s' if n != 1 else ''}"
    if not h.procesable:
        return "Falta el código", "ambar", "No se puede continuar con ese hotel"
    if all(a.vacia for a in h.allocations):
        extra = " · tarifa en todas las habitaciones" if any(a.tarifas.strip().upper() == "TODAS" for a in h.allocations) else ""
        return "Allocation vacía", "gris", f"Figura solo con su nombre{extra}"
    return "Tiene allocation", "verde", cod


def _ficha_html(hotel):
    n_con = sum(1 for a in hotel.allocations if not a.vacia)
    titulo = f"Habitaciones con allocation ({n_con})" if n_con else "Allocation vacía (solo se cierran tarifas)"
    out = [f'<div class="etiqueta-seccion">Ficha del registro</div>'
           f'<div class="ficha-cab"><div class="nom">{esc(hotel.nombre)}</div>'
           f'<div class="cod">{esc(hotel.codigo or "sin código")}</div></div>'
           f'<div style="font-weight:600;margin:.6rem 0">{esc(titulo)}</div>']
    for a in hotel.allocations:
        cab = "Allocation vacía" if a.vacia else _habitacion_txt(a)
        out.append(
            f'<div class="mini"><div class="t">{esc(cab)}</div>'
            f'<div class="m">{esc(a.descripcion or a.codigo)}</div>'
            f'<div>Cierra tarifa: {"SI" if a.cierra_tarifa else "NO"}'
            + (f' · tarifas a cerrar: {esc(a.tarifas)}' if a.cierra_tarifa else "") + '</div>'
            f'<div>Vigente hasta: {esc(_vigente_txt(a))}</div></div>')
    return "".join(out)


def render_hotel():
    reg = _cargar_registro()
    col_izq, col_der = st.columns([5, 6], gap="large")
    resultados = []
    with col_izq:
        with card("busqueda"):
            st.markdown("**Hotel**")
            consulta = st.text_input("Hotel", key="consulta", placeholder="Nombre o código",
                                     label_visibility="collapsed", icon=":material/search:")
            st.markdown('<div class="ayuda">Busca por nombre o código en la hoja ALLOCATIONS del registro. '
                        'No consulta Tourplan.</div>', unsafe_allow_html=True)
            if st.button("🔄 Recargar registro", key="recargar", type="tertiary",
                         help="Vuelve a leer la hoja ALLOCATIONS del Sheet."):
                _cargar_registro(forzar=True)
                st.rerun()
        if reg["error"]:
            st.error(f"No pude leer el registro: {reg['error']}")
            return
        dups = registro.duplicados(reg["allocs"])
        if dups:
            st.warning("Hay allocations repetidas en el registro (mismo hotel y código): "
                       + ", ".join(f"{h} / {c}" for h, c in dups))
        if not consulta.strip():
            st.markdown(f'<div class="ayuda">{len(reg["hoteles"])} hoteles en el registro. '
                        'Escribí un nombre o código para buscar.</div>', unsafe_allow_html=True)
        else:
            resultados = registro.buscar(reg["hoteles"], consulta)
            if not resultados:
                st.markdown(
                    '<div class="noreg"><b>No está en el registro</b>Se entiende que no tiene allocation ni '
                    'cierra tarifa convenio. Ante la duda, verificalo en Tourplan y agregalo a la hoja '
                    'ALLOCATIONS.</div>', unsafe_allow_html=True)
            else:
                claves = [_clave_hotel(h) for h in resultados]
                sel = st.session_state.get("hotel_sel")
                if sel not in claves:
                    sel = claves[0]
                    st.session_state["hotel_sel"] = sel
                st.markdown('<div class="etiqueta-seccion" style="margin-top:.4rem">Resultados</div>',
                            unsafe_allow_html=True)
                for i, h in enumerate(resultados):
                    texto, clase, sec = _etiqueta_hotel(h)
                    with st.container(key=f"res_{i}"):
                        st.markdown(
                            f'<div class="res{" sel" if _clave_hotel(h) == sel else ""}"><div>'
                            f'<div class="nom">{esc(h.nombre)}</div><div class="met mono">{esc(sec)}</div></div>'
                            f'<span class="tag {clase}">{texto}</span></div>', unsafe_allow_html=True)
                        st.button("Elegir", key=f"elegir_{i}", on_click=_elegir_hotel, args=(_clave_hotel(h),))
    with col_der:
        with card("ficha"):
            hotel = next((h for h in resultados if _clave_hotel(h) == st.session_state.get("hotel_sel")), None)
            if hotel is None:
                st.markdown('<div class="etiqueta-seccion">Ficha del registro</div>'
                            '<div class="ayuda" style="margin-top:.6rem">Buscá un hotel y elegilo para ver '
                            'sus allocations.</div>', unsafe_allow_html=True)
            else:
                st.markdown(_ficha_html(hotel), unsafe_allow_html=True)
                if not hotel.procesable:
                    st.error("Este hotel no tiene código de supplier en el registro: no se puede continuar. "
                             "Completá la columna «Código hotel» en el Sheet y recargá.")
            st.markdown('<div style="height:2rem"></div>', unsafe_allow_html=True)
            _, c_btn = st.columns([2, 1.3])
            c_btn.button("Continuar a fechas", type="primary", use_container_width=True,
                         disabled=hotel is None or not hotel.procesable, key="continuar_fechas",
                         on_click=_continuar_a_fechas if hotel else None,
                         args=(_clave_hotel(hotel), hotel) if hotel else None)


# ── Paso 2: fechas y alcance ──────────────────────────────────────────────

def _elegidas(hotel):
    return [a for i, a in enumerate(hotel.allocations) if st.session_state.get(f"chk_{i}")]


def render_fechas():
    hotel = _hotel_elegido()
    if hotel is None:
        _ir_paso(1)
        st.rerun()
    # Un cambio hecho desde el calendario se aplica al campo de texto ANTES de
    # crearlo (Streamlit no deja escribir un widget ya instanciado en esta corrida).
    if "_nuevo_texto" in st.session_state:
        st.session_state["texto_fechas"] = st.session_state.pop("_nuevo_texto")
    st.session_state.setdefault("sel_fechas", [])
    elegidas = _elegidas(hotel)
    sel = st.session_state["sel_fechas"]
    avisos = st.session_state.get("avisos_texto")
    n_alloc = len(hotel.allocations)

    col_izq, col_der = st.columns([2.4, 1], gap="large")
    with col_izq:
        with card("fechas"):
            st.markdown("**Escribir fechas**")
            if avisos and avisos.errores:
                st.markdown("<style>.st-key-texto_fechas input{border-color:#c0392b !important}</style>",
                            unsafe_allow_html=True)
            c_txt, c_n = st.columns([4, 1.3])
            with c_txt:
                st.text_input("Fechas", key="texto_fechas", on_change=_texto_cambio,
                              placeholder="20-23/10, 5/11, 18-19/11", label_visibility="collapsed")
            c_n.markdown(f'<div class="badge-verde">{len(sel)} fecha{"s" if len(sel) != 1 else ""} '
                         f'marcada{"s" if len(sel) != 1 else ""}</div>', unsafe_allow_html=True)
            st.markdown('<div class="ayuda">Atajos: <code>20-23/10</code> rango, <code>5/11</code> día suelto, '
                        'separados por coma. El texto marca el calendario y el calendario completa el texto.</div>',
                        unsafe_allow_html=True)
            if avisos:
                if avisos.errores:
                    st.error("No entendí: " + ", ".join(avisos.errores))
                if avisos.descartadas_pasadas:
                    st.warning(f"Se descartaron {len(avisos.descartadas_pasadas)} fecha(s) pasada(s) "
                               f"(hoy cuenta como vigente): {', '.join(fmt_rangos(avisos.descartadas_pasadas))}")
                if avisos.rechazadas_lejanas:
                    st.warning(f"Se rechazaron {len(avisos.rechazadas_lejanas)} fecha(s) a más de 2 años de hoy: "
                               f"{', '.join(fmt_rangos(avisos.rechazadas_lejanas))}")
            st.divider()
            tarde = sorted({f.isoformat() for a in elegidas if a.vigente_hasta and not a.vacia
                            for f in sel if f > a.vigente_hasta})
            val = _calendario(
                seleccion=[f.isoformat() for f in sel], hoy=hoy().isoformat(),
                tope=fch.limite_futuro(hoy()).isoformat(), tarde=tarde, key="calendario", default=None)
            if val is not None and val != st.session_state.get("cal_last"):
                st.session_state["cal_last"] = val
                nuevas = [date.fromisoformat(s) for s in val["sel"]]
                st.session_state["sel_fechas"] = fch.clasificar(nuevas, hoy())[0]
                st.session_state["_nuevo_texto"] = fch.a_atajos(st.session_state["sel_fechas"], hoy())
                st.session_state.pop("avisos_texto", None)
                st.rerun()

    with col_der:
        checked_css = []
        with card("todas"):
            st.markdown("**Habitaciones a cerrar**")
            st.checkbox(f"**Todas las habitaciones ({n_alloc})**", key="chk_todas",
                        on_change=_on_todas, args=(n_alloc,))
            st.markdown(f'<div class="ayuda" style="margin-top:-.4rem">Las mismas fechas para '
                        f'{"las dos" if n_alloc == 2 else "todas"}. Se carga una sola vez.</div>',
                        unsafe_allow_html=True)
        if st.session_state.get("chk_todas"):
            checked_css.append(".st-key-card_todas{border:2px solid #1d5bbf !important;background:#eef3fc !important}")
        for i, a in enumerate(hotel.allocations):
            with card(f"alloc_{i}"):
                c_chk, c_txt = st.columns([1, 9])
                c_chk.checkbox(a.codigo, key=f"chk_{i}", label_visibility="collapsed",
                               on_change=_on_alloc, args=(n_alloc,))
                c_txt.markdown(
                    f'<div class="alloc-txt"><div class="t">{esc(a.descripcion or a.codigo)}</div>'
                    f'<div class="m mono">{esc(a.codigo)} · {esc(_habitacion_txt(a) if not a.vacia else "allocation vacía")}'
                    f' · tarifa: {esc(_tarifa_txt(a))}</div>'
                    f'<div class="m">Vigente hasta {esc(_vigente_txt(a))}</div></div>', unsafe_allow_html=True)
        if checked_css:
            st.markdown(f"<style>{''.join(checked_css)}</style>", unsafe_allow_html=True)
        st.markdown(
            '<div class="ayuda">Destildá una para cargar solo la otra. Si el hotel tiene una sola allocation, '
            'viene preseleccionada. La descripción de cada allocation viene del registro y suele traer '
            'indicaciones para cerrarla. Las fechas posteriores a «Vigente hasta» se informan: en allocation '
            'no se tocan y en tarifas sí se cierran.</div>', unsafe_allow_html=True)
        por_definir = _por_definir(elegidas)
        if por_definir:
            st.error("No se puede continuar: " + ", ".join(a.codigo for a in por_definir)
                     + " cierra tarifa pero su alcance está en REVISAR (falta definir qué habitaciones). "
                     "Completá «Tarifas a cerrar» en el registro y recargá.")
        with card("origen"):
            st.markdown("**Origen (opcional)**")
            st.text_input("Origen", key="origen", placeholder="Asunto o remitente del mail",
                          label_visibility="collapsed")
            st.markdown('<div class="ayuda">Queda en la cola para poder volver al mail.</div>',
                        unsafe_allow_html=True)
        puede = bool(sel) and bool(elegidas) and not por_definir
        c_vol, c_cont = st.columns(2)
        c_vol.button("Volver", key="vol_1", use_container_width=True, on_click=_ir_paso, args=(1,))
        c_cont.button("Continuar", key="cont_3", type="primary", use_container_width=True,
                      disabled=not puede, on_click=_ir_paso, args=(3,))
        if not puede and not por_definir:
            st.markdown('<div class="ayuda">Elegí al menos una fecha y una habitación para continuar.</div>',
                        unsafe_allow_html=True)


# ── Paso 3: revisar y enviar ──────────────────────────────────────────────

def _paso_allocation_html(elegidas):
    vacias = [a for a in elegidas if a.vacia]
    if len(vacias) == len(elegidas):
        return ("<b>Allocation.</b> Las allocations elegidas están vacías: no hay nada que cerrar en allocation, "
                "solo tarifas.")
    txt = ("<b>Allocation.</b> Por cada fecha lee Used. Con Used en cero pone Max en 0. Con Used mayor a cero "
           "iguala Max a Used (aunque Max sea menor) y pone Release en 9999. Se repite en cada habitación "
           "elegida. Las fechas ya cerradas se saltean y nunca se reabre.")
    if vacias:
        txt += f" {esc(', '.join(a.codigo for a in vacias))} está vacía y se saltea en allocation."
    return txt


def _paso_tarifa_html(elegidas):
    con = [a for a in elegidas if a.cierra_tarifa]
    if not con:
        return "<b>Tarifa convenio.</b> No cierra tarifa."
    alcance = []
    for a in con:
        t = a.tarifas.strip().upper()
        if t == "LINKEADA":
            alcance.append("la habitación linkeada de cada allocation")
        elif t == "TODAS":
            alcance.append("todas las habitaciones HT del hotel, excepto " + " y ".join(sorted(EXCLUDED_OPTIONS)))
        else:
            alcance.append(f"las habitaciones {a.tarifas}")
    unicos = list(dict.fromkeys(alcance))
    return ("<b>Tarifa convenio.</b> Cierra la tarifa de " + esc(" y de ".join(unicos)) + ", con un período por "
            "rango y la tarifa en 0. Status Manual para TR, ND y EM, y Closed para el resto. Lo que ya está "
            "cerrado se saltea, y un período en Closed nunca pasa a Manual.")


def render_revisar():
    hotel = _hotel_elegido()
    sel = st.session_state.get("sel_fechas", [])
    elegidas = _elegidas(hotel) if hotel else []
    if hotel is None or not sel or not elegidas:
        _ir_paso(1 if hotel is None else 2)
        st.rerun()
    todas = len(elegidas) == len(hotel.allocations)
    cods = [a.codigo for a in elegidas]
    cfg = user_config.cargar()
    nombre = cfg["nombre"] or cfg["tp_usuario"]
    origen = st.session_state.get("origen", "")
    rangos = fch.agrupar_rangos(sel)

    col_izq, col_der = st.columns([2.4, 1], gap="large")
    with col_izq:
        with card("resumen"):
            st.markdown('<div class="etiqueta-seccion">Resumen del pedido</div>', unsafe_allow_html=True)
            nombres = [_habitacion_txt(a) if not a.vacia else a.codigo for a in elegidas]
            habs = (f"Todas ({len(elegidas)}): " + " y ".join(nombres)) if todas else ", ".join(nombres)
            chips = "".join(
                f'<span class="rango">{a:%d/%m} al {b:%d/%m}</span>' if a != b else f'<span class="rango">{a:%d/%m}</span>'
                for a, b in rangos)
            st.markdown(
                '<div class="resumen">'
                f'<div class="k">Hotel</div><div><b>{esc(hotel.nombre)}</b> <span class="mono ayuda">{esc(hotel.codigo)}</span></div>'
                f'<div class="k">Habitaciones</div><div>{esc(habs)}</div>'
                f'<div class="k">Fechas a cerrar</div><div>{chips}<span class="ayuda">{len(rangos)} '
                f'rango{"s" if len(rangos) != 1 else ""} · {len(sel)} fecha{"s" if len(sel) != 1 else ""}</span></div>'
                f'<div class="k">Origen</div><div>{esc(origen) if origen else "<span class=ayuda>—</span>"}</div>'
                '</div>', unsafe_allow_html=True)
            for a in elegidas:
                if a.vigente_hasta and not a.vacia:
                    despues = [f for f in sel if f > a.vigente_hasta]
                    if despues:
                        st.markdown(
                            f'<div class="aviso-ambar">{esc(a.codigo)}: {len(despues)} fecha(s) posteriores a la '
                            f'vigencia ({fmt_fecha(a.vigente_hasta)}): en allocation no se tocan'
                            f'{", en tarifas sí se cierran" if a.cierra_tarifa else ""}.</div>',
                            unsafe_allow_html=True)
            st.divider()
            st.markdown("**Qué va a hacer el script**")
            for n, txt in enumerate([_paso_allocation_html(elegidas), _paso_tarifa_html(elegidas)], start=1):
                st.markdown(f'<div class="paso-n"><div class="num">{n}</div><div>{txt}</div></div>',
                            unsafe_allow_html=True)

    with col_der:
        with card("modo"):
            st.markdown("**Modo**")
            modo = st.segmented_control("Modo", [MODO_LECTURA, MODO_APLICAR], default=MODO_LECTURA,
                                        required=True, key="modo_pedido", label_visibility="collapsed",
                                        width="stretch")
            st.markdown('<div class="ayuda">En lectura el script muestra qué cerraría sin escribir nada en '
                        'Tourplan. Conviene empezar por ahí y recién después aplicar.</div>',
                        unsafe_allow_html=True)
            if modo == MODO_APLICAR:
                st.warning(f"Modo aplicar: el script va a escribir en Tourplan ({cfg['entorno'].upper()}). "
                           "Tourplan no permite deshacer fácilmente y el script nunca reabre una fecha.")
        with card("revision"):
            revisado = st.checkbox("Revisé las fechas contra el mail original.", key="revisado")
        st.markdown('<div class="aviso-ambar">Hoy cuenta como fecha vigente. Las fechas anteriores a hoy se '
                    'descartan antes de enviar.</div>', unsafe_allow_html=True)
        if not nombre:
            st.warning("Cargá tu nombre en la Configuración (arriba a la derecha) para que figure en «Cargado por».")
        st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)
        c_vol, c_cola = st.columns(2)
        c_vol.button("Volver", key="vol_2", use_container_width=True, on_click=_ir_paso, args=(2,))
        enviar = c_cola.button("Enviar a la cola", key="enviar_cola", use_container_width=True,
                               disabled=not (revisado and nombre))
        st.button("Enviar y ejecutar", key="enviar_ejecutar", type="primary", use_container_width=True,
                  disabled=True,
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
        for k in ("hotel_clave", "hotel_sel"):
            st.session_state.pop(k, None)
        st.session_state["consulta"] = ""
        st.session_state["aviso"] = f"Pedido {valores[cola.C_ID]} enviado a la cola (fila {fila})."
        st.session_state.pop("cola_datos", None)
        _ir_paso(1)
        st.rerun()


# ── Cola ──────────────────────────────────────────────────────────────────

def _nombre_hotel(codigo):
    """Nombre del hotel según el registro (la hoja COLA ya no trae esa columna)."""
    for h in st.session_state.get("registro", {}).get("hoteles", []):
        if h.codigo and h.codigo.upper() == (codigo or "").upper():
            return h.nombre
    return codigo


def _habitaciones_cola(p):
    """Traduce los códigos de allocation de la COLA a la habitación (según ALLOCATIONS)."""
    del_hotel = [a for a in st.session_state.get("registro", {}).get("allocs", [])
                 if a.codigo_hotel.upper() == (p["hotel_codigo"] or "").upper()]
    if not del_hotel:
        return p["allocations"], []
    elegidas, faltan = registro.resolver_allocations(p["allocations"], del_hotel)
    if registro.normalizar(p["allocations"]) == "todas":
        return f"Todas ({len(elegidas)})", elegidas
    nombres = [_habitacion_txt(a) if not a.vacia else a.codigo for a in elegidas] + faltan
    return ", ".join(nombres), elegidas


def _pill(estado_crudo):
    clase = cola.clasificar_estado(estado_crudo).replace(" ", "_")
    return f'<span class="pill {esc(clase)}">{esc((estado_crudo or "PENDIENTE").strip() or "PENDIENTE")}</span>'


def _fila_cola_html(p):
    habs, elegidas = _habitaciones_cola(p)
    registro_ok = bool(elegidas)
    na_allot = registro_ok and all(a.vacia for a in elegidas) and cola.clasificar_estado(p["est_allotment"]) == "PENDIENTE"
    na_tarifa = registro_ok and not any(a.cierra_tarifa for a in elegidas) and cola.clasificar_estado(p["est_tarifa"]) == "PENDIENTE"
    if p["tomado_por"] and p["estado"] == "EN CURSO":
        obs = f"Tomado por {p['tomado_por']}" + (" ⚠️ ¿abandonado?" if p["abandonado"] else "")
    else:
        obs = " · ".join(t for t in (p["obs_allotment"], p["obs_tarifa"]) if t)
    na = '<span class="na">no aplica</span>'
    return (f'<tr><td class="id">{esc(p["id"])}</td><td class="hotel">{esc(_nombre_hotel(p["hotel_codigo"]))}</td>'
            f'<td>{esc(habs)}</td><td>{esc(p["cant"])}</td><td class="modo">{esc(p["modo"])}</td>'
            f'<td>{na if na_allot else _pill(p["est_allotment"])}</td>'
            f'<td>{na if na_tarifa else _pill(p["est_tarifa"])}</td><td class="obs">{esc(obs)}</td></tr>')


def _cola_datos(forzar=False):
    """Lee COLA como mucho cada INTERVALO_COLA segundos (el resto de las corridas reutiliza lo leído)."""
    ss = st.session_state
    if forzar or "cola_datos" not in ss or time.time() - ss.get("cola_ts", 0) >= INTERVALO_COLA:
        try:
            ss["cola_datos"] = cola.leer_cola(_conectar(HOJA_COLA), user_config.cargar()["minutos_abandono"])
            ss["cola_error"] = None
        except Exception as e:
            ss["cola_error"] = str(e)
        ss["cola_ts"] = time.time()
    return ss.get("cola_datos", [])


@st.fragment(run_every=INTERVALO_COLA)
def _tabla_cola():
    pedidos = _cola_datos()
    if st.session_state.get("cola_error"):
        st.error(f"No pude leer la cola: {st.session_state['cola_error']}")
        return
    filtro = st.session_state.get("filtro_cola") or "Todos"
    if filtro == "Pendientes":
        pedidos = [p for p in pedidos if p["estado"] == "PENDIENTE"]
    elif filtro == "Con error":
        pedidos = [p for p in pedidos if p["estado"] == "ERROR"]
    with st.container(key="cola_tabla"):
        if not pedidos:
            st.markdown('<div class="ayuda" style="padding:1rem">No hay pedidos para mostrar.</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(
                '<table class="cola"><thead><tr><th>ID_PEDIDO</th><th>Hotel</th><th>Habitaciones</th><th>Fechas</th>'
                '<th>MODO</th><th>Allotment</th><th>Tarifa</th><th>Observaciones</th></tr></thead><tbody>'
                + "".join(_fila_cola_html(p) for p in pedidos) + "</tbody></table>", unsafe_allow_html=True)


def render_cola():
    _cargar_registro()
    c_tit, c_fil, c_ref, c_ej = st.columns([4, 3, 0.8, 1.7])
    c_tit.markdown('<div style="font-size:1.7rem;font-weight:600">Cola de pedidos</div>'
                   '<div class="ayuda">Esta vista solo lee la pestaña COLA del Sheet.</div>', unsafe_allow_html=True)
    with c_fil:
        st.segmented_control("Filtro", ["Todos", "Pendientes", "Con error"], default="Todos",
                             required=True, key="filtro_cola", label_visibility="collapsed")
    if c_ref.button("🔄", key="refrescar_cola", help="Leer la cola ahora"):
        _cola_datos(forzar=True)
    c_ej.button("Ejecutar pendientes", type="primary", use_container_width=True, disabled=True,
                key="ejecutar_pendientes",
                help="Disponible en una etapa posterior (todavía no hay toma de pedidos con Selenium).")
    _tabla_cola()
    st.markdown('<div class="ayuda" style="margin-top:.6rem">Estados: PENDIENTE, EN CURSO, OK, SALTEADO o ERROR '
                'con detalle. EN CURSO: lo está ejecutando una PC. &nbsp;&nbsp; El script no frena el lote por un '
                f'error puntual y se puede retomar. La vista se actualiza sola cada {INTERVALO_COLA} segundos.</div>',
                unsafe_allow_html=True)
    st.markdown('<div style="height:1.2rem"></div>', unsafe_allow_html=True)
    with card("lectura"):
        render_lectura_tourplan()


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
        st.caption("Completá usuario/password de Tourplan y URL del Sheet en la Configuración (arriba a la derecha).")

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
            st.success("Terminó OK. La cola se actualiza sola: el plan queda en Observaciones.")
        elif rc == ABORT_EXIT_CODE:
            st.info("⏸️ Abortado.")
        else:
            st.error(f"El proceso terminó con error (código {rc}). Revisá el log.")
    if state["running"]:
        time.sleep(1)
        st.rerun()


# ── Programa principal ────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Cierre de allotment — Tourplan NX", layout="wide",
                       initial_sidebar_state="collapsed")
    _inyectar_css()
    st.session_state.setdefault("vista", "nuevo")
    st.session_state.setdefault("paso", 1)
    # mantiene vivo el estado de los widgets que no se dibujan en el paso actual
    for k in list(st.session_state):
        if k in _CLAVES_PERSISTENTES or k.startswith("chk_"):
            st.session_state[k] = st.session_state[k]
    render_topbar()
    with st.container(key="page"):
        if st.session_state["vista"] == "cola":
            render_cola()
        else:
            if st.session_state.get("aviso"):
                st.success(st.session_state.pop("aviso"))
            paso = st.session_state["paso"]
            if paso > 1 and _hotel_elegido() is None:
                paso = st.session_state["paso"] = 1
            render_pasos(paso, _hotel_elegido())
            {1: render_hotel, 2: render_fechas, 3: render_revisar}[paso]()


if __name__ == "__main__":
    main()
