# Proyecto: app de cierre de allotment y tarifas convenio en Tourplan NX

Construí una app nueva que automatiza el cierre de fechas en Tourplan NX a partir de pedidos que carga una persona. Este documento es la especificación completa. Está pensado para que no necesites nada más que el repositorio de referencia, el Google Sheet y acceso a Tourplan de prueba.

---

## 0. Cómo trabajar

1. **Primero leé el repositorio de referencia** (`Drive-TP-NX-App`, te paso la ruta local). Quiero que esta app replique cómo ese proyecto: se vincula con Google Sheets/Drive y se autentica, cómo sirve la interfaz, cómo inicia Selenium y Chrome, cómo hace login/logout en Tourplan, y qué helpers ya existen (esperas, escritura en campos Angular, manejo de dialogs). **No modifiques el repositorio de referencia.** La app nueva va en **otro repositorio** y corre **en la PC de cada persona**.
2. **Etapa 0, antes de escribir código:** resumime cómo funciona el repositorio de referencia, proponé la estructura del repositorio nuevo y esperá mi OK.
3. **No refactorices ni reescribas lo que ya funciona.** Si en el camino encontrás código muerto, duplicado o bugs secundarios, frená y preguntame en ese momento, explicando qué encontraste y dónde. Antes de cambiar algo fuera del foco de la tarea, preguntame y explicá por qué es necesario.
4. **Probá siempre primero en el Tourplan de prueba y en modo lectura.** Nada se escribe en Producción hasta que yo lo confirme. Tourplan no permite deshacer fácilmente: el script **nunca reabre** una fecha.
5. Al terminar cada etapa, dame un resumen breve de qué archivos creaste o modificaste y qué hace cada uno.

---

## 1. Qué hace la app

Una persona recibe por mail las fechas que un hotel cierra. Las carga en la app, que las deja en una **cola** (hoja de un Google Sheet). Un script con Selenium toma cada pedido y, en Tourplan NX:

1. **Cierra las fechas en la allocation** (Max / Release por día).
2. Si el hotel cierra tarifa convenio, **cierra las tarifas** de las habitaciones que corresponden (períodos en Rates con status Manual o Closed y tarifa en 0).

La app **no lee mails**. La persona ya sabe qué habitación aplica y carga las fechas.

Se puede **enviar el pedido a la cola** (para acumular varios) o **enviar y ejecutar** en el momento. Pueden ejecutar varias personas a la vez, cada una desde su PC.

---

## 2. El Google Sheet

Se importa desde `Registro_de_Allocation_v3.xlsx`. Pestañas: `LEEME`, `ALLOCATIONS`, `COLA`, `HISTORIAL`. **Ubicá las columnas por el nombre del encabezado, no por la letra.**

### ALLOCATIONS (solo lectura para la app; una fila por allocation)

| Columna | Contenido |
|---|---|
| Código hotel | Código de supplier en Tourplan (ej. `6RABA1`). Si está vacío, la fila no se puede procesar. |
| Hotel | Nombre. |
| Allocation (código) | Columna Name de la grilla de Allocations (ej. `ST`, `1EDE01 CL`, `SIN FS-CIERRA D`). |
| Descripción exacta en Tourplan | Columna Description de esa grilla. |
| Habitación linkeada (código) | **Código largo**: location + service type + código de hotel + option, ej. `BRCHT1EDE01ST`. Vacía = allocation vacía. |
| Descripción de la habitación | Informativa. |
| Cierra tarifa | `SI` / `NO`. |
| Tarifas a cerrar | `LINKEADA`, `TODAS`, o códigos largos separados por coma. |
| Vigente hasta | Fecha hasta la que la allocation está cargada. Se muestra en la app. |
| Notas | Informativa. |

La identidad de una allocation es el par **(Código hotel, Allocation (código))**. El código de allocation se repite entre hoteles.

**Significado de "Tarifas a cerrar":**
- `LINKEADA`: solo la habitación linkeada a la allocation.
- `TODAS`: todas las opciones del hotel con service type `HT`, **excepto** las de código `600HTL` y `ROOMS`. La lista se arma leyendo Tourplan (ver sección 6), no sale del Sheet.
- Lista de códigos largos: solo esas habitaciones. Sirve cuando una tarifa se cierra en habitaciones que no están linkeadas a la allocation.

