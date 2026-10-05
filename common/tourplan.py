"""
tourplan.py — helpers de Selenium compartidos por los flujos de Tourplan NX.

Los helpers de abajo (jc, wait, ss, esperas, set_val*, login, logout, fechas)
son copia textual de los que ya funcionan en Drive-TP-NX-App
(scripts/modificar_rate_name_text/modificar_rate_name_text.py, validados contra
Tourplan), reunidos acá una sola vez en vez de repetirlos en cada script.
Lo único propio: la configuración por variables de entorno TOURPLAN_* y
crear_driver(), que busca Chrome recién al llamarlo (no al importar).
"""
import os
import re
import tempfile
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from allocation.constantes import URL_TEST
from common.chrome_bootstrap import find_or_prepare_chrome

# Multiplicador de tiempos de espera. 1.0 = Test | 1.5 = producción.
VELOCIDAD = float(os.environ.get("TOURPLAN_VELOCIDAD", "1.0"))

# ── CONFIG (variables de entorno que setea la app) ─────────────────────────
USERNAME = os.environ.get("TOURPLAN_USERNAME", "")
PASSWORD = os.environ.get("TOURPLAN_PASSWORD", "")
BASE_URL = os.environ.get("TOURPLAN_BASE_URL", URL_TEST)
SS_DIR = os.environ.get("TOURPLAN_SS_DIR", "screenshots")
HEADLESS = os.environ.get("TOURPLAN_HEADLESS", "0").strip() in ("1", "true", "True")

CHROMIUM_BIN = None
ver_chrome = ""


def crear_driver():
    global CHROMIUM_BIN, ver_chrome
    CHROMIUM_BIN, ver_chrome = find_or_prepare_chrome()
    opts = Options()
    # Sin ventana visible solo si se pide explícitamente (TOURPLAN_HEADLESS).
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1704,1012")
    opts.add_argument("--disable-gpu")

    # Perfil temporal y aislado para esta corrida.
    _profile_dir = tempfile.mkdtemp(prefix="tourplan_chrome_profile_")
    opts.add_argument(f"--user-data-dir={_profile_dir}")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")

    if CHROMIUM_BIN:
        opts.binary_location = CHROMIUM_BIN
        print(f"Chrome binary: {CHROMIUM_BIN}  ({ver_chrome})")
    else:
        raise RuntimeError("No se encontró Chrome funcional.")

    log_path = os.path.join(tempfile.gettempdir(), "chromedriver.log")
    try:
        drv_path = ChromeDriverManager().install()
        print(f"Chromedriver: {drv_path}")
        svc = Service(executable_path=drv_path, log_output=log_path)
        d = webdriver.Chrome(service=svc, options=opts)
        print("✅ Driver iniciado")
        return d
    except Exception as e:
        if os.path.exists(log_path):
            with open(log_path) as f:
                print(f"\n--- ChromeDriver log ---\n{f.read()[-3000:]}\n---")
        raise RuntimeError(f"No se pudo iniciar Chrome.\nError: {e}")



# ── Helpers mínimos de DOM ──────────────────────────────────────────────
def jc(driver, el):
    """Click vía JavaScript — único método confiable en Angular."""
    driver.execute_script("arguments[0].click();", el)


def wait(driver, css, t=12):
    return WebDriverWait(driver, t).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, css)))


def waitx(driver, xpath, t=12):
    return WebDriverWait(driver, t).until(
        EC.presence_of_element_located((By.XPATH, xpath)))


_ss_n = [0]


def ss(driver, nombre, ss_dir=SS_DIR):
    _ss_n[0] += 1
    nombre_seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", nombre)[:60]
    os.makedirs(ss_dir, exist_ok=True)
    p = f"{ss_dir}/{_ss_n[0]:03d}_{nombre_seguro}_{int(time.time())}.png"
    try:
        ok = driver.save_screenshot(p)
        if not ok:
            print(f"  ⚠️ No se pudo guardar captura: {os.path.basename(p)}")
            return None
        print(f"  📸 {os.path.basename(p)}")
        return p
    except Exception as e:
        print(f"  ⚠️ Error guardando captura ({e})")
        return None


def dump(driver, nombre, ss_dir=SS_DIR):
    os.makedirs(ss_dir, exist_ok=True)
    p = f"{ss_dir}/{nombre}_{int(time.time())}.html"
    with open(p, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"  💾 HTML: {p}")


