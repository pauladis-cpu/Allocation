"""Fechas de un pedido: atajos de texto, rangos, validación y texto normalizado.

Reglas (spec sección 3):
  - Las fechas pasadas se descartan; HOY cuenta como vigente.
  - Se rechazan fechas a más de WINDOW_YEARS años de hoy.
  - Texto normalizado para la cola: fechas ISO separadas por ";" y rangos con
    "..", ej. "2026-10-08; 2026-10-20..2026-10-23".

Atajos aceptados (separados por coma, punto y coma o salto de línea):
    5/11            20-23/10          28/10-2/11
    5/11/26         5/11/2026         2026-11-05
    2026-10-20..2026-10-23
Si se omite el año se usa el de hoy; si el mes ya pasó este año se entiende
el año siguiente (ej. en octubre "5/1" es enero próximo). Una fecha del mes en
curso con día anterior a hoy se toma como pasada y se descarta (no salta de año).
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from allocation.constantes import WINDOW_YEARS

MESES_EN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

_D = r"(\d{1,2})"
_M = r"(\d{1,2})"
_Y = r"(\d{2}|\d{4})"
_RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RE_ISO_RANGO = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*\.\.\s*(\d{4}-\d{2}-\d{2})$")
_RE_MISMO_MES = re.compile(rf"^{_D}\s*-\s*{_D}\s*/\s*{_M}(?:\s*/\s*{_Y})?$")
_RE_FECHA = re.compile(rf"^{_D}\s*/\s*{_M}(?:\s*/\s*{_Y})?$")


class FechaInvalida(ValueError):
    pass


@dataclass
class ResultadoFechas:
    """Resultado de interpretar un texto de atajos."""
    fechas: list = field(default_factory=list)            # vigentes, ordenadas, sin repetir
    descartadas_pasadas: list = field(default_factory=list)
    rechazadas_lejanas: list = field(default_factory=list)
    errores: list = field(default_factory=list)            # tokens que no se entendieron


def limite_futuro(hoy):
    """Última fecha aceptada: hoy + WINDOW_YEARS años."""
    try:
        return hoy.replace(year=hoy.year + WINDOW_YEARS)
    except ValueError:  # hoy = 29/feb
        return hoy.replace(year=hoy.year + WINDOW_YEARS, day=28)


def _anio_completo(y):
    y = int(y)
    return 2000 + y if y < 100 else y


def _armar(dia, mes, anio, hoy, token):
    """Arma una fecha; si no hay año, aplica la regla de año implícito."""
    dia, mes = int(dia), int(mes)
    try:
        if anio is not None:
            return date(_anio_completo(anio), mes, dia)
        f = date(hoy.year, mes, dia)
        if mes < hoy.month:
            f = date(hoy.year + 1, mes, dia)
        return f
    except ValueError:
        raise FechaInvalida(token)


def _rango(a, b, token):
    if b < a:
        raise FechaInvalida(token)
    n = (b - a).days
    if n > 366 * WINDOW_YEARS + 5:
        raise FechaInvalida(token)
    return [a + timedelta(days=i) for i in range(n + 1)]


def _parse_token(token, hoy):
    """Un token -> lista de fechas. Levanta FechaInvalida si no se entiende."""
    t = token.strip()
    m = _RE_ISO_RANGO.match(t)
    if m:
        return _rango(date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)), token)
    m = _RE_ISO.match(t)
    if m:
        try:
            return [date(int(m.group(1)), int(m.group(2)), int(m.group(3)))]
        except ValueError:
            raise FechaInvalida(token)
    m = _RE_MISMO_MES.match(t)
    if m:
        d1, d2, mes, anio = m.groups()
        return _rango(_armar(d1, mes, anio, hoy, token), _armar(d2, mes, anio, hoy, token), token)
    m = _RE_FECHA.match(t)
    if m:
        return [_armar(*m.groups(), hoy, token)]
    # "d/m-d/m[/y]" (rango entre meses)
    if "-" in t:
        izq, _, der = t.partition("-")
        mi, md = _RE_FECHA.match(izq.strip()), _RE_FECHA.match(der.strip())
        if mi and md:
            a = _armar(*mi.groups(), hoy, token)
            b = _armar(*md.groups(), hoy, token)
            # "28/10-2/11" sin año en la derecha: si queda antes que la izquierda, es año siguiente
            if md.group(3) is None and b < a:
                b = _armar(md.group(1), md.group(2), a.year + 1, hoy, token)
            return _rango(a, b, token)
    raise FechaInvalida(token)


def interpretar(texto, hoy=None):
    """Interpreta un texto de atajos y separa vigentes / pasadas / lejanas / errores."""
    hoy = hoy or date.today()
    res = ResultadoFechas()
    tope = limite_futuro(hoy)
    vistas = set()
    pasadas, lejanas = set(), set()
    for token in re.split(r"[,;\n]+", texto or ""):
        if not token.strip():
            continue
        try:
            fechas = _parse_token(token, hoy)
        except FechaInvalida:
            res.errores.append(token.strip())
            continue
        for f in fechas:
            if f < hoy:
                pasadas.add(f)
            elif f > tope:
                lejanas.add(f)
            else:
                vistas.add(f)
    res.fechas = sorted(vistas)
    res.descartadas_pasadas = sorted(pasadas)
    res.rechazadas_lejanas = sorted(lejanas)
    return res


def clasificar(fechas, hoy=None):
    """Para fechas ya armadas (ej. del calendario): (vigentes, pasadas, lejanas)."""
    hoy = hoy or date.today()
    tope = limite_futuro(hoy)
    vig = sorted({f for f in fechas if hoy <= f <= tope})
    pas = sorted({f for f in fechas if f < hoy})
    lej = sorted({f for f in fechas if f > tope})
    return vig, pas, lej


def agrupar_rangos(fechas):
    """Fechas -> rangos consecutivos [(a, b), ...]; un día suelto es (a, a)."""
    rangos = []
    for f in sorted(set(fechas)):
        if rangos and f - rangos[-1][1] == timedelta(days=1):
            rangos[-1] = (rangos[-1][0], f)
        else:
            rangos.append((f, f))
    return rangos


def a_texto_normalizado(fechas):
    """Texto de la columna "Fechas a cerrar" de la cola."""
    partes = []
    for a, b in agrupar_rangos(fechas):
        partes.append(a.isoformat() if a == b else f"{a.isoformat()}..{b.isoformat()}")
    return "; ".join(partes)


def de_texto_normalizado(texto):
    """Inversa de a_texto_normalizado (la usa el runner). No aplica filtros de ventana."""
    fechas = []
    for token in re.split(r"[;\n]+", texto or ""):
        t = token.strip()
        if not t:
            continue
        m = _RE_ISO_RANGO.match(t)
        if m:
            fechas += _rango(date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2)), token)
        elif _RE_ISO.match(t):
            fechas.append(date.fromisoformat(t))
        else:
            raise FechaInvalida(token)
    return sorted(set(fechas))


def _corto(f, hoy, con_anio=False):
    s = f"{f.day}/{f.month}"
    return f"{s}/{f.year}" if con_anio else s


def a_atajos(fechas, hoy=None):
    """Fechas -> texto de atajos legible (ej. "20-23/10, 5/11"). El año solo se
    muestra cuando no se podría recuperar al volver a interpretar el texto."""
    hoy = hoy or date.today()

    def fmt(f):
        corto = _corto(f, hoy)
        try:
            if _parse_token(corto, hoy) == [f]:
                return corto
        except FechaInvalida:
            pass
        return _corto(f, hoy, con_anio=True)

    partes = []
    for a, b in agrupar_rangos(fechas):
        if a == b:
            partes.append(fmt(a))
        elif (a.year, a.month) == (b.year, b.month) and fmt(a).count("/") == 1:
            partes.append(f"{a.day}-{fmt(b)}")
        else:
            partes.append(f"{fmt(a)}-{fmt(b)}")
    return ", ".join(partes)


def parsear_fecha_registro(txt):
    """Fecha de una celda del Sheet (ej. "Vigente hasta"). Acepta ISO,
    dd/mm/yyyy, dd/mm/yy y dd/Mon/yyyy (mes en inglés). None si no se entiende."""
    s = (txt or "").strip()
    if not s:
        return None
    s = s.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2}\s", s) else s
    m = _RE_ISO.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})\s*[/-]\s*([A-Za-z]{3})[A-Za-z]*\s*[/-]\s*(\d{2}|\d{4})$", s)
    if m:
        mes = MESES_EN.get(m.group(2).lower())
        if mes:
            try:
                return date(_anio_completo(m.group(3)), mes, int(m.group(1)))
            except ValueError:
                return None
    m = re.match(rf"^{_D}\s*/\s*{_M}\s*/\s*{_Y}$", s)
    if m:
        try:
            return date(_anio_completo(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None
