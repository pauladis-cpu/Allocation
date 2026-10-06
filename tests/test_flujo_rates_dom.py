"""Prueba del JS de tourplan_flujos/rates.py contra un DOM SIMULADO (no es Tourplan): grilla de
períodos, diálogo del período (tarifas + Rate Set + Save) y Product Find paginado.
Requiere playwright y CHROME_BIN; si no, se saltea."""
import os
from datetime import date

import pytest

pytest.importorskip("playwright.sync_api")
CHROME = os.environ.get("CHROME_BIN")
if not CHROME:
    pytest.skip("CHROME_BIN no definido", allow_module_level=True)
os.environ.setdefault("TOURPLAN_VELOCIDAD", "0.05")

from playwright.sync_api import sync_playwright  # noqa: E402

from allocation import rates_plan as rp  # noqa: E402
from tests.test_flujo_allocations_dom import Driver  # noqa: E402
from tourplan_flujos import rates as rt  # noqa: E402
from tourplan_flujos.allocations import FlujoError  # noqa: E402

HAB = "BUEHT1ESP06CPNV"

HTML = r"""
<html><body>
<div id="grid"><table><thead><tr><th class="tpcol-RatePeriod">Rate Period</th><th>PC</th></tr></thead><tbody id="tb">
 <tr><td class="tpcol-rateperiod">01/Dec/2026 - 25/Dec/2026</td><td class="tpcol-pricecodecode">TR</td><td class="tpcol-ratestatuses">Confirmed</td><td class="tpcol-ratenames">Standard</td></tr>
 <tr><td class="tpcol-rateperiod">01/Dec/2026 - 25/Dec/2026</td><td class="tpcol-pricecodecode">RACK</td><td class="tpcol-ratestatuses">Confirmed</td><td class="tpcol-ratenames">Standard</td></tr>
 <tr><td class="tpcol-rateperiod">26/Dec/2026 - 31/Dec/2026</td><td class="tpcol-pricecodecode">TR</td><td class="tpcol-ratestatuses">Closed</td><td class="tpcol-ratenames">Standard</td></tr>
</tbody></table></div>
<div class="tpmodal-productlistnext"><tp-grid tpid="modalsNextprevproductMaingrid"><table><tbody id="mb"></tbody></table></tp-grid>
  <tp-button class="next"><button id="next">Next</button></tp-button></div>
<script>
  const PAG = [[["BUE","HT","1ESP06","600HTL"],["BUE","HT","1ESP06","CPNV"]],
               [["BUE","HT","1ESP06","CPNV"],["BUE","HT","1ESP06","ROOMS"],["BUE","HX","1ESP06","600HTX"]],
               [["BUE","HT","1ESP06","ROOMS"],["BUE","HT","1ESP06","SU"]]];
  let pag = 0, elegida = null;
  function pintar(){ document.getElementById('mb').innerHTML = PAG[pag].map(r =>
    '<tr>' + ['locationcode','servicecode','suppliercode','optioncode'].map((c,i) => '<td class="tpcol-' + c + '"> ' + r[i] + ' </td>').join('')
    + '<td class="tpcol-optiondescription">desc</td></tr>').join(''); }
  document.getElementById('mb').addEventListener('click', e => { const tr = e.target.closest('tr'); if (tr) elegida = tr.textContent.replace(/\s+/g,''); });
  document.getElementById('next').addEventListener('click', () => { if (pag < PAG.length - 1) { pag++; pintar(); } else { document.getElementById('next').disabled = true; } });
  window.elegida = () => elegida; pintar();

  document.getElementById('tb').addEventListener('click', e => {
    const td = e.target.closest('td.tpcol-rateperiod'); if (!td) return;
    const tr = td.parentElement, rango = td.textContent.trim().split(' - '), pc = tr.querySelector('.tpcol-pricecodecode').textContent.trim();
    const d = document.createElement('tp-dialog');
    d.innerHTML = '<div class="tpmodal-productcosts"><h3>%(hab)s   ' + rango[0] + '/' + rango[1] + ' "' + pc + '"</h3>'
      + '<ul><li id="tptablabel-tabs-rateset">Rate Set</li></ul>'
      + '<div id="tabs-rates"><div id="costs-panel"><table><tbody>'
      + '<tr><td class="tpcol-cost"><input class="tpnumber-ratecostamount" value="100"></td><td class="tpcol-cost"><input value="100"></td></tr>'
      + '<tr><td class="tpcol-cost"><input class="tpnumber-ratecostamount" value=""></td><td class="tpcol-cost"><input value=""></td></tr>'
      + '</tbody></table></div></div><div id="rs"></div>'
      + '<tp-button class="save"><button disabled>Save</button></tp-button><tp-button class="cancel"><button>Exit</button></tp-button></div>';
    document.body.appendChild(d); d.dataset.tr = Array.from(tr.parentElement.children).indexOf(tr);
    const save = d.querySelector('tp-button.save button');
    d.querySelectorAll('.tpnumber-ratecostamount').forEach(inp => inp.addEventListener('change', () => {   // Tourplan replica Group Cost
      inp.closest('tr').querySelectorAll('td.tpcol-cost input').forEach(o => { o.value = inp.value; }); save.disabled = false; }));
    d.querySelector('#tptablabel-tabs-rateset').addEventListener('click', () => {
      const actual = tr.querySelector('.tpcol-ratestatuses').textContent.trim();
      d.querySelector('#rs').innerHTML = '<tp-group class="tpgroup-ratestatus">' + ['Confirmed','Provisional','Terminal','Closed','Manual'].map((s,i) =>
        '<tp-radio><label class="tpradio"><input type="button" id="st' + i + '" class="' + (s === actual ? 'checked' : '') + '"></label></tp-radio><label for="st' + i + '">' + s + '</label>').join('') + '</tp-group>';
      d.querySelectorAll('#rs input').forEach(r => r.addEventListener('click', () => {
        d.querySelectorAll('#rs input').forEach(o => o.classList.remove('checked')); r.classList.add('checked'); save.disabled = false; })); });
    save.addEventListener('click', () => { const sel = d.querySelector('#rs input.checked');
      if (sel) tr.querySelector('.tpcol-ratestatuses').textContent = d.querySelector('label[for="' + sel.id + '"]').textContent;
      d.remove(); });
    d.querySelector('tp-button.cancel button').addEventListener('click', () => d.remove());
  });
</script></body></html>
""" % {"hab": HAB}


