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
    lejana = rp.Periodo(date(2026, 11, 25), date(2026, 11, 25), "TR", "Confirmed", "Standard")
    # el diálogo no existe en este mock: solo comprobamos que localizó y clickeó la fila exacta
    with pytest.raises(FlujoError, match="No se abrió el diálogo"):
        rt._clic_fila(drv_virtual, lejana)
    assert drv_virtual.execute_script("return window.abierto;").startswith("25/Nov/2026")
    inexistente = rp.Periodo(date(2027, 1, 1), date(2027, 1, 1), "TR", "Confirmed", "Standard")
    with pytest.raises(rt.FilaNoEncontrada, match="0 filas"):
        rt._clic_fila(drv_virtual, inexistente)


def _grilla_virtual(drv_pg, descendente):
    html = HTML_VIRTUAL.replace("f(i) + ' - ' + f(i)", "f(%s) + ' - ' + f(%s)" % (("N-1-i",) * 2 if descendente else ("i",) * 2))
    drv_pg.goto("about:blank")
    drv_pg.set_content(html)


def test_el_scroll_se_corta_con_el_margen_de_meses(drv_virtual, capsys, monkeypatch):
    """Grilla de la fecha más lejana a la más reciente: se scrollea hasta un período MESES_MARGEN antes de lo pedido."""
    _grilla_virtual(drv_virtual.page, True)                          # 29/Nov ... 01/Oct
    monkeypatch.setattr(rp, "MESES_MARGEN", 1)
    rangos = [(date(2026, 11, 25), date(2026, 11, 27))]              # límite: 27/Oct (1 mes antes)
    ps = rt.leer_periodos(drv_virtual, rangos)
    assert len(ps) < 45                                              # no leyó las 60 filas
    assert min(p.ini for p in ps) <= date(2026, 10, 27)              # llegó hasta el margen
    assert {date(2026, 11, 25), date(2026, 11, 26), date(2026, 11, 27)} <= {p.ini for p in ps}
    assert "se dejó de leer" in capsys.readouterr().out
    plan = rp.planear(ps, rangos)
    assert len(plan.ediciones) == 3 and plan.cortes == []


def test_con_el_margen_por_defecto_de_5_meses_una_grilla_corta_se_lee_entera(drv_virtual):
    _grilla_virtual(drv_virtual.page, True)
    assert len(rt.leer_periodos(drv_virtual, [(date(2026, 11, 25), date(2026, 11, 27))])) == 60


def test_grilla_ascendente_no_se_corta(drv_virtual):
    _grilla_virtual(drv_virtual.page, False)
    assert len(rt.leer_periodos(drv_virtual, [(date(2026, 10, 5), date(2026, 10, 7))])) == 60


def test_fechas_antiguas_en_grilla_descendente_se_leen_hasta_el_final(drv_virtual, monkeypatch):
    _grilla_virtual(drv_virtual.page, True)
    monkeypatch.setattr(rp, "MESES_MARGEN", 1)
    ps = rt.leer_periodos(drv_virtual, [(date(2026, 10, 5), date(2026, 10, 7))])
    assert {date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)} <= {p.ini for p in ps}


def test_sin_rangos_o_con_escaneo_completo_lee_todo(drv_virtual, monkeypatch):
    assert len(rt.leer_periodos(drv_virtual)) == 60
    _grilla_virtual(drv_virtual.page, True)
    monkeypatch.setattr(rp, "MESES_MARGEN", 1)
    monkeypatch.setenv("TOURPLAN_RATES_ESCANEO_COMPLETO", "1")
    assert len(rt.leer_periodos(drv_virtual, [(date(2026, 11, 25), date(2026, 11, 27))])) == 60


