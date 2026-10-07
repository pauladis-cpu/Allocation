"""Prueba del JS de tourplan_flujos/allocations.py contra un DOM SIMULADO (no es Tourplan):
diálogo de allocation, tabla 'Services Included' y una grilla de días virtual de 35 px
por fila. Sirve para atrapar errores del código (scroll, lectura por etiqueta, Release
con separador de miles). Requiere playwright y la variable CHROME_BIN; si no, se saltea."""
import os
from datetime import date, timedelta

import pytest

pytest.importorskip("playwright.sync_api")
CHROME = os.environ.get("CHROME_BIN")
if not CHROME:
    pytest.skip("CHROME_BIN no definido", allow_module_level=True)
os.environ.setdefault("TOURPLAN_VELOCIDAD", "0.4")

from playwright.sync_api import sync_playwright  # noqa: E402

from allocation.plan import DiaAllocation, planear, CERRAR, YA_CERRADA, SIN_FILA  # noqa: E402
from tourplan_flujos import allocations as fl  # noqa: E402

N_DIAS = 800
BASE = date(2026, 10, 5)

HTML = r"""
<html><body>
<tp-grid tpid="allocations-grid"><table><tbody>
  <tr><td class="tpcol-name"> ST </td><td class="tpcol-description">Standard  CIERRA DATABASE</td></tr>
  <tr><td class="tpcol-name">ST</td><td class="tpcol-description">Otra</td></tr>
  <tr><td class="tpcol-name">DUP</td><td class="tpcol-description">Igual</td></tr>
  <tr><td class="tpcol-name">DUP</td><td class="tpcol-description">igual</td></tr>
</tbody></table></tp-grid>
<tp-dialog><div class="tpmodal-allocation"><h3>Allocation Detail - ST</h3>
  <div class="buttons">
    <tp-button class="cancel"><button id="exit">Exit</button></tp-button>
    <tp-button class="discard"><button id="discard" disabled>Discard</button></tp-button>
    <tp-button class="save"><button id="save" disabled>Save</button></tp-button>
  </div>
  <div id="days-tab">
    <div class="filtercols">
      <tp-date id="datefrom"><input type="hidden" class="tphidden" value="05/Oct/2026"><input type="text" class="tpdate-datefrom"></tp-date>
      <tp-date id="dateto" name="dateto"><input type="hidden" class="tphidden" id="hdn" value="05/Nov/2026"><input type="text" class="tpdateinput tpdate-dateto" id="dto"></tp-date>
      <tp-button class="filter"><button id="filtrar">Filter</button></tp-button>
    </div>
    <div class="tpheader">
      <div class="tpheaderrow top"><span class="datecol action freeze">&nbsp;</span><span class="datecol date freeze">&nbsp;</span>
        <span class="splitcol"><label>GENERAL</label></span></div>
      <div class="tpheaderrow"><span class="datecol date freeze"><label>Date</label></span>
        <span class="max splitcol"><label>Max</label></span><span class="used splitcol"><label>Used</label></span>
        <span class="avail splitcol"><label>Avail</label></span><span class="release splitcol"><label>Release</label></span>
        <span class="request splitcol"><label>RQ</label></span></div>
    </div>
    <cdk-virtual-scroll-viewport id="vp" style="display:block;height:400px;overflow:auto;position:relative"></cdk-virtual-scroll-viewport>
  </div>
  <div id="setup-tab"><label for="showReleaseAsDate" class="showreleaseasdate">Show Release As Date</label>
    <tp-checkbox id="showReleaseAsDate"><label class="tpcheckbox"><input type="checkbox" class="tpcheckbox" id="chkrel"></label></tp-checkbox>
    <div class="tpselectiongrid"><div class="tpdestination"><label>Services Included</label><div class="tpselectiongrid-container">
      <table class="tpgrid"><thead><tr><th>Location</th><th>Service</th><th>Option</th><th>Description</th></tr></thead>
      <tbody><tr><td>BUE</td><td>HT</td><td>ST</td><td>Standard</td></tr></tbody></table></div></div></div></div>
</div></tp-dialog>
<script>
  const BASE = new Date(2026, 9, 5), MES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const MAXN = %(n)d; let N = 32;                       // el diálogo muestra ~1 mes hasta que se amplía Date To
  const STORE = {};                                      // data-index -> [used, max, rel] (modelo "guardado" + editado)
  function base(i){ return [i %% 4 === 0 ? 0 : 2, i %% 3 === 0 ? 5 : 1, i %% 5 === 0 ? 9999 : 3]; }
  function dato(i){ return STORE[i] || base(i); }
  const vp = document.getElementById("vp");
  vp.innerHTML = '<div id="sp"></div>';
  function fmt(d){ return String(d.getDate()).padStart(2,'0') + '/' + MES[d.getMonth()] + '/' + d.getFullYear(); }
  function render(){
    document.getElementById('sp').style.height = (N*35) + 'px';
    vp.querySelectorAll('.tpbodyrow').forEach(e => e.remove());
    const ini = Math.max(0, Math.floor(vp.scrollTop/35) - 2), fin = Math.min(N, ini + 16);
    for (let i = ini; i < fin; i++){
      const d = new Date(BASE.getTime()); d.setDate(d.getDate() + i);
      const [u,m,r] = dato(i);
      const row = document.createElement('div'); row.className = 'tpbodyrow'; row.dataset.index = i;
      row.style.cssText = 'position:absolute;top:' + (i*35) + 'px;height:35px';
      row.innerHTML = '<span class="datecol date freeze"><label>\n   ' + fmt(d) + '\n  </label></span>'
        + '<span class="max splitcol"><input data-i="' + i + '" data-k="1" value="' + m + '"></span>'
        + '<span class="used splitcol"><input value="' + u + '" disabled></span>'
        + '<span class="release splitcol"><input data-i="' + i + '" data-k="2" value="' + r.toLocaleString('en-US') + '"></span>';
      vp.appendChild(row);
    }
  }
  vp.addEventListener('scroll', render);
  vp.addEventListener('change', e => {                 // como el modelo de Angular: cambia el dato y habilita Save
    const t = e.target; if (!t.dataset.i) return;
    const i = +t.dataset.i, cur = dato(i).slice(); cur[+t.dataset.k] = parseInt(t.value.replace(/[^0-9]/g,''), 10);
    STORE[i] = cur; document.getElementById('save').disabled = false; document.getElementById('discard').disabled = false;
  });
  document.getElementById('save').addEventListener('click', e => { e.target.disabled = true; document.getElementById('discard').disabled = true; });
  document.getElementById('dto').addEventListener('blur', e => {     // dd/mm/aa -> hidden dd/Mon/yyyy
    const m = e.target.value.match(/^(\d+)\/(\d+)\/(\d+)$/); if (!m) return;
    document.getElementById('hdn').value = fmt(new Date(2000 + +m[3], +m[2]-1, +m[1]));
  });
  document.getElementById('filtrar').addEventListener('click', () => {
    const m = document.getElementById('hdn').value.match(/^(\d+)\/(\w+)\/(\d+)$/);
    const hasta = new Date(+m[3], MES.indexOf(m[2]), +m[1]);
    N = Math.min(MAXN, Math.round((hasta - BASE)/86400000) + 1); render();
  });
  document.getElementById('exit').addEventListener('click', () => document.querySelector('tp-dialog').remove());
  render();
</script></body></html>
""" % {"n": N_DIAS}