**Allocation vacía:** hay hoteles con una allocation sin días ni habitaciones (ej. `SIN FS-CIERRA D` / `CERRAR DATABASE`), creada solo para avisar que se cierra tarifa. En el registro tienen "Habitación linkeada" vacía. No hay nada que procesar en allocation; solo se trabajan las tarifas.

### COLA (la app escribe; el script actualiza)

| Columna | Contenido |
|---|---|
| ID_PEDIDO | Identificador del pedido. |
| Fecha de carga, Cargado por | Automáticos al crear el pedido. |
| Hotel (código) | Código de supplier. |
| Hotel | **Fórmula del Sheet. No la sobrescribas.** |
| Allocation(es) (código o TODAS) | Códigos separados por `;`, o `TODAS` (todas las allocations del hotel en el registro). |
| Fechas a cerrar | Texto normalizado: fechas `2026-10-08` separadas por `;` y rangos con `..` (ej. `2026-10-08; 2026-10-20..2026-10-23`). |
| Cant. de fechas | Cantidad de días. |
| Origen | Asunto o remitente del mail, opcional. |
| MODO | `lectura` o `aplicar`. |
| ESTADO_CIERRE_ALLOTMENT / OBSERVACIONES_CIERRE_ALLOTMENT | Resultado de la fase de allocation. |
| ESTADO_CIERRE_TARIFA / OBSERVACIONES_CIERRE_TARIFA | Resultado de la fase de tarifas. |
| TOMADO_POR, TOMADO_EN | Quién ejecuta el pedido y desde cuándo. |

**Estados:** `PENDIENTE` → `EN CURSO` → `OK` / `SALTEADO` / `ERROR: detalle`. Un pedido es un hotel. Cada fase (allocation, tarifa) tiene su estado, para poder retomar si una falla.

---

## 3. La interfaz

Seguí el estilo y la tecnología del repositorio de referencia. El esquema de pantallas (wireframe) es este:

1. **Buscar hotel.** Búsqueda por nombre o código sobre la hoja ALLOCATIONS. Muestra la ficha del hotel con sus allocations: descripción, habitación linkeada, si cierra tarifa y "Vigente hasta". Si el hotel no figura, dice que se entiende que no tiene allocation y sugiere verificar en Tourplan. No consulta Tourplan.
2. **Fechas y alcance.**
   - Calendario de varios meses (clic en un día, shift+clic para un rango) y un campo de texto con atajos (`20-23/10, 5/11, 18-19/11`) que se sincronizan entre sí.
   - Selección de allocations: **"Todas"**, una o varias. Cada allocation muestra su **descripción** (suele traer indicaciones para cerrarla), su habitación y su "Vigente hasta". Si se elige "Todas", se carga una sola vez.
   - Las fechas posteriores a "Vigente hasta" se informan: en allocation no se tocan y en tarifas sí se cierran.
3. **Revisar y enviar.** Resumen: hotel, allocations, fechas agrupadas en rangos, qué va a hacer el script. Selector de modo (por defecto `lectura`). Casilla "Revisé las fechas contra el mail". Dos botones: **Enviar a la cola** y **Enviar y ejecutar**.
4. **Cola.** Lee la hoja COLA: estados por fase, observaciones, quién la tiene en curso. Botón **Ejecutar pendientes**.

Reglas de la interfaz: las fechas pasadas se descartan, y **hoy cuenta como vigente**. Se rechazan fechas a más de 2 años de hoy.

---

## 4. Reglas de negocio (fijas, van como constantes en un solo lugar)

```python
PRICE_CODES_MANUAL = {"TR", "ND", "EM"}   # el resto va en Closed
EXCLUDED_OPTIONS   = {"600HTL", "ROOMS"}  # nunca se cierran, ni con TODAS
CLOSEABLE_SERVICE_TYPES = {"HT"}
RELEASE_CLOSED     = 9999
WINDOW_YEARS       = 2                    # filtro de Allocations: hoy + 2 años
```

### Allocation, por fecha
Se lee Used, Max y Release de la fila del día.

| Situación | Acción | ¿Ya cerrada? |
|---|---|---|
| Used = 0 | Max = 0 | Max = 0 |
| Used > 0 | Max = Used y Release = 9999 | Max = Used y Release = 9999 |

