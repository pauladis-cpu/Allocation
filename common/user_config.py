"""
user_config.py — Configuración local por persona/PC de la app de Allocation.

Mismo patrón que user_config.py de Drive-TP-NX-App: se guarda en una carpeta
del perfil del usuario, FUERA del repo (nunca se commitea ni se comparte).
Carpeta propia (~/.tourplan-allocation) para no pisar la config de la otra app
si conviven en la misma PC.

Campos:
  - "sheet_url": URL del Google Sheet del registro (ALLOCATIONS/COLA/HISTORIAL).
  - "entorno": "test" (default) o "produccion". Producción es una decisión
    deliberada, nunca el default.
  - "tp_usuario" / "tp_password": credenciales de Tourplan (texto plano, local).
  - "nombre": cómo se muestra "Cargado por" / "Tomado por" en la cola.
  - "headless": Chrome sin ventana (default False).
  - "minutos_abandono": un pedido EN CURSO hace más de N minutos se muestra
    como posiblemente abandonado.
"""

import json
import os

from allocation.constantes import SHEET_URL_DEFAULT

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".tourplan-allocation")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
TOKEN_PATH = os.path.join(CONFIG_DIR, "token.json")

_CREDENTIALS_PROPIO = os.path.join(CONFIG_DIR, "credentials.json")
_CREDENTIALS_APP_VIEJA = os.path.join(
    os.path.expanduser("~"), ".tourplan-nx-app", "credentials.json")

# Si todavía no copiaste credentials.json a la carpeta de esta app pero ya lo
# tenés en la de Drive-TP-NX-App (mismo cliente OAuth), se reutiliza ese.
if not os.path.exists(_CREDENTIALS_PROPIO) and os.path.exists(_CREDENTIALS_APP_VIEJA):
    CREDENTIALS_PATH = _CREDENTIALS_APP_VIEJA
else:
    CREDENTIALS_PATH = _CREDENTIALS_PROPIO

VALORES_DEFAULT = {
    "sheet_url": SHEET_URL_DEFAULT,
    "entorno": "test",
    "tp_usuario": "",
    "tp_password": "",
    "nombre": "",
    "headless": False,
    "minutos_abandono": 30,
}


def cargar():
    """Devuelve la config guardada, completando con los defaults cualquier
    clave que todavía no exista."""
    cfg = dict(VALORES_DEFAULT)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def guardar(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
