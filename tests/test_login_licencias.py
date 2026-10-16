"""Reintento de login por licencias agotadas, estado.json de la corrida y capturas solo de errores."""
import json
import os

import pytest

import runner
from common import tourplan as tp


class _Driver:
    def __init__(self, cerrados):
        self.cerrados = cerrados

    def quit(self):
        self.cerrados.append(1)

    def save_screenshot(self, ruta):
        open(ruta, "wb").write(b"x")
        return True


class _TP:
    LicenciasAgotadasError = tp.LicenciasAgotadasError

    def __init__(self, fallos):
        self.fallos, self.logins, self.cerrados = fallos, 0, []

    def crear_driver(self):
        return _Driver(self.cerrados)

    def login(self, driver):
        self.logins += 1
        if self.fallos:
            self.fallos -= 1
            raise tp.LicenciasAgotadasError("sin licencias")


@pytest.fixture(autouse=True)
def _rapido(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "LICENCIAS_ESPERA_MIN", 0.001)
    monkeypatch.setattr(runner, "abort_solicitado", lambda: False)
    monkeypatch.setattr(runner, "RUN_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "_estado", {})


def test_reintenta_hasta_conseguir_licencia():
    t = _TP(fallos=2)
    assert runner.login_con_reintentos(t) is not None
    assert t.logins == 3 and len(t.cerrados) == 2          # cierra Chrome entre un intento y otro


def test_se_agotan_los_intentos():
    t = _TP(fallos=99)
    with pytest.raises(tp.LicenciasAgotadasError, match="tras 3 intentos"):
        runner.login_con_reintentos(t)
    assert t.logins == runner.LICENCIAS_MAX_INTENTOS and len(t.cerrados) == 3


def test_abort_durante_la_espera(monkeypatch):
    t = _TP(fallos=99)
    llamadas = iter([False, True, True])                     # no hay abort al empezar, sí durante la espera
    monkeypatch.setattr(runner, "abort_solicitado", lambda: next(llamadas, True))
    assert runner.login_con_reintentos(t) is None
    assert t.logins == 1


def test_otro_error_de_login_no_se_reintenta():
    class _Mal(_TP):
        def login(self, driver):
            self.logins += 1
            raise AssertionError("Login falló")
    t = _Mal(fallos=0)
    with pytest.raises(AssertionError):
        runner.login_con_reintentos(t)
    assert t.logins == 1 and len(t.cerrados) == 1


def test_estado_json_resumen_y_estado_final(tmp_path):
    runner.contar_fase("OK")
    runner.contar_fase("ERROR: algo")
    runner.contar_fase("NO APLICA")
    runner.contar_fase("")                                   # lectura: no cuenta
    runner.finalizar_estado(runner.LICENCIAS_EXIT_CODE)
    est = json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))
    assert est["estado_final"] == "sin_licencias" and est["finalizada"] is True
    assert (est["resumen"]["ok"], est["resumen"]["error"], est["resumen"]["omitidos"]) == (1, 1, 1)


def test_capturas_solo_de_errores(tmp_path):
    d = _Driver([])
    for nombre in ("login_page", "post_login", "logout_done", "error_6RABA1", "login_sin_licencias"):
        tp.ss(d, nombre, ss_dir=str(tmp_path / "ss"))
    nombres = sorted(os.listdir(tmp_path / "ss"))
    assert len(nombres) == 2 and "error_6RABA1" in nombres[0] and "login_sin_licencias" in nombres[1]