def test_terminal_y_provisional_se_editan_segun_las_reglas(drv):
    drv.page.evaluate("""() => { const s = document.querySelectorAll('#tb .tpcol-ratestatuses');
        s[0].textContent = 'Terminal'; s[1].textContent = 'Provisional'; }""")   # TR Terminal, RACK Provisional
    rangos = [(date(2026, 12, 1), date(2026, 12, 25))]
    plan = rp.planear(rt.leer_periodos(drv, rangos), rangos)
    assert {(e.periodo.pc, e.nuevo_status) for e in plan.ediciones} == {("TR", "Manual"), ("RACK", "Closed")}   # Terminal -> objetivo (TR Manual)
    for e in plan.ediciones:
        rt.editar_periodo(drv, HAB, e)
    assert [p.status for p in rt.leer_periodos(drv, rangos)] == ["Manual", "Closed", "Closed"]


def test_provisional_de_price_code_manual_pasa_a_manual(drv):
    drv.page.evaluate("() => { document.querySelectorAll('#tb .tpcol-ratestatuses')[0].textContent = 'Provisional'; }")
    rangos = [(date(2026, 12, 1), date(2026, 12, 25))]
    e = next(e for e in rp.planear(rt.leer_periodos(drv, rangos), rangos).ediciones if e.periodo.pc == "TR")
    assert e.nuevo_status == "Manual"
    rt.editar_periodo(drv, HAB, e)
    assert rt.leer_periodos(drv, rangos)[0].status == "Manual"


def test_editar_periodo_de_fx_se_niega_sin_abrir_el_dialogo(drv):
    drv.page.evaluate("() => { document.querySelectorAll('#tb .tpcol-pricecodecode')[1].textContent = 'FX'; }")
    fx = next(p for p in rt.leer_periodos(drv) if p.pc == "FX")
    with pytest.raises(rp.PlanRatesError, match="FX"):
        rt.editar_periodo(drv, HAB, rp.Edicion(fx, "Closed"))
    assert drv.find_elements(None, "body > tp-dialog") == []                 # ni siquiera se abrió


def test_filas_con_el_mismo_periodo_y_price_code_pero_distinto_rate_name_se_distinguen(drv):
    drv.page.evaluate("""() => { const tb = document.getElementById('tb'), c = tb.rows[0].cloneNode(true);
        c.querySelector('.tpcol-ratenames').textContent = 'Promo'; tb.appendChild(c); }""")     # TR Standard + TR Promo
    ps = [p for p in rt.leer_periodos(drv) if p.pc == "TR" and p.ini == date(2026, 12, 1)]
    assert sorted(p.rate_name for p in ps) == ["Promo", "Standard"]
    promo = next(p for p in ps if p.rate_name == "Promo")
    rt.editar_periodo(drv, HAB, rp.Edicion(promo, "Manual"))
    estados = {p.rate_name: p.status for p in rt.leer_periodos(drv) if p.pc == "TR" and p.ini == date(2026, 12, 1)}
    assert estados == {"Standard": "Confirmed", "Promo": "Manual"}          # se abrió y editó solo la fila Promo


