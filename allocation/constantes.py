"""Reglas de negocio y constantes fijas, en un solo lugar (spec sección 4)."""

# ── Reglas de negocio (sección 4) ───────────────────────────────────────────
PRICE_CODES_MANUAL = {"TR", "ND", "EM"}   # el resto va en Closed
EXCLUDED_OPTIONS = {"600HTL", "ROOMS"}    # nunca se cierran, ni con TODAS
CLOSEABLE_SERVICE_TYPES = {"HT"}
RELEASE_CLOSED = 9999
WINDOW_YEARS = 2                          # filtro de Allocations: hoy + 2 años

# ── Google Sheet ────────────────────────────────────────────────────────────
SHEET_URL_DEFAULT = (
    "https://docs.google.com/spreadsheets/d/"
    "1SCp0CQnYphKYWTxSgL1AIpvyZ7z1HThiGf1C-g3AUug/edit"
)
HOJA_ALLOCATIONS = "ALLOCATIONS"
HOJA_COLA = "COLA"
HOJA_HISTORIAL = "HISTORIAL"

# ── Tourplan ────────────────────────────────────────────────────────────────
# Test y Producción son base paths distintos (no un dominio compartido).
URL_TEST = "https://tourplannx.eurotur.com.ar/TourplanNX_Test"
URL_PRODUCCION = "https://tourplannx.eurotur.com.ar/tourplannx"
URLS_ENTORNO = {"test": URL_TEST, "produccion": URL_PRODUCCION}

# ── Modos y estados de la cola ──────────────────────────────────────────────
MODO_LECTURA = "lectura"
MODO_APLICAR = "aplicar"

ESTADO_PENDIENTE = "PENDIENTE"
ESTADO_EN_CURSO = "EN CURSO"
ESTADO_OK = "OK"
ESTADO_SALTEADO = "SALTEADO"
ESTADO_ERROR = "ERROR"   # se escribe como "ERROR: detalle"

# Valor de "Allocation(es)" en la cola para "todas las del hotel".
ALLOCATIONS_TODAS = "TODAS"
SEPARADOR_ALLOCATIONS = ";"