@pytest.fixture()
def drv():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(HTML)
        yield Driver(pg)
        b.close()


def test_leer_periodos_y_clic_exacto(drv):
    ps = rt.leer_periodos(drv)
    assert [(p.ini, p.fin, p.pc, p.status) for p in ps][0] == (date(2026, 12, 1), date(2026, 12, 25), "TR", "Confirmed")
    assert len(ps) == 3
    rt._clic_fila(drv, ps[1])                      # RACK: la fila exacta (rango + price code), no la de TR
    rt.verificar_titulo_periodo(drv, HAB, ps[1])
    with pytest.raises(FlujoError, match="Título"):
        rt.verificar_titulo_periodo(drv, HAB, ps[0])
    with pytest.raises(FlujoError, match="0 filas"):
        rt._clic_fila(drv, rp.Periodo(date(2026, 1, 1), date(2026, 1, 2), "TR", "Confirmed"))


def test_editar_periodo_pone_cero_cambia_status_y_guarda(drv):
    ps = rt.leer_periodos(drv)
    rt.editar_periodo(drv, HAB, rp.Edicion(ps[0], "Manual"))                 # TR Confirmed -> Manual
    rt.editar_periodo(drv, HAB, rp.Edicion(ps[1], "Closed"))                 # RACK Confirmed -> Closed
    despues = rt.leer_periodos(drv)
    assert [p.status for p in despues] == ["Manual", "Closed", "Closed"]
    assert drv.find_elements(None, "body > tp-dialog") == []
    plan = rp.planear(despues, [(date(2026, 12, 1), date(2026, 12, 25))])
    assert plan.ediciones == [] and plan.cortes == []                          # idempotente