HTML_SPLIT = r"""
<html><body>
<table><thead><tr><th class="tpcol-RatePeriod">Rate Period</th></tr></thead><tbody id="tb">
 <tr><td class="tpcol-rateperiod">01/Dec/2026 - 25/Dec/2026</td><td class="tpcol-pricecodecode">TR</td>
     <td class="tpcol-ratestatuses">Confirmed</td><td class="tpcol-ratenames">Standard</td></tr></tbody></table>
<script>
  window.log = []; const MES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const fmt = d => String(d.getDate()).padStart(2,'0') + '/' + MES[d.getMonth()] + '/' + d.getFullYear();
  document.getElementById('tb').addEventListener('click', e => {
    if (!e.target.closest('td.tpcol-rateperiod')) return;
    const d = document.createElement('tp-dialog');
    d.innerHTML = '<div class="tpmodal-productcosts"><h3>%(hab)s   01/Dec/2026/25/Dec/2026 "TR"</h3>'
      + '<tp-button class="splitdaterange"><button>Split Date Range</button></tp-button>'
      + '<tp-button class="save"><button disabled>Save</button></tp-button><tp-button class="cancel"><button>Exit</button></tp-button></div>';
    document.body.appendChild(d);
    d.querySelector('tp-button.cancel button').addEventListener('click', () => d.remove());
    d.querySelector('tp-button.splitdaterange button').addEventListener('click', () => {
      const s = document.createElement('tp-dialog');
      s.innerHTML = '<div class="split-content-panel"><h3>Split Date - 01/Dec/2026 - 25/Dec/2026</h3>'
        + (window.CASILLA ? '<input type="checkbox" id="split-applicable" style="display:none">'   // input invisible, como en Tourplan
                            + '<label for="split-applicable">Split All Applicable Price Codes</label>' : '')
        + '<div><input type="text" class="tpdate-productdatesplitpoint"><input type="hidden" class="tphidden"></div>'
        + '<button class="tpbutton-addsplit" disabled>Add Split</button><ul class="dateranges"></ul>'
        + '<tp-button class="ok"><button>OK</button></tp-button></div>';
      document.body.appendChild(s);
      const inp = s.querySelector('.tpdate-productdatesplitpoint'), hid = s.querySelector('.tphidden'), add = s.querySelector('.tpbutton-addsplit');
      inp.addEventListener('blur', () => { const m = inp.value.match(/^(\d+)\/(\d+)\/(\d+)$/); if (!m) return;
        const f = new Date(2000 + +m[3], +m[2]-1, +m[1]); hid.value = fmt(f); add.disabled = !(f > new Date(2026,11,1) && f <= new Date(2026,11,25)); });
      const chk = s.querySelector('#split-applicable');
      if (chk) chk.addEventListener('change', () => window.log.push('casilla:' + chk.checked));
      const cuts = [], txt = [];
      add.addEventListener('click', () => { const m = inp.value.match(/^(\d+)\/(\d+)\/(\d+)$/), f = new Date(2000 + +m[3], +m[2]-1, +m[1]);
        cuts.push(f); txt.push(inp.value); cuts.sort((a, b) => a - b);
        const ini = [new Date(2026,11,1)].concat(cuts), fin = cuts.map(c => { const a = new Date(c); a.setDate(a.getDate() - 1); return a; }).concat([new Date(2026,11,25)]);
        s.querySelector('ul.dateranges').innerHTML = ini.map((a, i) => '<li><span class="date-range-display">Tue ' + fmt(a) + ' - Fri ' + fmt(fin[i]) + '</span></li>').join('');
        inp.value = ''; add.disabled = true; });
      s.querySelector('tp-button.ok button').addEventListener('click', () => { window.log.push('ok:' + txt.join('+') + ':todos=' + (chk ? chk.checked : 'sin-casilla')); s.remove();
        const sv = d.querySelector('tp-button.save button');
        setTimeout(() => { sv.disabled = false; }, 150);
        sv.addEventListener('click', () => { window.log.push('guardado'); d.remove(); }); });
    });
  });
</script></body></html>
""" % {"hab": HAB}


@pytest.mark.parametrize("con_casilla", [True, False])
def test_split_tilda_la_casilla_solo_si_aparece(con_casilla):
    """Tourplan solo muestra 'Split All Applicable Price Codes' si más de un price code comparte el período."""
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(HTML_SPLIT)
        pg.evaluate("window.CASILLA = %s" % ("true" if con_casilla else "false"))
        d = Driver(pg)
        per = rt.leer_periodos(d)[0]
        rt.hacer_corte(d, HAB, per, date(2026, 12, 10))
        log = pg.evaluate("window.log")
        assert log[-2:] == ["ok:10/12/26:todos=" + ("true" if con_casilla else "sin-casilla"), "guardado"]
        assert d.find_elements(None, "body > tp-dialog") == []          # se cerraron el split y el período
        b.close()