def cerrar_nav_backdrop(driver, timeout=3, velocidad=1.0):
    """Limpia el backdrop (.tpnavbackdrop) que a veces deja colgado el menú
    hamburguesa tras cerrarlo. Ver skill buscando-productos-en-tourplan."""
    fin = time.time() + timeout * velocidad
    while time.time() < fin:
        if not driver.find_elements(By.CSS_SELECTOR, ".tpnavbackdrop"):
            return
        time.sleep(0.2)
    driver.execute_script("""
        document.querySelectorAll('.tpnavbackdrop').forEach(function(e){ e.remove(); });
    """)
    print("    ⚠ .tpnavbackdrop seguía presente tras cerrar el menú — removido a mano")


def esperar_fin_carga(driver, timeout=15, velocidad=1.0):
    """Tourplan muestra un <dialog> nativo 'PLEASE WAIT...' mientras termina
    de procesar la fila anterior — esperar a que cierre antes de clickear la
    lupa de búsqueda de la fila siguiente. Ver skill buscando-productos-en-tourplan."""
    fin = time.time() + timeout * velocidad
    while time.time() < fin:
        if not driver.find_elements(By.CSS_SELECTOR, "dialog[open]"):
            return
        time.sleep(0.3)
    print("    ⚠ El dialog de carga ('PLEASE WAIT...') seguía abierto tras esperar")


# ── Fechas / formatos Tourplan ──────────────────────────────────────────
MESES_ES = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def parsear_fecha(txt):
    """Acepta ISO (YYYY-MM-DD, típico de openpyxl) o dd/Mon/yyyy /
    dd/mm/yyyy / dd/mm/yy (típico de Tourplan/Excel)."""
    if not txt:
        return None
    if isinstance(txt, datetime):
        return txt
    txt = str(txt).strip()
    if len(txt) >= 10 and txt[4] == "-" and txt[7] == "-":
        try:
            return datetime.fromisoformat(txt[:10])
        except Exception:
            pass
    p = txt.split("/")
    if len(p) == 3:
        try:
            dia = int(p[0])
            mes_raw = p[1]
            mes = MESES_ES.get(mes_raw[:3].capitalize(), None) or int(mes_raw)
            anio_raw = int(p[2])
            anio = anio_raw + 2000 if anio_raw < 100 else anio_raw
            return datetime(anio, mes, dia)
        except Exception:
            pass
    return None


def fmt_tp(dt):
    """dd/Mon/yyyy — formato que esperan los inputs de fecha de Tourplan."""
    meses = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
    return f"{dt.day:02d}/{meses[dt.month]}/{dt.year}"


# ── Escritura Angular (set_val / set_val_con_blur) ──────────────────────
def set_val(driver, el, value):
    """Versión corta — inputs de filtro/búsqueda (no requieren blur)."""
    driver.execute_script("""
        var inp = arguments[0], val = arguments[1];
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, val);
        inp.dispatchEvent(new Event('input',  {bubbles:true}));
        inp.dispatchEvent(new Event('change', {bubbles:true}));
    """, el, value)


def set_val_con_blur(driver, el, value):
    """Versión completa — necesaria para inputs tp-validator/tp-number que
    solo confirman el valor al perder foco (blur). Replica el flujo humano:
    focus → setter nativo → eventos → blur."""
    driver.execute_script("""
        var inp = arguments[0], val = arguments[1];
        inp.focus();
        inp.dispatchEvent(new Event('focus', {bubbles:true}));
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, val);
        inp.dispatchEvent(new Event('input',  {bubbles:true}));
        inp.dispatchEvent(new Event('change', {bubbles:true}));
        inp.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
        inp.blur();
        inp.dispatchEvent(new Event('blur',     {bubbles:true}));
        inp.dispatchEvent(new Event('focusout', {bubbles:true}));
    """, el, value)


