# Cierre de allotment y tarifas convenio — Tourplan NX

App local (Streamlit) que corre en la PC de cada persona. Una persona recibe por
mail las fechas que un hotel cierra, las carga acá y quedan en una **cola** (hoja
`COLA` de un Google Sheet). Más adelante un script con Selenium tomará cada pedido
y cerrará las fechas en la allocation y, si corresponde, las tarifas convenio en
Tourplan NX. Especificación completa: `PROMPT_Claude_Code_Cierre_Allotment.md`.

Sigue el mismo patrón que `Drive-TP-NX-App` (Streamlit + subproceso por variables
de entorno + config por PC + OAuth de Google con gspread).

## Estado por etapas

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | Lectura del Sheet, pantallas, escritura de pedidos en COLA | **hecha** |
| 2 | Lectura de allocations en Tourplan (modo lectura) | **hecha, probada en Test** |
| 3 | Aplicar allocations (Max/Release, Save, verificación, idempotencia) | **hecha, probada en Test** |
| 4 | Rates en lectura (grilla de períodos, cortes y ediciones calculados) | **hecha, probada en Test** |
| 5 | Rates en aplicar (split, tarifa en 0, status, Save) | **hecha, probada en Test** |
| 6 | Cola completa (toma de pedidos, EN CURSO, «Enviar y ejecutar», «Ejecutar pendientes») | **hecha, probada en Test** |
| 7 | Endurecimiento (errores, logs, reintentos) | pendiente |

Cómo se ejecuta: «Enviar a la cola» solo escribe el pedido. «Enviar y ejecutar» (ese pedido) y
«Ejecutar pendientes» (todos) lanzan `runner.py`. Desde la interfaz **todos los pedidos nuevos se cargan en
modo aplicar** (la pantalla «Revisar y enviar» ya no tiene selector de modo ni casilla de revisión: solo
Volver, Enviar a la cola y Enviar y ejecutar). El runner sigue usando el **MODO de cada fila de la cola**, así que
una fila cargada a mano con `MODO = lectura` se sigue tratando como lectura:

- **lectura**: no escribe nada en Tourplan, no toma el pedido ni cambia estados; deja el plan en
  `OBSERVACIONES_CIERRE_ALLOTMENT` y `OBSERVACIONES_CIERRE_TARIFA`.
- **aplicar**: toma el pedido (`EN CURSO` / `TOMADO_POR` / `TOMADO_EN`, con relectura para varias PCs),
  cierra las fechas en la allocation y después las tarifas, y deja `OK` / `SALTEADO` / `NO APLICA` / `ERROR: detalle`
  por fase. Es resumible (solo corre fases PENDIENTE) e idempotente. Un error no frena el lote.

**Reglas de tarifas (actualizan la especificación original):**
- Status objetivo: Manual para TR, ND y EM; Closed para el resto.
- Confirmed y **Provisional** pasan al objetivo. **Terminal** también pasa al objetivo (TR, ND y EM a Manual; el resto a Closed).
- Closed se saltea y **nunca** pasa a Manual. Manual pasa a Closed salvo en TR, ND y EM.
- **Rate sets:** si un período tiene varios (el status viene como «Confirmed, Confirmed»), cada rate set se procesa igual y por separado: tarifa en 0 y status con las mismas reglas, avanzando con la flecha derecha del selector, y se guarda una sola vez.
- Al price code **FX nunca se le cambia la tarifa ni el status**. Su período sí puede cortarse (split):
  si comparte el período con otros price codes, el corte con «Split All Applicable Price Codes» lo corta también.
- Se sigue frenando el pedido si el status de la grilla es ambiguo. El **Rate Name no influye**: no frena ni decide si se cierra.

**Producción:** el modo aplicar se niega a escribir en Producción salvo que, en la Configuración, el
entorno sea Producción **y** esté tildada la autorización explícita. Por defecto está destildada.

## Cómo correrla

Windows: doble clic en `run_app.bat` (crea el entorno la primera vez, instala
dependencias y abre la app). Requiere Python. Manual:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py --server.address=localhost
```

`actualizar_app.bat` hace `git pull` (requiere que la carpeta sea un clon de git).

## Primera vez en cada PC (Configuración: clic en tu nombre, arriba a la derecha)

La configuración vive en `~/.tourplan-allocation/` (fuera del repo, nunca se sube):

- **Nombre**: aparece en «Cargado por» / «Tomado por».
- **URL del Google Sheet**: viene precargada con el registro actual.
- **Entorno**: `test` por defecto (`https://tourplannx.eurotur.com.ar/TourplanNX_Test`).
  Producción (`.../tourplannx`) es una elección deliberada.
- **Usuario / password de Tourplan** (texto plano, solo en esta PC).
- **credentials.json** (cliente OAuth de Google): copialo a
  `~/.tourplan-allocation/credentials.json`. Si ya lo tenés en
  `~/.tourplan-nx-app/` (Drive-TP-NX-App) se reutiliza ese. La primera vez que se
  lee el Sheet se abre el navegador para elegir cuenta; el token queda en
  `~/.tourplan-allocation/token.json`.

## El Google Sheet

Pestañas `ALLOCATIONS` (solo lectura para la app), `COLA` (la app escribe) e
`HISTORIAL`. **Las columnas se ubican por el nombre del encabezado**, no por la
letra; si falta una columna obligatoria la app lo informa y no modifica el Sheet.
La columna `Hotel` de COLA es una fórmula del Sheet: la app nunca la escribe.