- Si una fecha ya está cerrada, se saltea.
- Cada campo se corrige solo si hace falta (puede faltar solo el Release).
- **Si Max es menor que Used y la fecha debe cerrarse, Max se iguala a Used y se pone Release 9999.** Es la única situación en que Max sube.
- **Nunca se reabre una fecha**, ni se sube Max en ninguna otra situación.
- Una fecha del pedido sin fila en la allocation (posterior a lo cargado) no se toca; se informa en OBSERVACIONES.

### Tarifas, por price code
Cada fila de la grilla de períodos de Rates es un par (período, price code).

- **Status objetivo:** `Manual` para TR, ND y EM. `Closed` para cualquier otro price code.
- **Tarifa en 0** en ambos casos: el campo **Group Cost** (la primera columna de costo) de cada fila de la grilla de tarifas que tenga un valor distinto de cero. Tourplan repite ese valor en las demás columnas. Después de escribir, releé las otras columnas de esa fila; si Tourplan no las actualizó, frená y avisá. Nunca escribas en ellas.
- **"Ya cerrado" se decide por el status de la grilla, sin abrir el período:**

| Status actual | TR, ND, EM | Otros price codes |
|---|---|---|
| Closed | se saltea (cerrado) | se saltea (cerrado) |
| Manual | se saltea (cerrado) | se cambia a Closed |
| Confirmed | se cambia a Manual | se cambia a Closed |
| Provisional o Terminal | **frenar y avisar** | **frenar y avisar** |

- **Un período en Closed nunca pasa a Manual.** Dos barreras: la función que elige el status no puede devolver Manual si el actual es Closed, y justo antes del clic se vuelve a leer el radio seleccionado.
- **Un período por rango consecutivo de fechas.** No se hace un período por día. No se fusionan períodos existentes: dos períodos cerrados consecutivos son válidos.
- Si una parte del rango ya cae en períodos cerrados, solo se trabaja lo que falta.

---

## 5. Flujo Selenium: Allocations

Convenciones generales: ver sección 8. Los selectores marcados como estables sirven; **no uses** los atributos `_ngcontent-*`, los `id` con forma de GUID, ni `nth-of-type`.

1. **Login** con `try/finally` y logout garantizado (hay licencias limitadas). Navegá `#/home` y después `#/product`.
2. **Supplier.** Escribí el código de hotel en `#searchSupplier input`. Aparece una lista (`#searchSupplier .tpcombo table tbody tr`) con celdas `td.code` y `td.description`. Hacé clic en la fila cuyo `td.code`, recortado, es **igual** al código. **Nunca uses Enter ni Tab** (aceptan la primera sugerencia), y `tr.selectedRow` solo marca el autocompletado. Verificá que el campo quedó empezando con ese código.
3. **Menú.** Clic en `nav img`, esperá `.nav-menu`, y entrá a "Allocations" **por el texto** del ítem (en las grabaciones era `li:nth-of-type(9) label`, no uses la posición). Esperá a que desaparezca el diálogo "PLEASE WAIT…" y el fondo `.tpnavbackdrop`.
4. **Filtro** (`tp-supplier-allocations tp-group.tpgroup-allocationsfilter`):
   - Si tiene la clase `tpcollapsed`, clic en `.legend i`. Abierto = `tpexpanded`. Es un interruptor.
   - Fecha "hasta": `input.tpdate-dateto` dentro del grupo. Escribí hoy + 2 años en formato `DD/MM/AA`, hacé blur, y verificá en el `input.tphidden` hermano (formato `DD/Mon/YYYY`) que Tourplan entendió la fecha correcta. "Fecha desde" ya viene con hoy y no se toca.
   - "Show Archived" (`#deleted`) queda sin tildar.
   - Clic en `tp-button.filter button` y esperá a que la grilla se actualice.