class Driver:
    """Adaptador mínimo con la interfaz de Selenium que usa el módulo."""
    def __init__(self, page):
        self.page = page

    def execute_script(self, script, *args):
        """Como Selenium: devuelve valores JSON, y elementos DOM como handles (reutilizables como argumento)."""
        h = self.page.evaluate_handle("([src, args]) => new Function(src).apply(null, args)", [script, list(args)])
        return self._desempacar(h)

    def _desempacar(self, h):
        tipo = h.evaluate("""x => x === null || x === undefined ? 'null' : (x instanceof Node ? 'node'
            : (Array.isArray(x) && x.some(e => e instanceof Node) ? 'nodes' : 'json'))""")
        if tipo == "null":
            return None
        if tipo == "node":
            return h
        if tipo == "nodes":
            n = h.evaluate("x => x.length")
            return [self._desempacar(h.evaluate_handle(f"x => x[{i}]")) for i in range(n)]
        return h.json_value()

    def find_elements(self, by, css):
        return self.page.query_selector_all(css)


@pytest.fixture(scope="module")
def drv():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(HTML)
        yield Driver(pg)
        b.close()


def esperado(i):
    return (0 if i % 4 == 0 else 2, 5 if i % 3 == 0 else 1, 9999 if i % 5 == 0 else 3)


