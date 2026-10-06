"""Decisión de cierre de tarifas por período + price code (spec secciones 4 y 6.4).
Lógica pura, sin Selenium: recibe la grilla de períodos leída de Rates y los rangos de
fechas a cerrar, y devuelve qué cortes (splits) y qué ediciones hacen falta.

Reglas:
  - Una fila de la grilla es un par (período, price code).
  - Status objetivo: Manual para TR/ND/EM, Closed para el resto.
  - Closed -> se saltea. Manual -> se saltea si el objetivo es Manual, si no pasa a Closed.
    Confirmed y Provisional -> pasan al objetivo (TR/ND/EM a Manual, el resto a Closed).
    Terminal -> pasa a Closed sin importar el price code.
  - El price code FX NUNCA se toca: ni se edita ni se corta su período.
  - Un período en Closed NUNCA pasa a Manual (dos barreras: acá y justo antes del clic).
  - Un período por rango consecutivo. No se fusionan períodos existentes.
  - Solo se parte donde el borde del rango cae ADENTRO del período.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from allocation.constantes import PRICE_CODES_MANUAL

CONFIRMED, PROVISIONAL, TERMINAL, CLOSED, MANUAL = "Confirmed", "Provisional", "Terminal", "Closed", "Manual"
STATUS_CONOCIDOS = {s.casefold(): s for s in (CONFIRMED, PROVISIONAL, TERMINAL, CLOSED, MANUAL)}
RATE_NAME_ESPERADO = "standard"
PRICE_CODE_INTOCABLE = "FX"   # nunca se hacen cambios en sus períodos


class PlanRatesError(Exception):
    """Algo no esperado en la grilla: se frena el pedido y se informa."""


@dataclass(frozen=True)
class Periodo:
    ini: date
    fin: date
    pc: str
    status: str
    rate_name: str = "Standard"


@dataclass(frozen=True)
class Corte:
    ini: date      # período a dividir
    fin: date
    fecha: date    # el nuevo período empieza en esta fecha: [ini, fecha-1] y [fecha, fin]


@dataclass(frozen=True)
class Edicion:
    periodo: Periodo
    nuevo_status: str


@dataclass
class Plan:
    cortes: list = field(default_factory=list)
    ediciones: list = field(default_factory=list)
    ya_cerrados: list = field(default_factory=list)   # filas que se saltean (ya cerradas)
    intocables: list = field(default_factory=list)    # filas del price code FX: nunca se tocan
    sin_periodo: list = field(default_factory=list)   # fechas del pedido que ningún período cubre


def normalizar_status(txt):
    """'Manual' -> 'Manual'. Más de un status en la celda o desconocido -> frenar."""
    palabras = re.findall(r"[A-Za-z]+", txt or "")
    conocidos = {STATUS_CONOCIDOS.get(p.casefold()) for p in palabras}
    if len(palabras) != 1 or None in conocidos:
        raise PlanRatesError(f"Status ambiguo o desconocido en la grilla: {txt!r}")
    return STATUS_CONOCIDOS[palabras[0].casefold()]


def status_objetivo(pc):
    return MANUAL if (pc or "").strip().upper() in PRICE_CODES_MANUAL else CLOSED


def es_intocable(pc):
    return (pc or "").strip().upper() == PRICE_CODE_INTOCABLE


def decidir_status(actual, pc):
    """None = no hay que cambiar nada (ya cerrado, o price code FX); si no, el status al que hay que pasar."""
    if es_intocable(pc) or actual == CLOSED:
        return None
    if actual == TERMINAL:
        return CLOSED                      # Terminal -> Closed, sin importar el price code
    objetivo = status_objetivo(pc)
    if actual == MANUAL:
        return None if objetivo == MANUAL else CLOSED
    if actual in (CONFIRMED, PROVISIONAL):
        return objetivo
    raise PlanRatesError(f"Status {actual!r} no contemplado (price code {pc}): se frena el pedido, revisar a mano.")


def corte_afecta_a_intocables(periodos, corte):
    """True si alguna fila FX tiene exactamente el mismo período que se va a cortar. En ese caso el corte
    NO puede hacerse con 'Split All Applicable Price Codes' (cortaría también el período de FX)."""
    return any(es_intocable(p.pc) and (p.ini, p.fin) == (corte.ini, corte.fin) for p in periodos)


def verificar_no_pasa_de_closed_a_manual(actual, nuevo):
    """Segunda barrera, se llama justo antes del clic en el radio."""
    if actual == CLOSED and nuevo != CLOSED:
        raise PlanRatesError("Intento de sacar un período de Closed: nunca se reabre.")


def _solapa(p, a, b):
    return a <= p.fin and b >= p.ini


def planear(periodos, rangos):
    """periodos: lista de Periodo leídos de la grilla. rangos: [(a, b)] consecutivos a cerrar.
    Si hay cortes pendientes devuelve solo los cortes (hay que volver a leer la grilla y
    replanear); si no, devuelve las ediciones."""
    plan = Plan()
    cortes = set()
    por_editar = []
    for p in periodos:
        solapados = [(a, b) for a, b in rangos if _solapa(p, a, b)]
        if not solapados:
            continue
        if es_intocable(p.pc):
            plan.intocables.append(p)          # FX: no se evalúa ni se toca
            continue
        if p.rate_name.strip().casefold() != RATE_NAME_ESPERADO:
            raise PlanRatesError(
                f"Rate Name {p.rate_name!r} en {p.ini:%d/%m/%Y}-{p.fin:%d/%m/%Y} ({p.pc}): se esperaba Standard.")
        nuevo = decidir_status(normalizar_status(p.status), p.pc)
        if nuevo is None:
            plan.ya_cerrados.append(p)
            continue
        hay_corte = False
        for a, b in solapados:
            lo, hi = max(a, p.ini), min(b, p.fin)
            if lo > p.ini:
                cortes.add(Corte(p.ini, p.fin, lo)); hay_corte = True
            if hi < p.fin:
                cortes.add(Corte(p.ini, p.fin, hi + timedelta(days=1))); hay_corte = True
        if not hay_corte:
            por_editar.append(Edicion(p, nuevo))
    plan.cortes = sorted(cortes, key=lambda c: (c.ini, c.fin, c.fecha))
    if not plan.cortes:
        plan.ediciones = por_editar
    cubiertas = []
    for p in periodos:
        cubiertas.append((p.ini, p.fin))
    for a, b in rangos:
        d = a
        while d <= b:
            if not any(i <= d <= f for i, f in cubiertas):
                plan.sin_periodo.append(d)
            d += timedelta(days=1)
    return plan


MESES_MARGEN = 5   # meses hacia atrás desde la fecha más reciente pedida, por si los price codes tienen cortes distintos


def restar_meses(d, meses):
    """d menos N meses; si el día no existe en el mes destino (ej. 31 -> febrero) se usa el último día."""
    total = d.year * 12 + (d.month - 1) - meses
    anio, mes = divmod(total, 12)
    mes += 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue
    raise ValueError(d)


def limite_de_lectura(rangos, meses=None):
    """Fecha más allá de la cual (hacia atrás) ya no hace falta leer la grilla: la más ANTIGUA entre el inicio
    del rango más antiguo pedido y (fecha más reciente pedida - MESES_MARGEN). El margen cubre price codes
    con cortes distintos, cuyas filas pueden aparecer más abajo de lo que indicaría el orden."""
    meses = MESES_MARGEN if meses is None else meses
    return min(min(a for a, _ in rangos), restar_meses(max(b for _, b in rangos), meses))


def ya_paso_el_objetivo(periodos_en_orden, rangos, meses=None):
    """True si ya se leyó un período que empieza en o antes de limite_de_lectura(): la grilla viene de la
    fecha más lejana a la más reciente, así que lo que falta leer es más antiguo y no puede tocar lo pedido.
    Si lo leído hasta ahora parece venir en el orden contrario (ascendente), NO corta: se lee todo."""
    if not rangos or not periodos_en_orden:
        return False
    if periodos_en_orden[0].ini < periodos_en_orden[-1].ini:
        return False
    limite = limite_de_lectura(rangos, meses)
    return any(p.ini <= limite for p in periodos_en_orden)


def resumen(codigo_largo, plan, lectura=True):
    """Texto para OBSERVACIONES_CIERRE_TARIFA."""
    verbo = "cerraría" if lectura else "cerró"
    ed = len(plan.ediciones)
    partes = [f"{codigo_largo}: {verbo} {ed} período(s)/price code(s)"]
    if plan.cortes:
        partes.append(f"requiere {len(plan.cortes)} corte(s) previos (" + ", ".join(
            f"{c.fecha:%d/%m/%y}" for c in plan.cortes) + ")")
    partes.append(f"ya cerrados {len(plan.ya_cerrados)}")
    if plan.intocables:
        partes.append(f"{PRICE_CODE_INTOCABLE} sin tocar {len(plan.intocables)}")
    if plan.sin_periodo:
        from allocation.plan import _rangos_txt
        partes.append(f"SIN PERÍODO en Rates: {_rangos_txt(plan.sin_periodo)}")
    return " · ".join(partes)