def test_terminal_em_pasa_a_manual(drv):
    drv.page.evaluate("""() => { const tr = document.querySelectorAll('#tb tr')[0];
        tr.querySelector('.tpcol-pricecodecode').textContent = 'EM'; tr.querySelector('.tpcol-ratestatuses').textContent = 'Terminal'; }""")
    rangos = [(date(2026, 12, 1), date(2026, 12, 25))]
    e = next(e for e in rp.planear(rt.leer_periodos(drv, rangos), rangos).ediciones if e.periodo.pc == "EM")
    assert e.nuevo_status == "Manual"
    rt.editar_periodo(drv, HAB, e)
    assert next(p for p in rt.leer_periodos(drv, rangos) if p.pc == "EM").status == "Manual"


def test_la_fila_se_encuentra_aunque_el_rate_name_leido_no_coincida(drv):
    """El Rate Name no decide si una fila existe: solo desempata. Una fila única (rango + price code) siempre se abre."""
    raro = rp.Periodo(date(2026, 12, 1), date(2026, 12, 25), "RACK", "Confirmed", "nombre que no coincide")
    rt.editar_periodo(drv, HAB, rp.Edicion(raro, "Closed"))
    assert next(p for p in rt.leer_periodos(drv) if p.pc == "RACK").status == "Closed"


def test_error_de_fila_no_encontrada_informa_las_filas_a_la_vista(drv):
    inexistente = rp.Periodo(date(2030, 1, 1), date(2030, 1, 2), "TR", "Confirmed", "Standard")
    with pytest.raises(FlujoError, match="Filas a la vista.*01/Dec/2026"):
        rt._clic_fila(drv, inexistente)


def test_lectura_completa_reintenta_si_la_grilla_trae_menos_filas(monkeypatch):
    lecturas = [[1], [1, 2], [1, 2, 3]]
    monkeypatch.setattr(rt, "leer_periodos", lambda d, r=None: lecturas.pop(0))
    monkeypatch.setattr(rt.tp, "esperar_fin_carga", lambda *a, **k: None)
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)
    assert rt.leer_periodos_completo(None, [], minimo=3) == [1, 2, 3]


def test_cortes_encadenados_en_una_sola_apertura():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(HTML_SPLIT)
        pg.evaluate("window.CASILLA = false")
        d = Driver(pg)
        per = rt.leer_periodos(d)[0]
        rt.hacer_corte(d, HAB, per, [date(2026, 12, 20), date(2026, 12, 10)])
        log = pg.evaluate("window.log")
        assert log == ["ok:10/12/26+20/12/26:todos=sin-casilla", "guardado"]
        with pytest.raises(rt.FlujoError, match="fuera del período"):
            rt.hacer_corte(d, HAB, per, [date(2026, 12, 10), date(2027, 1, 5)])
        b.close()


def test_grilla_sin_actualizar_no_repite_el_corte(monkeypatch):
    larga = rp.Periodo(date(2026, 4, 1), date(2028, 12, 31), "TR", "Confirmed", "Standard")
    monkeypatch.setattr(rt, "abrir_habitacion", lambda *a, **k: None)
    monkeypatch.setattr(rt, "leer_periodos_completo", lambda d, r, minimo=0: [larga])   # la grilla nunca cambia
    cortes = []
    monkeypatch.setattr(rt, "hacer_corte", lambda d, h, per, fechas: cortes.append(fechas))
    monkeypatch.setattr(rt.tp, "esperar_fin_carga", lambda *a, **k: None)
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)
    with pytest.raises(FlujoError, match="no lo refleja"):
        rt.procesar_habitacion(None, "H", "IGRHT1H", [(date(2026, 11, 10), date(2026, 11, 14))], aplicar=True)
    assert len(cortes) == 1                      # el corte se hizo una sola vez


def test_grilla_sin_actualizar_no_repite_la_edicion(monkeypatch):
    p = rp.Periodo(date(2026, 11, 10), date(2026, 11, 14), "TR", "Confirmed", "Standard")
    monkeypatch.setattr(rt, "abrir_habitacion", lambda *a, **k: None)
    monkeypatch.setattr(rt, "leer_periodos_completo", lambda d, r, minimo=0: [p])      # la grilla nunca cambia
    editadas = []
    monkeypatch.setattr(rt, "editar_periodo", lambda d, h, e: editadas.append(e))
    monkeypatch.setattr(rt.tp, "esperar_fin_carga", lambda *a, **k: None)
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)
    with pytest.raises(FlujoError, match="no la refleja"):
        rt.procesar_habitacion(None, "H", "IGRHT1H", [(date(2026, 11, 10), date(2026, 11, 14))], aplicar=True)
    assert len(editadas) == 1                    # la edición se hizo una sola vez