5. **Elegir la allocation** en `tp-grid[tpid="allocations-grid"] tbody tr`: la fila donde `td.tpcol-name` es igual al código del Sheet **y** `td.tpcol-description` es igual a la descripción del Sheet (recortando y normalizando espacios, sin distinguir mayúsculas). Si no hay ninguna o hay más de una, error. Hacé clic en `td.tpcol-description`.
6. **Verificar el diálogo.** Se abre en `body > tp-dialog` (fuera de la lista; acotá siempre los selectores a su contenedor, porque tiene su propio filtro con las mismas clases). El título (`.tpmodal-allocation h3`) debe decir `Allocation Detail - <código>`.
7. **Verificar la habitación linkeada.** La tabla "Services Included" de la pestaña Setup (`#setup-tab .tpdestination tbody tr`) está en el DOM aunque la pestaña esté oculta. Cada fila tiene Location, Service, Option. Armá `location + service + código de hotel + option` y compará con "Habitación linkeada" del Sheet. **Si el código, la descripción o la habitación no coinciden, no escribas nada.**
8. **Allocation vacía** (habitación linkeada vacía en el Sheet): verificá que la pestaña Days no tenga filas `.tpbodyrow` y que "Services Included" esté vacío. Si es así, Exit, `ESTADO_CIERRE_ALLOTMENT = SALTEADO` ("allocation vacía") y pasá a tarifas. Si no coincide, frená.
9. **Grilla de días** (`#days-tab cdk-virtual-scroll-viewport`, es una grilla virtual):
   - Cada fila es `div.tpbodyrow` con `data-index`. La fecha está en `.datecol.date label` con formato `05/Oct/2026` (meses en inglés abreviado: usá tu propia tabla, no el idioma del sistema). Las filas miden 35 px y son días consecutivos desde "Fecha desde".
   - Para llegar a una fecha, calculá el scroll a partir de la diferencia de días y **verificá siempre leyendo la etiqueta**. Si no está, recorré de a pasos. **Nunca guardes referencias a elementos ni uses `data-index` como verdad.** Releé la fila por su etiqueta antes de cada escritura.
   - Campos: `span.max input` (clase `tpnumber-allocationmax`), `span.release input` (`tpnumber-allocationrelease`), `span.used input` (solo lectura). **Los valores son propiedades `value`, no atributos del HTML.** Release se muestra con separador de miles (`9,999`): limpialo antes de comparar y escribí `9999` sin coma. Max, Used y Release se tratan como enteros.
   - Si hay más de un grupo de columnas (`.splitcol`) distinto de `GENERAL`, o si "Show Release As Date" está tildado, **frená y avisá**.
10. **Guardar.** Si hubo cambios: esperá que `tp-button.save > button` se habilite (arranca deshabilitado), clic, y esperá a que vuelva a deshabilitarse. Releé los campos modificados. **Después, siempre Exit** (`tp-button.cancel > button`): el diálogo **no se cierra solo** en Allocations. Si no hubo cambios, Exit directo. Esperá a que el diálogo desaparezca.

Los dos botones Save y Exit se eligen **dentro del diálogo activo**.

---

## 6. Flujo Selenium: Rates

Solo si "Cierra tarifa" = `SI` en el registro.

### 6.1 Qué habitaciones
- `LINKEADA`: la del paso 7 anterior.
- Lista de códigos: esos.
- `TODAS`: se lee de Product Find (ver 6.2) y se filtra por service type `HT`, excluyendo `EXCLUDED_OPTIONS`. Si en el pedido hay varias allocations con distintas "Tarifas a cerrar", se une el conjunto de habitaciones sin repetir.

### 6.2 Ir a la habitación
1. Clic en la lupa del Product: `#searchWrapper tp-button.lookupproduct button.tplookupproduct`. **No uses `.find-button` a secas**: lo comparte con la lupa de Supplier.
2. Se abre el modal "Product Find" (`.tpmodal-productlistnext`) con las opciones del hotel en `tp-grid[tpid="modalsNextprevproductMaingrid"]`. Celdas: `td.tpcol-locationcode`, `td.tpcol-servicecode`, `td.tpcol-suppliercode`, `td.tpcol-optioncode`, `td.tpcol-optiondescription`.
3. Armá el código largo de cada fila (location + service + supplier + código de opción) y hacé clic en la que coincide **exactamente** con la buscada. No hay scroll: paginá con `.tpmodal-productlistnext tp-button.next button` hasta encontrarla. **La última fila de una página se repite como primera de la siguiente: deduplicá por código largo.** Cortá cuando una página no traiga filas nuevas. Si no la encontrás, error.
4. Para `TODAS`, recorré todas las páginas y juntá las filas con service `HT` que no estén excluidas.
5. Menú → ítem de primer nivel cuyo `.menu-heading > label` dice `Rates` (clic en su `.click-area`). Esperá el fondo `.tpnavbackdrop`. Verificá que aparezca la grilla con la columna `th.tpcol-RatePeriod`.

### 6.3 Grilla de períodos
Es una tabla común (verificá si hay hoteles con muchas temporadas). Una fila por (período, price code):

