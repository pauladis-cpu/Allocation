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
| 1 | Lectura del Sheet, pantallas 1 a 3, escritura de pedidos en COLA (sin Selenium) | **hecha** |
| 2 | Selenium en modo lectura contra Tourplan de prueba (allocations) | **hecha, sin probar en Tourplan real** |
| 3 | Aplicar allocations (prueba) | pendiente |
| 4–5 | Rates en lectura / aplicar (prueba) | pendiente |
| 6 | Cola completa (tomar pedidos, EN CURSO, "Enviar y ejecutar") | pendiente |
| 7 | Endurecimiento | pendiente |

«Enviar y ejecutar» y «Ejecutar pendientes» siguen deshabilitados hasta la etapa 6.
**Nada se escribe en Tourplan.** En la pantalla Cola, «Leer plan (lectura)» abre
Tourplan, lee las allocations de los pedidos PENDIENTE y deja el plan en
`OBSERVACIONES_CIERRE_ALLOTMENT` (no cambia ESTADO ni toma el pedido). El módulo
de Selenium de esta etapa no tiene ninguna función que escriba Max/Release ni Save.
Los selectores salen de la especificación y de las grabaciones: hay que validarlos
contra el Tourplan de prueba (ver «Etapa 2: cómo probar»).

## Cómo correrla

Windows: doble clic en `run_app.bat` (crea el entorno la primera vez, instala
dependencias y abre la app). Requiere Python. Manual:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py --server.address=localhost
```

`actualizar_app.bat` hace `git pull` (requiere que la carpeta sea un clon de git).

## Primera vez en cada PC (⚙️ Configuración)

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

## Estructura

```
app.py                  Interfaz Streamlit: Buscar hotel / Fechas y alcance / Revisar y enviar / Cola / Configuración
components/calendario/  Calendario de varios meses (clic y shift+clic) como componente Streamlit
allocation/
  constantes.py         Reglas de negocio y constantes en un solo lugar
  fechas.py             Atajos de texto, rangos, ventana de 2 años, texto normalizado de la cola
  registro.py           Lee ALLOCATIONS, agrupa por hotel, busca
  cola.py               Arma y escribe pedidos en COLA, lee y clasifica estados
  plan.py               Decisión por fecha (Used/Max/Release), con barrera «nunca reabrir»
tourplan_flujos/
  allocations.py        Selenium (solo lectura): supplier, menú, filtro, allocation, días
runner.py               Proceso hijo que lee los pedidos PENDIENTE en Tourplan (modo lectura)
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

## Etapa 2: cómo probar contra Tourplan de prueba

1. En ⚙️ Configuración: usuario/password de Test, entorno `test`, tu nombre.
2. Cargá en Test un hotel del registro (ej. `6RABA1` con su allocation `Standard` /
   `Standard CIERRA DATABASE` y la habitación `BUEHT6RABA1ST`).
3. Enviá un pedido en modo lectura a la cola y, en la pestaña Cola, «Leer plan (lectura)».
4. Mirá el log y `OBSERVACIONES_CIERRE_ALLOTMENT`. Si algún selector no coincide, el log
   dice en qué paso se frenó y se guarda una captura en la carpeta temporal de la corrida.

## Pruebas

```bash
pip install -r requirements.txt && python -m pytest
```

`tests/test_flujo_allocations_dom.py` prueba el JS del flujo contra un DOM simulado de
Tourplan (diálogo, habitaciones y grilla de días virtual); necesita `playwright` y la
variable `CHROME_BIN` con la ruta de un Chrome/Chromium, y si no se saltea.