def test_product_find_espera_si_la_pagina_viene_vacia_al_principio(monkeypatch):
    fila = {"loc": "IGR", "srv": "HT", "sup": "1INT01", "opt": "MEFV", "desc": "x"}
    paginas = [[], [], [fila]]                                  # la grilla tarda en cargar
    monkeypatch.setattr(rt, "_leer_pagina_modal", lambda d: paginas.pop(0) if len(paginas) > 1 else paginas[0])
    monkeypatch.setattr(rt.tp, "esperar_fin_carga", lambda *a, **k: None)
    monkeypatch.setattr(rt.time, "sleep", lambda s: None)

    class Drv:
        def find_elements(self, *a):
            return []

        def execute_script(self, js, *a):
            return 1                                            # clic exacto resuelto
    assert rt.recorrer_product_find(Drv(), objetivo="IGRHT1INT01MEFV") is True


# ── Períodos con varios rate sets ───────────────────────────────────────────

HTML_RATESETS = r"""
<html><body>
<div id="grid"><table><thead><tr><th class="tpcol-RatePeriod">Rate Period</th></tr></thead><tbody id="tb">
 <tr><td class="tpcol-rateperiod">22/May/2026 - 24/May/2026</td><td class="tpcol-pricecodecode">TR</td><td class="tpcol-ratestatuses">Confirmed, Confirmed</td><td class="tpcol-ratenames">1-1, 2-999</td></tr>
 <tr><td class="tpcol-rateperiod">22/May/2026 - 24/May/2026</td><td class="tpcol-pricecodecode">RACK</td><td class="tpcol-ratestatuses">Confirmed, Manual</td><td class="tpcol-ratenames">1-1, 2-999</td></tr>
 <tr><td class="tpcol-rateperiod">22/May/2026 - 24/May/2026</td><td class="tpcol-pricecodecode">ND</td><td class="tpcol-ratestatuses">Confirmed, Confirmed, Confirmed</td><td class="tpcol-ratenames">a, b, c</td></tr>
</tbody></table></div>
<script>
  window.guardados = 0; window.ultimo = null;
  document.getElementById('tb').addEventListener('click', e => {
    const td = e.target.closest('td.tpcol-rateperiod'); if (!td) return;
    const tr = td.parentElement, rango = td.textContent.trim().split(' - '), pc = tr.querySelector('.tpcol-pricecodecode').textContent.trim();
    const nombres = tr.querySelector('.tpcol-ratenames').textContent.split(',').map(s => s.trim());
    const sets = tr.querySelector('.tpcol-ratestatuses').textContent.split(',').map((s, i) => ({nombre: nombres[i], status: s.trim(), rates: ['100', '']}));
    if (window.EXTRA) sets.push({nombre: 'extra', status: 'Confirmed', rates: ['100', '']});
    let cur = 0;
    const d = document.createElement('tp-dialog');
    d.innerHTML = '<div class="tpmodal-productcosts"><h3>%(hab)s   ' + rango[0] + '/' + rango[1] + ' "' + pc + '"</h3>'
      + '<div id="rate-set"><tp-button><button class="tpbutton tpbutton-navleft"></button></tp-button>'
      + '<div class="tpcombo"><input readonly></div><tp-button><button class="tpbutton tpbutton-navright"></button></tp-button></div>'
      + '<ul><li id="tptablabel-tabs-rates">Rates</li><li id="tptablabel-tabs-rateset">Rate Set</li></ul>'
      + '<div id="tabs-rates" class="tptab"><div id="costs-panel"><table><tbody>'
      + '<tr><td class="tpcol-cost"><input class="tpnumber-ratecostamount"></td><td class="tpcol-cost"><input></td></tr>'
      + '<tr><td class="tpcol-cost"><input class="tpnumber-ratecostamount"></td><td class="tpcol-cost"><input></td></tr>'
      + '</tbody></table></div></div><div id="tabs-rateset" class="tptab tab-hidden"><div id="rs"></div></div>'
      + '<tp-button class="save"><button disabled>Save</button></tp-button><tp-button class="cancel"><button>Exit</button></tp-button></div>';
    document.body.appendChild(d);
    const save = d.querySelector('tp-button.save button'), izq = d.querySelector('.tpbutton-navleft'), der = d.querySelector('.tpbutton-navright');
    const filas = Array.from(d.querySelectorAll('#costs-panel tbody tr'));
    function pintar() {
      d.querySelector('.tpcombo input').value = sets[cur].nombre;
      izq.disabled = cur === 0; der.disabled = cur === sets.length - 1;
      filas.forEach((f, i) => { const ins = f.querySelectorAll('input'); ins[0].value = i ? '' : sets[cur].rates[0]; ins[1].value = i ? '' : sets[cur].rates[0]; });
      d.querySelector('#rs').innerHTML = '<tp-group class="tpgroup-ratestatus">' + ['Confirmed','Provisional','Terminal','Closed','Manual'].map((s, i) =>
        '<tp-radio><label class="tpradio"><input type="button" id="st' + i + '" class="' + (s === sets[cur].status ? 'checked' : '') + '"></label></tp-radio><label for="st' + i + '">' + s + '</label>').join('') + '</tp-group>';
      d.querySelectorAll('#rs input').forEach(r => r.addEventListener('click', () => {
        d.querySelectorAll('#rs input').forEach(o => o.classList.remove('checked')); r.classList.add('checked');
        sets[cur].status = d.querySelector('label[for="' + r.id + '"]').textContent; save.disabled = false; }));
    }
    pintar();
    der.addEventListener('click', () => { cur++; setTimeout(pintar, 80); });          // Angular re-renderiza con retraso
    izq.addEventListener('click', () => { cur--; setTimeout(pintar, 80); });
    filas.forEach(f => f.querySelector('.tpnumber-ratecostamount').addEventListener('change', e => {
      f.querySelectorAll('input').forEach(o => { o.value = e.target.value; }); sets[cur].rates[0] = filas[0].querySelector('input').value; save.disabled = false; }));
    d.querySelector('#tptablabel-tabs-rates').addEventListener('click', () => { d.querySelector('#tabs-rates').classList.remove('tab-hidden'); d.querySelector('#tabs-rateset').classList.add('tab-hidden'); });
    d.querySelector('#tptablabel-tabs-rateset').addEventListener('click', () => { d.querySelector('#tabs-rateset').classList.remove('tab-hidden'); d.querySelector('#tabs-rates').classList.add('tab-hidden'); });
    save.addEventListener('click', () => { tr.querySelector('.tpcol-ratestatuses').textContent = sets.map(s => s.status).join(', ');
      window.guardados++; window.ultimo = JSON.stringify(sets); d.remove(); });
    d.querySelector('tp-button.cancel button').addEventListener('click', () => d.remove());
  });
</script></body></html>
""" % {"hab": HAB}