# ── Login / logout ───────────────────────────────────────────────────────
def login(driver):
    print("🔐 Login...")
    driver.get(f"{BASE_URL}/#/login")
    time.sleep(6 * VELOCIDAD)
    ss(driver, "login_page")

    def _campos_visibles():
        return driver.execute_script("""
            function vis(e){return !!(e && (e.offsetWidth||e.offsetHeight
                                      ||e.getClientRects().length)
                                      && !e.disabled);}
            var txt = Array.from(document.querySelectorAll(
                "input[type='text'], input:not([type])")).filter(vis);
            var pwd = Array.from(document.querySelectorAll(
                "input[type='password']")).filter(vis);
            return [txt[0]||null, pwd[0]||null];
        """)

    u_el = p_el = None
    for intento in range(15):
        u_el, p_el = _campos_visibles()
        if u_el and p_el:
            break
        time.sleep(2 * VELOCIDAD)
    if not (u_el and p_el):
        ss(driver, "login_sin_campos")
        raise Exception("No aparecieron los campos de login (usuario/password)")

    def _set(el, valor):
        try:
            el.clear()
        except Exception:
            pass
        try:
            el.click()
        except Exception:
            pass
        try:
            el.send_keys(valor)
        except Exception:
            driver.execute_script("""
                var el=arguments[0], v=arguments[1];
                var s=Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype,'value').set;
                s.call(el,v);
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
            """, el, valor)

    _set(u_el, USERNAME)
    _set(p_el, PASSWORD)
    time.sleep(0.5)

    clic = driver.execute_script("""
        function vis(e){return !!(e && (e.offsetWidth||e.offsetHeight
                                  ||e.getClientRects().length) && !e.disabled);}
        var b = Array.from(document.querySelectorAll(
            "button.login, button[type='submit'], button")).filter(vis)
            .find(function(x){return /log\\s*in|ingresar|entrar|sign\\s*in/i
                                     .test((x.innerText||'')) ||
                                     x.classList.contains('login');});
        if (b){ b.click(); return (b.innerText||'button.login').trim(); }
        return null;
    """)
    if not clic:
        try:
            p_el.send_keys(Keys.ENTER)
        except Exception:
            pass
    time.sleep(8 * VELOCIDAD)
    assert "login" not in driver.current_url.lower(), "Login falló"
    ss(driver, "post_login")
    print("✅ Login OK")


def logout(driver):
    """Cierra ventanas secundarias y hace logout real. Ver skill
    arrancando-un-script-de-tourplan/references/licencias-y-sesiones.md:
    Tourplan tiene licencias concurrentes limitadas, una sesión colgada
    puede bloquear a otra persona real."""
    print("\n🔒 Finalización: cerrando ventanas y haciendo logout...")
    try:
        principal = driver.window_handles[0]
        for h in driver.window_handles[1:]:
            try:
                driver.switch_to.window(h)
                driver.close()
            except Exception:
                pass
        driver.switch_to.window(principal)
    except Exception:
        pass

    def _click_item(regex):
        return driver.execute_script("""
            var rx = new RegExp(arguments[0], 'i');
            var els = Array.from(document.querySelectorAll(
                'li, label, a, button, span, div'));
            var best = null;
            for (var el of els){
                if (!el.offsetParent) continue;
                var t = (el.innerText || '').trim();
                if (!t || t.length > 40 || !rx.test(t)) continue;
                if (!best || t.length <= (best.innerText||'').trim().length)
                    best = el;
            }
            if (!best) return null;
            best.click();
            return (best.innerText || '').trim().slice(0, 40);
        """, regex)

    def _en_login():
        return driver.execute_script("""
            var pwd = document.querySelector("input[type='password']");
            return (pwd && pwd.offsetParent !== null) ||
                   /login/i.test(window.location.href);
        """)

    try:
        driver.get(f"{BASE_URL}/#/home")
        time.sleep(4 * VELOCIDAD)
        ss(driver, "logout_home")

        clicked = None
        try:
            btn_panel = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#openUserPanel")))
            jc(driver, btn_panel)
            time.sleep(2 * VELOCIDAD)
            ss(driver, "logout_usermenu")
            btn_logout = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "div.panelHeader tp-button button, div.panelHeader button")))
            texto_btn = (btn_logout.text or "Logout").strip()
            jc(driver, btn_logout)
            clicked = texto_btn or "Logout"
        except Exception as _e:
            print(f"    ⚠ Flujo #openUserPanel falló ({_e}) — fallback por texto")

        rx_logout = r"^(log\s?out|sign\s?out|cerrar sesi)"
        if not clicked:
            clicked = _click_item(rx_logout)
        if not clicked:
            padre = _click_item(r"logged in as")
            time.sleep(2 * VELOCIDAD)
            if padre:
                clicked = _click_item(rx_logout)

        time.sleep(5 * VELOCIDAD)
        ss(driver, "logout_done")

        if clicked and _en_login():
            print(f"  🔓 Logout OK (click en '{clicked}', volvió al login)")
        elif clicked:
            print(f"  ⚠ Click en '{clicked}' pero NO volvió al login — logout no confirmado")
        else:
            print("  ⚠ No encontré la opción LOG OUT en el menú — logout no realizado")
    except Exception as e:
        print(f"  ⚠ Error en logout: {e}")

