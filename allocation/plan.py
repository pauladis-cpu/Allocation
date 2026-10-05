"""Decisión de cierre por fecha en una allocation (spec sección 4). Lógica pura,
sin Selenium: recibe lo leído de Tourplan y devuelve qué hacer.

| Situación  | Acción                      | ¿Ya cerrada?                    |
| Used = 0   | Max = 0                     | Max = 0                         |
| Used > 0   | Max = Used y Release = 9999 | Max = Used y Release = 9999     |

- Cada campo se corrige solo si hace falta (puede faltar solo el Release).
- Si Max < Used y la fecha debe cerrarse, Max sube a Used: es la ÚNICA situación
  en que Max sube. Nunca se reabre una fecha.
"""

from dataclasses import dataclass
from datetime import date

from allocation.constantes import RELEASE_CLOSED

CERRAR = "cerrar"
YA_CERRADA = "ya_cerrada"
SIN_FILA = "sin_fila"


@dataclass(frozen=True)
class DiaAllocation:
    fecha: date
    used: int
    max: int
    release: int


@dataclass(frozen=True)
class Accion:
    fecha: date
    tipo: str                    # CERRAR | YA_CERRADA | SIN_FILA
    nuevo_max: object = None     # int | None (None = no tocar)
    nuevo_release: object = None  # int | None (None = no tocar)
    detalle: str = ""


class ReaperturaProhibida(AssertionError):
    pass


def planear_dia(dia):
    """Acción para una fecha que existe en la grilla."""
    objetivo_max = 0 if dia.used == 0 else dia.used
    cambia_max = dia.max != objetivo_max
    cambia_rel = dia.used > 0 and dia.release != RELEASE_CLOSED
    if not cambia_max and not cambia_rel:
        return Accion(dia.fecha, YA_CERRADA)
    accion = Accion(
        dia.fecha, CERRAR,
        nuevo_max=objetivo_max if cambia_max else None,
        nuevo_release=RELEASE_CLOSED if cambia_rel else None,
        detalle=f"Used={dia.used} Max={dia.max} Rel={dia.release}")
    verificar_no_reabre(dia, accion)
    return accion


def verificar_no_reabre(dia, accion):
    """Barrera dura: Max solo sube cuando estaba por debajo de Used (y queda en Used);
    Release solo cambia a 9999 y solo si Used > 0."""
    if accion.nuevo_max is not None and accion.nuevo_max > dia.max and not (
            dia.max < dia.used and accion.nuevo_max == dia.used):
        raise ReaperturaProhibida(f"{dia}: Max {dia.max} -> {accion.nuevo_max}")
    if accion.nuevo_release is not None and (
            accion.nuevo_release != RELEASE_CLOSED or dia.used == 0):
        raise ReaperturaProhibida(f"{dia}: Release {dia.release} -> {accion.nuevo_release}")


def planear(dias_por_fecha, fechas):
    """dias_por_fecha: {date: DiaAllocation} leídos de la grilla. fechas: las del pedido.
    Devuelve una Accion por fecha pedida, en orden."""
    acciones = []
    for f in sorted(set(fechas)):
        dia = dias_por_fecha.get(f)
        acciones.append(Accion(f, SIN_FILA) if dia is None else planear_dia(dia))
    return acciones


def _rangos_txt(fechas):
    from allocation.fechas import agrupar_rangos
    partes = []
    for a, b in agrupar_rangos(fechas):
        partes.append(a.strftime("%d/%m/%y") if a == b else f"{a:%d/%m/%y}-{b:%d/%m/%y}")
    return ", ".join(partes)


def resumen(codigo_allocation, acciones, lectura=True):
    """Texto de OBSERVACIONES para una allocation."""
    cerrar = [a.fecha for a in acciones if a.tipo == CERRAR]
    ya = [a.fecha for a in acciones if a.tipo == YA_CERRADA]
    sin = [a.fecha for a in acciones if a.tipo == SIN_FILA]
    verbo = "cerraría" if lectura else "cerró"
    partes = [f"{codigo_allocation}: {verbo} {len(cerrar)}" + (f" ({_rangos_txt(cerrar)})" if cerrar else "")]
    partes.append(f"ya cerradas {len(ya)}" + (f" ({_rangos_txt(ya)})" if ya else ""))
    if sin:
        partes.append(f"SIN FILA en la allocation {len(sin)} ({_rangos_txt(sin)}): no se tocan")
    return " · ".join(partes)