def test_closed_nunca_pasa_a_manual_ni_se_abre_el_dialogo(drv):
    cerrado = rt.leer_periodos(drv)[2]
    with pytest.raises(rp.PlanRatesError):
        rt.editar_periodo(drv, HAB, rp.Edicion(cerrado, "Manual"))
    assert drv.find_elements(None, "body > tp-dialog") == []


def test_poner_en_cero_solo_toca_group_cost_con_valor(drv):
    rt._clic_fila(drv, rt.leer_periodos(drv)[0])
    assert rt.poner_tarifas_en_cero(drv) == 1                                  # la fila vacía no se toca
    vals = drv.execute_script("return Array.from(document.querySelectorAll('tp-dialog td.tpcol-cost input')).map(i => i.value);")
    assert vals == ["0", "0", "", ""]


def test_product_find_pagina_deduplica_y_filtra_ht(drv):
    todas = rt.recorrer_product_find(drv)
    assert sorted(todas) == ["BUEHT1ESP06600HTL", "BUEHT1ESP06CPNV", "BUEHT1ESP06ROOMS", "BUEHT1ESP06SU", "BUEHX1ESP06600HTX"]
    elegibles = sorted(c for c, f in todas.items() if f["srv"] == "HT" and f["opt"] not in ("600HTL", "ROOMS"))
    assert elegibles == ["BUEHT1ESP06CPNV", "BUEHT1ESP06SU"]


def test_product_find_elige_la_exacta_y_falla_si_no_esta(drv):
    assert rt.recorrer_product_find(drv, objetivo="BUEHT1ESP06SU") is True
    assert drv.page.evaluate("window.elegida()").startswith("BUEHT1ESP06SU")
    with pytest.raises(FlujoError, match="No encontré la habitación"):
        rt.recorrer_product_find(drv, objetivo="BUEHT1ESP06XX")


HTML_VIRTUAL = r"""
<html><body>
<div id="vp" style="height:150px;overflow:auto">
<table><thead><tr><th class="tpcol-RatePeriod">Rate Period</th><th>PC</th></tr></thead><tbody id="tb"></tbody></table></div>
<script>
  // 60 períodos de un día (uno por price code TR) y solo ~6 filas renderizadas cerca del scroll (CDK virtual)
  const N = 60, H = 30, MES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const f = i => { const d = new Date(2026, 9, 1 + i); return String(d.getDate()).padStart(2,'0') + '/' + MES[d.getMonth()] + '/' + d.getFullYear(); };
  const vp = document.getElementById('vp'), tb = document.getElementById('tb');
  function render(){
    const ini = Math.max(0, Math.floor(vp.scrollTop / H) - 1), fin = Math.min(N, ini + 8);
    let h = '<tr style="height:' + (ini*H) + 'px"><td colspan="4"></td></tr>';
    for (let i = ini; i < fin; i++)
      h += '<tr style="height:' + H + 'px"><td class="tpcol-rateperiod">' + f(i) + ' - ' + f(i) + '</td><td class="tpcol-pricecodecode">TR</td>'
         + '<td class="tpcol-ratestatuses">Confirmed</td><td class="tpcol-ratenames">Standard</td></tr>';
    h += '<tr style="height:' + ((N-fin)*H) + 'px"><td colspan="4"></td></tr>';
    tb.innerHTML = h;
  }
  vp.addEventListener('scroll', render); render();
  tb.addEventListener('click', e => { const td = e.target.closest('td.tpcol-rateperiod'); if (td) window.abierto = td.textContent; });
</script></body></html>
"""


@pytest.fixture()
def drv_virtual():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(HTML_VIRTUAL)
        yield Driver(pg)
        b.close()