@pytest.fixture()
def drv_sets():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page()
        pg.set_content(HTML_RATESETS)
        yield Driver(pg)
        b.close()


RANGO_SETS = [(date(2026, 5, 22), date(2026, 5, 24))]


def test_el_plan_decide_cada_rate_set_por_separado(drv_sets):
    ps = rt.leer_periodos(drv_sets)
    plan = rp.planear(ps, RANGO_SETS)
    por_pc = {e.periodo.pc: e.por_set for e in plan.ediciones}
    assert por_pc == {"TR": ("Manual", "Manual"), "RACK": ("Closed", "Closed"), "ND": ("Manual", "Manual", "Manual")}


def test_editar_periodo_con_dos_rate_sets_cambia_los_dos_y_guarda_una_vez(drv_sets):
    import json
    tr = next(e for e in rp.planear(rt.leer_periodos(drv_sets), RANGO_SETS).ediciones if e.periodo.pc == "TR")
    rt.editar_periodo(drv_sets, HAB, tr)
    assert drv_sets.execute_script("return window.guardados;") == 1                     # un solo Save
    sets = json.loads(drv_sets.execute_script("return window.ultimo;"))
    assert [(s["status"], s["rates"][0]) for s in sets] == [("Manual", "0"), ("Manual", "0")]
    assert next(p for p in rt.leer_periodos(drv_sets) if p.pc == "TR").status == "Manual, Manual"
    assert drv_sets.find_elements(None, "body > tp-dialog") == []