| Dato | Celda |
|---|---|
| Rango | `td.tpcol-rateperiod`, ej. `29/Dec/2026 - 30/Jun/2027` |
| Price code | `td.tpcol-pricecodecode` |
| Status | `td.tpcol-ratestatuses` (`Confirmed`, `Manual`, `Closed`, ...) |
| Rate Name | `td.tpcol-ratenames` |

Releé la grilla completa después de cada split y cada save. **Ubicá las filas por (rango, price code), nunca por posición.** Si una fila del rango tiene un Rate Name distinto de `Standard` o más de un status en la celda, frená y avisá.

### 6.4 Qué períodos hay que tocar y qué splits hacen falta
1. Agrupá las fechas de la habitación en **rangos consecutivos** `[a, b]`.
2. Para cada período `[ps, pe]` que se superpone con `[a, b]` y que no esté "ya cerrado" según la tabla de la sección 4: la parte a cerrar es `[max(a, ps), min(b, pe)]`.
3. **Solo se parte donde el borde cae adentro del período:**
   - corte en `max(a, ps)` si ese valor es mayor que `ps`;
   - corte en `min(b, pe) + 1` si `min(b, pe)` es menor que `pe`.
4. Ejemplos con una grilla donde 17/11–23/11, 24/11 y 25/11–27/11 ya están en Manual y 28/11–30/11 está en Confirmed:
   - cerrar 20/11 al 30/11 → sin splits; se editan los períodos 28/11–30/11 (uno por price code);
   - un período 29/12/26–30/06/27 en Confirmed y cierre 29/12 al 05/01 → 1 corte en 06/01;
   - un período 01/12–25/12 en Confirmed y cierre 10/12 al 12/12 → 2 cortes, en 10/12 y en 13/12.

### 6.5 Hacer un split
Se abre desde el diálogo del período (`tp-button.splitdaterange > button`), y es un **segundo `tp-dialog` apilado**: apuntá siempre al que contiene `.split-content-panel`.

1. Verificá el título: `Split Date - 01/Dec/2026 - 25/Dec/2026` debe ser el período que querés dividir.
2. Checkbox `#split-applicable` ("Split All Applicable Price Codes"): leé la propiedad `checked` y hacé clic en su `label` solo si está destildado. Verificá que quedó tildado. Aplica el corte a todos los price codes que tengan **exactamente** el mismo período.
3. Escribí la fecha en `input.tpdate-productdatesplitpoint` (formato `DD/MM/AA`), blur, y confirmá en el `input.tphidden` hermano (formato `DD/Mon/YYYY`) que es la fecha correcta.
4. Esperá a que `button.tpbutton-addsplit` se habilite y hacé clic. Si no se habilita, la fecha no es válida: Exit y error.
5. Leé `ul.dateranges span.date-range-display` (formato `Tue 01/Dec/2026 - Tue 22/Dec/2026`, ignorá el día de la semana). Tienen que ser **exactamente dos rangos**: `[ps, X−1]` y `[X, pe]`. Si no, Exit.
6. `tp-button.ok button`. **Un solo corte por diálogo.** No hagas clic en los botones `.tpbutton-removesplit`.
7. Releé la grilla y verificá, price code por price code, que existe un período que cubre exactamente el rango buscado. Si algún price code tenía un período distinto y quedó sin dividir, repetí el split desde la fila de ese price code.

### 6.6 Editar un período
Clic en `td.tpcol-rateperiod` de la fila (rango, price code). Se abre `.tpmodal-productcosts`.

1. **Verificá el título:** `BUEHT1ESP06CPNV   24/Nov/2026/24/Nov/2026 "TR"` = código largo de la habitación, rango (las dos fechas separadas por `/`) y price code entre comillas. Si algo no coincide con lo esperado, Exit y error.
2. **Tarifa.** Pestaña `Rates` (`#tptablabel-tabs-rates`, abierta por defecto). La grilla `#tabs-rates #costs-panel table tbody tr` tiene filas Twin/Double Room, Single Room, Additional Adult, Child e Infant. En cada fila, el primer `td.tpcol-cost input.tpnumber-ratecostamount` es Group Cost. Si tiene un valor distinto de cero, escribí 0. No toques las filas vacías ni las que ya valen 0. Hay otro `#costs-panel` en la pestaña Extra Nights (oculta y vacía): no lo uses.
3. **Status.** Abrí la pestaña `Rate Set` (`#tptablabel-tabs-rateset`): su contenido **no existe en el DOM hasta que se hace clic**. El grupo `tp-group.tpgroup-ratestatus` tiene cinco radios: Confirmed, Provisional, Terminal, Closed y Manual. El seleccionado tiene la clase `checked`. **Elegí el radio por el texto de su etiqueta**, no por el `id` (`ratestatusManual_4`, el sufijo es la posición). Aplicá la tabla de la sección 4 y verificá que quedó seleccionado el correcto.
4. **Save** (`tp-button.save > button`, arranca deshabilitado). **En Rates el diálogo se cierra solo al guardar**: esperá a que desaparezca y, si no, error. Si no hubo ningún cambio, hacé Exit.

