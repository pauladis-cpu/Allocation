"""Lectura de la pestaña ALLOCATIONS (solo lectura para la app).

Las columnas se ubican por el NOMBRE del encabezado (sin distinguir mayúsculas,
tildes ni espacios sobrantes), nunca por la letra. Una fila = una allocation;
su identidad es el par (Código hotel, Allocation (código)).
"""

import unicodedata
from dataclasses import dataclass, field

from allocation.constantes import HOJA_ALLOCATIONS
from allocation.fechas import parsear_fecha_registro

# clave interna -> encabezado esperado en el Sheet
ENCABEZADOS = {
    "codigo_hotel": "Código hotel",
    "hotel": "Hotel",
    "codigo": "Allocation (código)",
    "descripcion": "Descripción exacta en Tourplan",
    "habitacion": "Habitación linkeada (código)",
    "desc_habitacion": "Descripción de la habitación",
    "cierra_tarifa": "Cierra tarifa",
    "tarifas": "Tarifas a cerrar",
    "vigente_hasta": "Vigente hasta",
    "notas": "Notas",
}
# Sin estas no se puede trabajar; el resto (descripción de la habitación, notas) es informativo.
OBLIGATORIAS = ("codigo_hotel", "hotel", "codigo", "descripcion", "habitacion",
                "cierra_tarifa", "tarifas", "vigente_hasta")


def normalizar(txt):
    """Minúsculas, sin tildes y con espacios colapsados (para comparar textos)."""
    s = unicodedata.normalize("NFD", str(txt or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.casefold().split())


class RegistroInvalido(ValueError):
    pass


@dataclass
class AllocationReg:
    codigo_hotel: str
    hotel: str
    codigo: str
    descripcion: str
    habitacion: str            # código largo; "" = allocation vacía; puede ser "Multiple Options"
    desc_habitacion: str
    cierra_tarifa: bool
    tarifas: str               # LINKEADA | TODAS | códigos largos separados por coma
    vigente_hasta: object      # date | None
    vigente_hasta_txt: str
    notas: str
    fila: int

    @property
    def vacia(self):
        return not self.habitacion.strip()

    @property
    def id(self):
        return (self.codigo_hotel, self.codigo)


@dataclass
class Hotel:
    codigo: str                # "" si el registro no tiene código de hotel
    nombre: str
    allocations: list = field(default_factory=list)

    @property
    def procesable(self):
        return bool(self.codigo)

    @property
    def cierra_tarifa(self):
        return any(a.cierra_tarifa for a in self.allocations)


def _mapear_columnas(columnas):
    por_norm = {normalizar(c): c for c in columnas}
    mapa, faltan = {}, []
    for clave, esperado in ENCABEZADOS.items():
        real = por_norm.get(normalizar(esperado))
        if real is None:
            if clave in OBLIGATORIAS:
                faltan.append(esperado)
        else:
            mapa[clave] = real
    if faltan:
        raise RegistroInvalido(
            f"Faltan columnas en la hoja {HOJA_ALLOCATIONS}: {faltan}. "
            f"Columnas detectadas: {[c for c in columnas if c]}")
    return mapa


def construir_allocations(filas, columnas):
    """filas/columnas como las devuelve sheets_client.cargar_sheet()."""
    mapa = _mapear_columnas(columnas)

    def val(fila, clave):
        col = mapa.get(clave)
        return str(fila.get(col, "") if col else "").strip()

    allocs = []
    for fila in filas:
        a = AllocationReg(
            codigo_hotel=val(fila, "codigo_hotel"),
            hotel=val(fila, "hotel"),
            codigo=val(fila, "codigo"),
            descripcion=val(fila, "descripcion"),
            habitacion=val(fila, "habitacion"),
            desc_habitacion=val(fila, "desc_habitacion"),
            cierra_tarifa=normalizar(val(fila, "cierra_tarifa")) in ("si", "s"),
            tarifas=val(fila, "tarifas"),
            vigente_hasta=parsear_fecha_registro(val(fila, "vigente_hasta")),
            vigente_hasta_txt=val(fila, "vigente_hasta"),
            notas=val(fila, "notas"),
            fila=fila.get("__row_idx__", 0),
        )
        if a.codigo or a.hotel or a.codigo_hotel:
            allocs.append(a)
    return allocs


def agrupar_hoteles(allocs):
    """Agrupa por código de hotel; las filas sin código se agrupan por nombre."""
    hoteles = {}
    for a in allocs:
        clave = a.codigo_hotel.upper() if a.codigo_hotel else "~" + normalizar(a.hotel)
        h = hoteles.get(clave)
        if h is None:
            h = hoteles[clave] = Hotel(codigo=a.codigo_hotel, nombre=a.hotel)
        if not h.nombre and a.hotel:
            h.nombre = a.hotel
        h.allocations.append(a)
    return sorted(hoteles.values(), key=lambda h: normalizar(h.nombre))


def duplicados(allocs):
    """Pares (Código hotel, Allocation (código)) repetidos en el registro."""
    vistos, dups = set(), set()
    for a in allocs:
        k = (a.codigo_hotel.upper(), normalizar(a.codigo))
        if k in vistos:
            dups.add(a.id)
        vistos.add(k)
    return sorted(dups)


def buscar(hoteles, consulta):
    """Hoteles cuyo nombre o código contienen la consulta (todas las palabras)."""
    palabras = normalizar(consulta).split()
    if not palabras:
        return []
    res = []
    for h in hoteles:
        texto = normalizar(f"{h.codigo} {h.nombre}")
        if all(p in texto for p in palabras):
            res.append(h)
    return res


def cargar_registro(ws):
    """Lee la hoja ALLOCATIONS ya conectada (ws) -> (allocations, hoteles)."""
    from common.sheets_client import cargar_sheet
    filas, columnas = cargar_sheet(ws)
    if not columnas:
        raise RegistroInvalido(f"La hoja {HOJA_ALLOCATIONS} está vacía.")
    allocs = construir_allocations(filas, columnas)
    return allocs, agrupar_hoteles(allocs)