def test_grilla_de_periodos_con_scroll_virtual_se_lee_completa(drv_virtual):
    """Regresión: solo las filas cercanas a la pantalla existen en el DOM; leer sin scroll perdía períodos."""
    renderizadas = drv_virtual.execute_script("return document.querySelectorAll('td.tpcol-rateperiod').length;")
    assert renderizadas < 12                                    # sin scroll solo hay unas pocas filas
    ps = rt.leer_periodos(drv_virtual)
    assert len(ps) == 60
    assert ps[0].ini == date(2026, 10, 1) and max(p.ini for p in ps) == date(2026, 11, 29)


def test_clic_en_una_fila_fuera_de_pantalla_hace_scroll_y_la_encuentra(drv_virtual):
    lejana = rp.Periodo(date(2026, 11, 25), date(2026, 11, 25), "TR", "Confirmed")
    # el diálogo no existe en este mock: solo comprobamos que localizó y clickeó la fila exacta
    with pytest.raises(FlujoError, match="No se abrió el diálogo"):
        rt._clic_fila(drv_virtual, lejana)
    assert drv_virtual.execute_script("return window.abierto;").startswith("25/Nov/2026")
    inexistente = rp.Periodo(date(2027, 1, 1), date(2027, 1, 1), "TR", "Confirmed")
    with pytest.raises(FlujoError, match="0 filas"):
        rt._clic_fila(drv_virtual, inexistente)


def _grilla_virtual(drv_pg, descendente):
    html = HTML_VIRTUAL.replace("f(i) + ' - ' + f(i)", "f(%s) + ' - ' + f(%s)" % (("N-1-i",) * 2 if descendente else ("i",) * 2))
    drv_pg.goto("about:blank")
    drv_pg.set_content(html)


@pytest.mark.parametrize("descendente", [False, True])
def test_el_scroll_se_corta_al_pasar_el_rango_pedido(drv_virtual, descendente, capsys):
    """Solo se scrollea hasta cubrir las fechas pedidas, no toda la grilla (ascendente o descendente)."""
    _grilla_virtual(drv_virtual.page, descendente)
    # las fechas pedidas están al principio de la grilla (más antiguas si es ascendente, más recientes si es descendente)
    rangos = [(date(2026, 11, 25), date(2026, 11, 27))] if descendente else [(date(2026, 10, 5), date(2026, 10, 7))]
    ps = rt.leer_periodos(drv_virtual, rangos)
    assert len(ps) < 40                                              # no leyó las 60 filas
    assert {r0 + __import__("datetime").timedelta(days=i) for r0 in [rangos[0][0]] for i in range(3)} <= {p.ini for p in ps}
    assert "se dejó de leer" in capsys.readouterr().out
    plan = rp.planear(ps, rangos)                                    # el plan con lo leído es completo
    assert len(plan.ediciones) == 3 and plan.cortes == []


def test_grilla_descendente_con_fechas_antiguas_lee_hasta_encontrarlas(drv_virtual):
    """Si las fechas pedidas están al final del orden, hay que scrollear hasta ahí (no hay atajo): igual se lee bien."""
    _grilla_virtual(drv_virtual.page, True)
    rangos = [(date(2026, 10, 5), date(2026, 10, 7))]
    ps = rt.leer_periodos(drv_virtual, rangos)
    assert {date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)} <= {p.ini for p in ps}


@pytest.mark.parametrize("descendente", [False, True])
def test_rango_que_llega_al_final_de_la_grilla_lee_hasta_el_final(drv_virtual, descendente):
    _grilla_virtual(drv_virtual.page, descendente)
    rangos = [(date(2026, 11, 28), date(2026, 11, 29))]
    ps = rt.leer_periodos(drv_virtual, rangos)
    assert {date(2026, 11, 28), date(2026, 11, 29)} <= {p.ini for p in ps}


def test_sin_rangos_o_con_escaneo_completo_lee_todo(drv_virtual, monkeypatch):
    assert len(rt.leer_periodos(drv_virtual)) == 60
    monkeypatch.setenv("TOURPLAN_RATES_ESCANEO_COMPLETO", "1")
    assert len(rt.leer_periodos(drv_virtual, [(date(2026, 10, 5), date(2026, 10, 6))])) == 60