**Nunca hagas clic en** Delete Date Range, Copy Date Range, Insert Rate Set ni Delete Rate Set.

---

## 7. Protecciones duras

1. Nunca se reabre una fecha en allocation.
2. Nunca se cierran `600HTL` ni `ROOMS`, y solo service type `HT`. Si una fila del Sheet lo pidiera, frená y avisá.
3. Nunca se pasa un período de Closed a Manual.
4. Si el código, la descripción o la habitación linkeada de la allocation no coinciden con el Sheet, no se escribe nada.
5. Nunca se hace clic en la primera fila de una lista ni se confirma con Enter: siempre se elige por coincidencia exacta, y se frena si no hay una o hay más de una.
6. Antes de escribir se verifica el título del diálogo. Después de escribir se relee el valor.
7. Provisional o Terminal frenan el pedido.
8. Fechas fuera de la ventana o sin fila en la allocation se informan, no se ignoran en silencio.

---

## 8. Convenciones técnicas de Tourplan NX

- **Login/logout:** hay un número limitado de licencias simultáneas. Logout siempre en `finally`. Si el login falla por falta de licencia, mostrá un mensaje claro y reintentá más tarde. Test y Producción tienen **base paths distintos**.
- **Esperas:** Tourplan muestra un `<dialog open>` "PLEASE WAIT…" entre acciones. Esperá a que desaparezca (poll de hasta ~15 s) antes de cada clic importante. El menú de navegación puede dejar colgado un `.tpnavbackdrop` que tapa los clics siguientes: esperá a que se vaya.
- **Navegación entre pedidos:** pasá por `#/home` antes de `#/product`. Con el mismo hash la página no se recarga y el estado del pedido anterior queda cargado. (En el repositorio de referencia, además, la lupa de Product Search abre un popover en vez del modal completo en esa situación. En este flujo usamos el modal "Product Find" que abre la lupa dentro del producto, como se describe en 6.2.)
- **Campos numéricos Angular (`tp-number`):** asignar `.value` o `send_keys` no se registra. Usá el patrón completo: foco, setter nativo del `value`, eventos `input` y `change`, blur, y verificá releyendo. Reusá el helper que ya exista en el repositorio de referencia.
- **Fechas:** Tourplan muestra `DD/Mon/YYYY` con meses en inglés abreviado, y puede reformatear lo que se escribe. Compará siempre fechas **parseadas por valor**, nunca por texto.
- **Botones Save y Exit:** hay varios en pantalla. Elegí siempre el del diálogo activo (el último `tp-dialog`), y esperá a que Save esté habilitado.
- **Selectores:** preferí clases de componente (`tpcol-*`, `tpdate-*`, `tp-button.save`), `tpid`, `tptype` y el texto visible. Evitá `_ngcontent-*`, `id` con GUID y posiciones.
- **Grillas con scroll virtual:** nunca guardes referencias a filas ni leas o escribas por índice. Releé por contenido.

---

## 9. Cola, ejecución y concurrencia