def test_con_tres_rate_sets_y_uno_ya_cerrado_solo_se_tocan_los_que_corresponden(drv_sets):
    import json
    drv_sets.execute_script("""const f = document.querySelectorAll('#tb tr')[1];     // RACK -> TR: 'Confirmed, Manual'
        f.querySelector('.tpcol-pricecodecode').textContent = 'TR'; f.querySelector('.tpcol-ratenames').textContent = '7-7, 8-8';""")
    e = next(e for e in rp.planear(rt.leer_periodos(drv_sets), RANGO_SETS).ediciones
             if e.periodo.status == "Confirmed, Manual")
    assert e.por_set == ("Manual", None)                                   # el 2.º ya es Manual: no se toca
    rt.editar_periodo(drv_sets, HAB, e)
    sets = json.loads(drv_sets.execute_script("return window.ultimo;"))
    assert [(s["status"], s["rates"][0]) for s in sets] == [("Manual", "0"), ("Manual", "100")]    # la tarifa del 2.º no se tocó


def test_tres_rate_sets_se_recorren_todos(drv_sets):
    import json
    nd = next(e for e in rp.planear(rt.leer_periodos(drv_sets), RANGO_SETS).ediciones if e.periodo.pc == "ND")
    rt.editar_periodo(drv_sets, HAB, nd)
    sets = json.loads(drv_sets.execute_script("return window.ultimo;"))
    assert [(s["status"], s["rates"][0]) for s in sets] == [("Manual", "0")] * 3


def test_si_el_selector_tiene_mas_rate_sets_que_la_grilla_no_guarda(drv_sets):
    drv_sets.execute_script("window.EXTRA = true;")
    tr = next(e for e in rp.planear(rt.leer_periodos(drv_sets), RANGO_SETS).ediciones if e.periodo.pc == "TR")
    with pytest.raises(FlujoError, match="rate set"):
        rt.editar_periodo(drv_sets, HAB, tr)
    assert drv_sets.execute_script("return window.guardados;") == 0
    assert drv_sets.find_elements(None, "body > tp-dialog") == []


def test_destinos_distintos_a_la_cantidad_de_rate_sets_se_frenan(drv_sets):
    tr = rt.leer_periodos(drv_sets)[0]
    with pytest.raises(rp.PlanRatesError):
        rt.editar_periodo(drv_sets, HAB, rp.Edicion(tr, "Manual", ("Manual",)))


def test_periodo_ya_procesado_a_medias_se_completa_para_que_todos_queden_iguales(drv_sets):
    import json
    drv_sets.execute_script("document.querySelectorAll('#tb tr')[0].querySelector('.tpcol-ratestatuses').textContent = 'Manual, Confirmed';")
    e = next(e for e in rp.planear(rt.leer_periodos(drv_sets), RANGO_SETS).ediciones if e.periodo.pc == "TR")
    assert e.por_set == (None, "Manual")
    rt.editar_periodo(drv_sets, HAB, e)
    sets = json.loads(drv_sets.execute_script("return window.ultimo;"))
    assert [(s["status"], s["rates"][0]) for s in sets] == [("Manual", "100"), ("Manual", "0")]    # solo se tocó el 2.º
    assert next(p for p in rt.leer_periodos(drv_sets) if p.pc == "TR").status == "Manual, Manual"
