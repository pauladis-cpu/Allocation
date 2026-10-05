from datetime import date

from allocation import fechas as f

HOY = date(2026, 10, 5)


def test_atajos_basicos():
    r = f.interpretar("20-23/10, 5/11, 18-19/11", HOY)
    assert r.fechas == [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23),
                        date(2026, 11, 5), date(2026, 11, 18), date(2026, 11, 19)]
    assert not r.errores


def test_hoy_cuenta_y_pasadas_se_descartan():
    r = f.interpretar("4/10, 5/10, 6/10", HOY)
    assert r.fechas == [date(2026, 10, 5), date(2026, 10, 6)]
    assert r.descartadas_pasadas == [date(2026, 10, 4)]


def test_mes_anterior_sin_anio_es_anio_siguiente():
    assert f.interpretar("5/1", HOY).fechas == [date(2027, 1, 5)]


def test_mas_de_dos_anios_se_rechaza():
    r = f.interpretar("5/10/2028, 6/10/2028", HOY)
    assert r.fechas == [date(2028, 10, 5)]
    assert r.rechazadas_lejanas == [date(2028, 10, 6)]


def test_formatos_con_anio_e_iso_y_rangos():
    r = f.interpretar("5/11/26; 2026-11-06; 2026-11-08..2026-11-09; 28/10-2/11", HOY)
    assert date(2026, 11, 5) in r.fechas and date(2026, 11, 6) in r.fechas
    assert date(2026, 11, 8) in r.fechas and date(2026, 11, 9) in r.fechas
    assert date(2026, 10, 28) in r.fechas and date(2026, 11, 2) in r.fechas
    assert len([x for x in r.fechas if date(2026, 10, 28) <= x <= date(2026, 11, 2)]) >= 6


def test_errores_se_informan():
    r = f.interpretar("32/10, hola, 31/2, 20-10/10", HOY)
    assert r.fechas == [] and len(r.errores) == 4


def test_texto_normalizado_y_vuelta():
    fechas = [date(2026, 10, 8), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    txt = f.a_texto_normalizado(fechas)
    assert txt == "2026-10-08; 2026-10-20..2026-10-23"
    assert f.de_texto_normalizado(txt) == fechas


def test_atajos_ida_y_vuelta():
    fechas = f.interpretar("20-23/10, 5/11, 28/12-3/1, 10/2/2028", HOY).fechas
    assert f.interpretar(f.a_atajos(fechas, HOY), HOY).fechas == fechas


def test_agrupar_rangos():
    assert f.agrupar_rangos([date(2026, 10, 9), date(2026, 10, 7), date(2026, 10, 8), date(2026, 10, 20)]) == [
        (date(2026, 10, 7), date(2026, 10, 9)), (date(2026, 10, 20), date(2026, 10, 20))]


def test_clasificar():
    vig, pas, lej = f.clasificar([date(2026, 10, 4), date(2026, 10, 5), date(2029, 1, 1)], HOY)
    assert vig == [date(2026, 10, 5)] and pas == [date(2026, 10, 4)] and lej == [date(2029, 1, 1)]


def test_fecha_registro():
    assert f.parsear_fecha_registro("2027-03-31") == date(2027, 3, 31)
    assert f.parsear_fecha_registro("31/03/2027") == date(2027, 3, 31)
    assert f.parsear_fecha_registro("31/Mar/2027") == date(2027, 3, 31)
    assert f.parsear_fecha_registro("") is None and f.parsear_fecha_registro("n/a") is None