**«Tarifas a cerrar»** (hoja ALLOCATIONS) admite:

| Valor | Qué cierra en Rates |
|---|---|
| `LINKEADA` | solo la habitación linkeada a la allocation |
| `TODAS` | todas las habitaciones HT del hotel, excepto `600HTL` y `ROOMS` (se lee de Tourplan) |
| `OTRO` | las habitaciones que figuren en la columna **«Habitaciones a cerrar»** |
| `REVISAR` | falta definir: el pedido no se puede enviar ni ejecutar |

**«Habitaciones a cerrar»** (columna opcional, la ubicás donde quieras, por ejemplo entre «Tarifas a cerrar» y
«Vigente hasta») solo se completa con `OTRO`: códigos largos (`location + HT + código de hotel + opción`, ej.
`IGRHT1MERC1ST`) separados por coma. Si querés cerrar la linkeada **y** otra, escribí las dos. «Habitación
linkeada (código)» lleva siempre una sola (la que Tourplan tiene linkeada) y no decide qué tarifas se cierran.
Con `OTRO` y la columna vacía el pedido se frena. Siguen valiendo las protecciones: solo service type `HT`, nunca
`600HTL` ni `ROOMS`, y la habitación tiene que existir en el Product Find del hotel.

## Estructura

```
app.py                  Interfaz Streamlit: barra superior (Nuevo pedido / Cola / usuario), flujo de 3 pasos
                        (Hotel / Fechas y alcance / Revisar y enviar) y Cola; Configuración en un diálogo
.streamlit/config.toml  Tema (colores y tipografía) de la interfaz
components/calendario/  Calendario de varios meses (clic y shift+clic) como componente Streamlit
allocation/
  constantes.py         Reglas de negocio y constantes en un solo lugar
  fechas.py             Atajos de texto, rangos, ventana de 2 años, texto normalizado de la cola
  registro.py           Lee ALLOCATIONS, agrupa por hotel, busca
  cola.py               Arma y escribe pedidos en COLA, lee y clasifica estados
  plan.py               Decisión por fecha (Used/Max/Release), con barrera «nunca reabrir»
  rates_plan.py         Decisión de tarifas: price codes, status, cortes y ediciones (sin Selenium)
tourplan_flujos/
  allocations.py        Selenium: supplier, menú, filtro, allocation, días; escritura solo en modo aplicar
  rates.py              Selenium: habitación (Product Find), grilla de períodos, cortes, edición
runner.py               Proceso hijo: ejecuta los pedidos de la cola según el MODO de cada fila
common/
  tourplan.py           Helpers Selenium (copiados de la referencia): login/logout, esperas, set_val
  abort.py, chrome_bootstrap.py   Copias sin cambios de Drive-TP-NX-App
  sheets_client.py      Copia sin cambios de Drive-TP-NX-App (OAuth + gspread)
  user_config.py        Config por PC (adaptada a esta app)
tests/                  Pruebas unitarias de la lógica pura y de la escritura en COLA
```

## Reglas de fechas

- Las fechas pasadas se descartan; **hoy cuenta como vigente**; se rechazan fechas a más de 2 años.
- Atajos: `20-23/10, 5/11, 18-19/11`, `28/10-2/11`, `5/11/26`, `2026-11-05`. Sin año: el actual,
  o el siguiente si el mes ya pasó (en octubre, `5/1` es enero próximo).
- Texto normalizado de la cola: `2026-10-08; 2026-10-20..2026-10-23`.

## Cómo probar el proceso completo en Tourplan de prueba

Hacelo en este orden, siempre en el entorno `test` y con una fecha de prueba que no importe:

1. **Lectura** de un hotel con allocation y tarifa (ej. `6RABA1`): mirá `OBSERVACIONES_*` de la cola.
2. **Aplicar solo allocation**: un hotel que no cierre tarifa (ej. `1EDE01`) con una fecha. Verificá en
   Tourplan Max/Release. Volvé a ejecutar el mismo pedido: debe quedar todo `SALTEADO`.
3. **Aplicar con tarifa**: `6RABA1` (LINKEADA). Probá un rango que obligue a 0, 1 y 2 cortes.
4. **Allocation vacía** (ej. Novotel con código cargado) y **`TODAS`** (se excluyen `600HTL` y `ROOMS`).
5. **Dos PCs** con la misma cola: nadie debe procesar el mismo pedido dos veces.

Puntos del flujo que solo se pueden confirmar en Tourplan (si algo falla, el log dice en qué paso;
mandame el HTML o el log):
- Después de «OK» en Split Date, ¿el diálogo del período queda abierto? La app guarda si Save está
  habilitado y si no sale con Exit.
- Estructura de los radios del status (pestaña Rate Set) y botón Save/Exit de los diálogos.
- Selectores del modal Product Find y del menú Rates.

## Pruebas

```bash
pip install -r requirements.txt && python -m pytest
```

`tests/test_flujo_allocations_dom.py` prueba el JS del flujo contra un DOM simulado de
Tourplan (diálogo, habitaciones y grilla de días virtual); necesita `playwright` y la
variable `CHROME_BIN` con la ruta de un Chrome/Chromium, y si no se saltea.