- **Modo `lectura`:** no escribe nada en Tourplan. En el Sheet solo escribe en OBSERVACIONES el plan (qué cerraría, qué saltearía y por qué). No cambia el ESTADO ni toma el pedido. Es el modo por defecto.
- **Modo `aplicar`:** ejecuta.
- **Tomar un pedido (varias PCs a la vez):** leé las filas `PENDIENTE`, escribí `TOMADO_POR` y `TOMADO_EN` y pasá el ESTADO a `EN CURSO`, esperá un par de segundos y **releé**: si `TOMADO_POR` sigue siendo vos, es tuyo; si no, soltalo. Google Sheets no tiene una escritura atómica, por eso la relectura. Una fila `EN CURSO` hace más de N minutos (configurable) se muestra como posiblemente abandonada y se puede retomar a mano.
- **Procesamiento:** fila por fila, con `try/except` por fila para que un error no frene el lote. Es resumible: si la fase de allocation está `OK` y la de tarifa `PENDIENTE`, solo se hace tarifa. Todo el proceso es idempotente: correrlo dos veces no cambia nada la segunda vez.
- **Orden dentro de un pedido:** abrir el hotel una sola vez, cerrar las allocations seleccionadas, y después las tarifas del conjunto de habitaciones.
- **Resultado por fase:** `OK` (con resumen de cuántas fechas se cerraron y cuántas ya estaban cerradas), `SALTEADO` (con motivo: no cierra tarifa, allocation vacía, ya estaba todo cerrado) o `ERROR: detalle`.

---

## 10. Plan por etapas (esperá mi OK entre una y otra)

0. Leer el repositorio de referencia, resumirlo, proponer la estructura. **Esperar OK.**
1. Esqueleto: lectura del Sheet, pantallas 1 a 3 y escritura de pedidos en COLA. Sin Selenium.
2. Selenium en modo lectura contra el Tourplan de **prueba**: login, buscar hotel, abrir Allocations, filtrar, ubicar la allocation, verificar código, descripción y habitación, leer los días y mostrar el plan.
3. Aplicar allocations en prueba. Probar idempotencia.
4. Rates en modo lectura: leer la grilla de períodos y calcular los cortes y las ediciones.
5. Rates en modo aplicar, en prueba.
6. Cola completa: tomar pedidos, `EN CURSO`, "Enviar y ejecutar", vista de cola.
7. Endurecimiento: errores, logs, reintentos, mensajes claros.

### Pruebas de aceptación (todas en el entorno de prueba)
- El modo lectura no escribe en Tourplan ni cambia estados.
- Correr dos veces el mismo pedido: la segunda vez todo queda `SALTEADO`.
- Fecha con Used = 0, con Used > 0 y con Max < Used.
- Fecha ya cerrada (se saltea) y fecha posterior a lo cargado (se informa).
- Rangos con 0, 1 y 2 splits (los ejemplos de la sección 6.4).
- TR, ND y EM quedan en Manual; otros price codes en Closed; un período Closed no cambia.
- Un período en Provisional frena el pedido.
- Allocation vacía: no hay nada que escribir y se pasa a tarifas.
- Código, descripción o habitación que no coinciden: no se escribe nada.
- `TODAS` excluye `600HTL` y `ROOMS`, y solo toma service type `HT`.
- Dos PCs con la misma cola: nadie procesa el mismo pedido dos veces.

---

## 11. Datos reales para probar

| Hotel | Datos |
|---|---|
| Intersur Recoleta | `1TULY1`, allocation `1TULY1 EX` / `EXECUTIVE ROOM`. No cierra tarifa. |
| Ramada Buenos Aires Centro | `6RABA1`, allocation `Standard` / `Standard CIERRA DATABASE`, habitación `BUEHT6RABA1ST`. Cierra tarifa (`LINKEADA`). |
| NH Edelweiss | `1EDE01`, allocations `1EDE01 CL` (STANDARD), `1EDE01 SP` (SUPERIOR ROOM) y `SPWV` (SUPERIOR VISTA). No cierra tarifa. |
| Hotel `1ESP06` | Opción `CPNV`, allocation `CIERRA DATABASE CPNV CONCEPT ROOM`. La grilla de Rates tiene price codes TR y ND, con períodos Confirmed y Manual. |
| Novotel | Allocation vacía `SIN FS-CIERRA D` / `CERRAR DATABASE`. Opciones: `SPQ` y `SPT` (HT, se cierran), `600HTL` (excluida), `600HTX` (service HX) y `MAP` (service ML). Falta el código de hotel en el Sheet. |

Pedime qué hoteles existen en el Tourplan de prueba antes de la etapa 2.

---

## 12. Lo que necesito de vos antes de empezar

- La ruta local del repositorio de referencia.
- La URL y las credenciales del Tourplan de prueba, y cómo se guardan en este proyecto (según el repositorio de referencia).
- El ID del Google Sheet importado.
- Qué hoteles de prueba hay en Tourplan Test.