def test_sin_ampliar_date_to_las_fechas_lejanas_no_tienen_fila(drv):
    assert fl.leer_dias(drv, [BASE + timedelta(days=300)]) == {}     # el diálogo solo muestra ~1 mes


def test_leer_dias_cerca_lejos_y_sin_fila(drv):
    fechas = [BASE + timedelta(days=d) for d in (0, 1, 37, 300, 700, 801)]
    fl.filtrar_dias_hasta(drv, max(fechas), hoy=BASE.date() if hasattr(BASE, "date") else BASE)
    dias = fl.leer_dias(drv, fechas)
    for d in (0, 1, 37, 300, 700):
        u, m, r = esperado(d)
        assert dias[BASE + timedelta(days=d)] == DiaAllocation(BASE + timedelta(days=d), u, m, r)
    assert BASE + timedelta(days=801) not in dias          # posterior a lo cargado
    acc = planear(dias, fechas)
    assert acc[-1].tipo == SIN_FILA and {a.tipo for a in acc[:-1]} <= {CERRAR, YA_CERRADA}


def test_fecha_anterior_a_la_primera_fila_no_rompe(drv):
    assert fl.leer_dias(drv, [BASE - timedelta(days=3)]) == {}


def test_abrir_allocation_exacta_ok_ambigua_y_ausente(drv):
    # coincidencia exacta (espacios y mayúsculas normalizados) -> hace clic y verifica título
    fl.abrir_allocation(drv, "ST", "standard cierra database")
    with pytest.raises(fl.FlujoError, match="2 coincidencias"):
        fl.abrir_allocation(drv, "DUP", "Igual")
    with pytest.raises(fl.FlujoError, match="0 coincidencias"):
        fl.abrir_allocation(drv, "ST", "no existe")


def test_habitaciones_y_verificacion(drv):
    assert fl.leer_habitaciones(drv, "6RABA1") == ["BUEHT6RABA1ST"]
    assert fl.verificar_habitacion("BUEHT6RABA1ST", ["BUEHT6RABA1ST"]) == (True, "")
    assert not fl.verificar_habitacion("BUEHT6RABA1XX", ["BUEHT6RABA1ST"])[0]
    assert fl.verificar_habitacion("Multiple Options", ["A", "B"])[0]
    assert not fl.verificar_habitacion("BUEHT6RABA1ST", ["BUEHT6RABA1ST", "OTRA"])[0]




def test_columnas_dias_con_estructura_real_no_confunde_encabezados_con_grupos(drv):
    # regresión: en Tourplan TODAS las columnas llevan la clase splitcol; el grupo (GENERAL)
    # está solo en la fila superior del encabezado
    fl.verificar_columnas_dias(drv)


def test_columnas_dias_frena_si_hay_otro_grupo(drv):
    drv.page.evaluate("""() => { const f = document.querySelector('.tpheaderrow.top');
        const e = document.createElement('span'); e.className = 'splitcol'; e.innerHTML = '<label>TWIN</label>'; f.appendChild(e); }""")
    try:
        with pytest.raises(fl.FlujoError, match="TWIN"):
            fl.verificar_columnas_dias(drv)
    finally:
        drv.page.evaluate("() => { const f = document.querySelector('.tpheaderrow.top'); f.removeChild(f.lastElementChild); }")


def test_aplicar_dias_escribe_guarda_verifica_y_es_idempotente(drv):
    from allocation import plan as pl
    fechas = [BASE + timedelta(days=d) for d in (3, 4, 5, 6)]
    fl.filtrar_dias_hasta(drv, max(fechas), hoy=BASE)
    acciones = pl.planear(fl.leer_dias(drv, fechas), fechas)
    assert any(a.tipo == pl.CERRAR for a in acciones)
    fl.aplicar_dias(drv, acciones)
    # releído: todas cerradas, y volver a planear no encuentra nada para cerrar
    despues = pl.planear(fl.leer_dias(drv, fechas), fechas)
    assert {a.tipo for a in despues} == {pl.YA_CERRADA}
    assert drv.page.evaluate("() => document.getElementById('save').disabled") is True
    # Max nunca subió por encima de lo que había salvo el caso Max < Used
    for a in acciones:
        antes = esperado((a.fecha - BASE).days)
        d = fl.leer_dias(drv, [a.fecha])[a.fecha]
        assert d.max <= max(antes[1], antes[0]) and (d.release == 9999 or antes[0] == 0)


