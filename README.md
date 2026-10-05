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
| 2 | Selenium en modo lectura contra Tourplan de prueba | pendiente |
| 3 | Aplicar allocations (prueba) | pendiente |
| 4–5 | Rates en lectura / aplicar (prueba) | pendiente |
| 6 | Cola completa (tomar pedidos, EN CURSO, "Enviar y ejecutar") | pendiente |
| 7 | Endurecimiento | pendiente |

En la etapa 1 los botones «Enviar y ejecutar» y «Ejecutar pendientes» están
deshabilitados a propósito. **Nada se escribe en Tourplan.**

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
common/
  sheets_client.py      Copia sin cambios de Drive-TP-NX-App (OAuth + gspread)
  user_config.py        Config por PC (adaptada a esta app)
tests/                  Pruebas unitarias de la lógica pura y de la escritura en COLA
```

## Reglas de fechas

- Las fechas pasadas se descartan; **hoy cuenta como vigente**; se rechazan fechas a más de 2 años.
- Atajos: `20-23/10, 5/11, 18-19/11`, `28/10-2/11`, `5/11/26`, `2026-11-05`. Sin año: el actual,
  o el siguiente si el mes ya pasó (en octubre, `5/1` es enero próximo).
- Texto normalizado de la cola: `2026-10-08; 2026-10-20..2026-10-23`.

## Pruebas

```bash
pip install -r requirements.txt && python -m pytest
```
