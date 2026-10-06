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

HTML = """
<html><body>
<tp-grid tpid="allocations-grid"><table><tbody>
  <tr><td class="tpcol-name"> ST </td><td class="tpcol-description">Standard  CIERRA DATABASE</td></tr>
  <tr><td class="tpcol-name">ST</td><td class="tpcol-description">Otra</td></tr>
  <tr><td class="tpcol-name">DUP</td><td class="tpcol-description">Igual</td></tr>
  <tr><td class="tpcol-name">DUP</td><td class="tpcol-description">igual</td></tr>
</tbody></table></tp-grid>
<tp-dialog><div class="tpmodal-allocation"><h3>Allocation Detail - ST</h3>
  <div id="setup-tab"><table class="tpdestination"><thead><tr><th>Location</th><th>Service</th><th>Option</th></tr></thead>
    <tbody><tr><td>BUE</td><td>HT</td><td>ST</td></tr></tbody></table></div>
  <div id="days-tab">
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
  <tp-button class="cancel"><button id="exit">Exit</button></tp-button>
</div></tp-dialog>
<script>
  const N = %(n)d, BASE = new Date(2026, 9, 5);
  const MES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const vp = document.getElementById("vp");
  vp.innerHTML = '<div id="sp" style="height:' + (N*35) + 'px"></div>';
  window.DATOS = {};   // data-index -> [used, max, rel]
  function datos(i){ return [i %% 4 === 0 ? 0 : 2, i %% 3 === 0 ? 5 : 1, i %% 5 === 0 ? 9999 : 3]; }
  function render(){
    vp.querySelectorAll('.tpbodyrow').forEach(e => e.remove());
    const ini = Math.max(0, Math.floor(vp.scrollTop/35) - 2), fin = Math.min(N, ini + 16);
    for (let i = ini; i < fin; i++){
      const d = new Date(BASE.getTime()); d.setDate(d.getDate() + i);
      const [u,m,r] = datos(i);
      const row = document.createElement('div'); row.className = 'tpbodyrow'; row.dataset.index = i;
      row.style.cssText = 'position:absolute;top:' + (i*35) + 'px;height:35px';
      row.innerHTML = '<span class="datecol date"><label>' + String(d.getDate()).padStart(2,'0') + '/' + MES[d.getMonth()] + '/' + d.getFullYear() + '</label></span>'
        + '<span class="used splitcol"><input value="' + u + '"></span><span class="max splitcol"><input value="' + m + '"></span>'
        + '<span class="release splitcol"><input value="' + r.toLocaleString('en-US') + '"></span>';
      vp.appendChild(row);
    }
  }
  vp.addEventListener('scroll', render); render();
  document.getElementById('exit').addEventListener('click', () => document.querySelector('tp-dialog').remove());
</script></body></html>
""" % {"n": N_DIAS}


class Driver:
    """Adaptador mínimo con la interfaz de Selenium que usa el módulo."""
    def __init__(self, page):
        self.page = page

    def execute_script(self, script, *args):
        return self.page.evaluate("([src, args]) => new Function(src).apply(null, args)", [script, list(args)])

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


def test_leer_dias_cerca_lejos_y_sin_fila(drv):
    fechas = [BASE + timedelta(days=d) for d in (0, 1, 37, 300, 799, 801)]
    dias = fl.leer_dias(drv, fechas)
    for d in (0, 1, 37, 300, 799):
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


def test_exit_cierra_dialogo(drv):  # va al final: borra el diálogo simulado
    fl.cerrar_dialogo(drv)
    assert drv.find_elements(None, "body > tp-dialog") == []