def test_aplicar_frena_si_la_fila_cambio_desde_la_lectura(drv):
    from allocation import plan as pl
    f = BASE + timedelta(days=9)            # día con Used > 0 (9 %% 4 != 0), todavía sin cerrar
    fl.filtrar_dias_hasta(drv, f, hoy=BASE)
    acc = pl.planear(fl.leer_dias(drv, [f]), [f])[0]
    assert acc.tipo == pl.CERRAR
    drv.page.evaluate("() => { document.querySelector('#vp').scrollTop = 0; }")
    falsa = pl.Accion(f, pl.CERRAR, nuevo_max=0, nuevo_release=None)      # plan viejo que ya no corresponde
    with pytest.raises(fl.FlujoError, match="cambió desde la lectura"):
        fl.aplicar_dias(drv, [falsa])


def test_show_release_as_date_tildado_frena(drv):
    drv.page.evaluate("() => { document.getElementById('chkrel').checked = true; }")
    try:
        with pytest.raises(fl.FlujoError, match="Show Release As Date"):
            fl.verificar_columnas_dias(drv)
    finally:
        drv.page.evaluate("() => { document.getElementById('chkrel').checked = false; }")


def test_exit_cierra_dialogo(drv):  # va al final: borra el diálogo simulado
    fl.cerrar_dialogo(drv)
    assert drv.find_elements(None, "body > tp-dialog") == []


def test_esperar_fin_carga_ignora_el_modal_y_espera_un_please_wait_real(drv, capsys):
    """Regresión: el diálogo de una allocation puede ser un <dialog open> dentro de <tp-dialog>
    y no debe contarse como 'cargando' (hacía esperar 15 s en cada paso). Va al final: reemplaza la página."""
    import time
    from common import tourplan as tp
    pg = drv.page
    pg.set_content("<tp-dialog><dialog open>Allocation Detail</dialog></tp-dialog>")
    t = time.time()
    tp.esperar_fin_carga(drv, timeout=15, velocidad=0.2)
    assert time.time() - t < 1 and "seguía abierto" not in capsys.readouterr().out
    # un PLEASE WAIT real (fuera de tp-dialog) sí se espera, y se informa si no cierra
    pg.evaluate("() => { const x = document.createElement('dialog'); x.setAttribute('open',''); x.textContent = 'PLEASE WAIT...'; document.body.appendChild(x); }")
    tp.esperar_fin_carga(drv, timeout=3, velocidad=0.2)
    assert "PLEASE WAIT" in capsys.readouterr().out
    pg.evaluate("() => document.querySelector('body > dialog').remove()")
    t = time.time()
    tp.esperar_fin_carga(drv, timeout=3, velocidad=0.2)
    assert time.time() - t < 1


def test_abrir_supplier_reintenta_si_un_dialog_tapa_el_campo(monkeypatch):
    from selenium.common.exceptions import ElementClickInterceptedException

    class Campo:
        clics = 0

        def click(self):
            Campo.clics += 1
            if Campo.clics < 3:
                raise ElementClickInterceptedException("tapado por <dialog open>")

    class Parado(Exception):
        pass

    class Drv:
        def get(self, url):
            pass

    def parar(*a, **k):
        raise Parado()
    monkeypatch.setattr(fl.time, "sleep", lambda s: None)
    monkeypatch.setattr(fl.tp, "esperar_fin_carga", lambda *a, **k: None)
    monkeypatch.setattr(fl.tp, "wait", lambda d, sel: Campo())
    monkeypatch.setattr(fl.tp, "set_val", parar)           # llegó hasta escribir: el clic se resolvió
    with pytest.raises(Parado):
        fl.abrir_supplier(Drv(), "1INT01")
    assert Campo.clics == 3
