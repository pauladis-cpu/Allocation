"""Decisión de cierre de tarifas por período + price code (spec secciones 4 y 6.4).
Lógica pura, sin Selenium: recibe la grilla de períodos leída de Rates y los rangos de
fechas a cerrar, y devuelve qué cortes (splits) y qué ediciones hacen falta.

Reglas:
  - Una fila de la grilla es un par (período, price code).
  - Status objetivo: Manual para TR/ND/EM, Closed para el resto.
  - Closed -> se saltea. Manual -> se saltea si el objetivo es Manual, si no pasa a Closed.
    Confirmed -> pasa al objetivo. Provisional/Terminal -> frenar.
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


def decidir_status(actual, pc):
    """None = ya cerrado (se saltea); si no, el status al que hay que pasar."""
    if actual == CLOSED:
        return None
    objetivo = status_objetivo(pc)
    if actual == MANUAL:
        return None if objetivo == MANUAL else CLOSED
    if actual == CONFIRMED:
        return objetivo
    raise PlanRatesError(
        f"Un período está en {actual} (price code {pc}): se frena el pedido, revisar a mano.")


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


def direccion_orden(periodos):
    """'asc' | 'desc' | None: en qué orden vienen las filas de la grilla según los períodos leídos hasta ahora
    (se colapsan los repetidos consecutivos: varios price codes del mismo período). Hace falta ver al menos
    3 períodos distintos y que TODOS respeten el mismo sentido; si no, no se asume ningún orden."""
    inis = []
    for p in periodos:
        if not inis or inis[-1] != p.ini:
            inis.append(p.ini)
    if len(inis) < 3:
        return None
    if all(a >= b for a, b in zip(inis, inis[1:])):
        return "desc"
    if all(a <= b for a, b in zip(inis, inis[1:])):
        return "asc"
    return None


def ya_paso_el_objetivo(periodos_en_orden, rangos):
    """True si, dado el orden de la grilla, las filas que faltan leer ya no pueden tocar ninguno de los
    rangos a cerrar (se leyó una fila más allá del extremo del rango). Permite dejar de scrollear apenas se
    cubrió lo que importa. Sin un orden claro devuelve False (se lee todo)."""
    if not rangos or not periodos_en_orden:
        return False
    sentido = direccion_orden(periodos_en_orden)
    ultimo = periodos_en_orden[-1]
    if sentido == "asc":
        return ultimo.ini > max(b for _, b in rangos)       # más recientes que todo lo pedido
    if sentido == "desc":
        return ultimo.fin < min(a for a, _ in rangos)       # más antiguas que todo lo pedido
    return False


def resumen(codigo_largo, plan, lectura=True):
    """Texto para OBSERVACIONES_CIERRE_TARIFA."""
    verbo = "cerraría" if lectura else "cerró"
    ed = len(plan.ediciones)
    partes = [f"{codigo_largo}: {verbo} {ed} período(s)/price code(s)"]
    if plan.cortes:
        partes.append(f"requiere {len(plan.cortes)} corte(s) previos (" + ", ".join(
            f"{c.fecha:%d/%m/%y}" for c in plan.cortes) + ")")
    partes.append(f"ya cerrados {len(plan.ya_cerrados)}")
    if plan.sin_periodo:
        from allocation.plan import _rangos_txt
        partes.append(f"SIN PERÍODO en Rates: {_rangos_txt(plan.sin_periodo)}")
    return " · ".join(partes)
