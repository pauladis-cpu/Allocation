# Checklist de pruebas en Test (antes de Producción y de la etapa 7)

Entorno: `https://tourplannx.eurotur.com.ar/TourplanNX_Test`. Marcar cada ítem con la fecha y el ID de pedido usado.
Regla general: **nada se prueba en Producción** hasta tener todo lo marcado como «Bloqueante» en verde.

Convenciones: **[B]** = bloqueante para Producción · **[E7]** = insumo para el diseño de la etapa 7.

---

## 0. Preparación
- [ ] **[B]** Hoteles de prueba creados en Test (con allocations en cada situación de las secciones 3 y 4).
- [ ] **[B]** `config.json` apunta a Test; Producción **no** confirmada (`produccion_confirmada` en falso).
- [ ] **[B]** Credenciales de Google y de Tourplan cargadas; la app abre y lee el Sheet (ALLOCATIONS, COLA, HISTORIAL).
- [ ] Anotar el estado inicial de cada hotel de prueba (captura de Allocations y de Rates) para poder comparar y revertir.
- [ ] Probar con `VELOCIDAD` normal y con una más lenta (equipo lento).

## 1. Interfaz y armado del pedido
- [ ] Pantalla 1: buscar hotel por nombre y por código; hotel sin código aparece marcado y no deja avanzar.
- [ ] Pantalla 2: elegir una allocation, varias, y «todas»; calendario con selección simple, rango, fechas sueltas y desmarcar.
- [ ] Fechas pasadas: no se pueden elegir / se avisa que no se consideran.
- [ ] Fechas posteriores a «Vigente hasta»: aviso de que en allocation no se tocan.
- [ ] Allocation con tarifas en `REVISAR`, o `OTRO` sin «Habitaciones a cerrar»: **bloquea** el envío.
- [ ] Allocation vacía (sin habitación): se informa, no rompe.
- [ ] Pantalla 3: solo botones **Volver / Enviar a la cola / Enviar y ejecutar**; muestra el entorno (Test/Producción).
- [ ] Sin scroll vertical en las 3 pantallas, con ventana chica y grande.
- [ ] «Enviar a la cola» escribe la fila en COLA con estados `PENDIENTE` (allocation y tarifa) y no ejecuta.
- [ ] Enviar dos veces el mismo pedido seguido: la verificación anti-carrera no duplica ni pisa filas.
- [ ] Configuración: guardar usuario/clave/URL; cambiar a Producción exige confirmación explícita.

## 2. Cola, estados y concurrencia
- [ ] Pedido nuevo → `PENDIENTE`; al ejecutarlo → `EN CURSO` → `OK` / `SALTEADO` / `ERROR: detalle`, **por fase**.
- [ ] «Enviar y ejecutar» ejecuta solo ese pedido; «Ejecutar pendientes» procesa todos los pendientes en orden.
- [ ] Una fase en `OK` y la otra en `ERROR`: al poner la fallida en `PENDIENTE` se reintenta **solo esa fase**.
- [ ] Si la fase allocation falla, la de tarifa queda `PENDIENTE` («no se evaluó») y no se ejecuta.
- [ ] **Abortar** desde la UI en medio de: login, allocations, un split de Rates, un guardado → lo `EN CURSO` vuelve a `PENDIENTE` y no queda ningún diálogo ni cambio a medias. **[E7]**
- [ ] Cerrar la ventana/proceso de golpe (sin abortar): ver en qué quedó la fila (¿`EN CURSO` colgado?). **[E7]**
- [ ] Dos PCs con la misma cola: no toman el mismo pedido (relectura al tomar). **[B]**
- [ ] Pedido con hotel que no está en el registro: error claro, sin tocar Tourplan.
- [ ] Pedido con allocation que no está en el registro: error claro.
- [ ] Fechas ilegibles en la columna de fechas: error claro.
- [ ] Todas las fechas pasadas: «no quedan fechas vigentes», sin tocar Tourplan.
- [ ] Observaciones y estados se leen bien en la hoja (formato `ERROR: …`, sin textos cortados que confundan).
- [ ] Columnas de la hoja reordenadas / con una columna extra: la app sigue ubicando por encabezado.

## 3. Allocations (Max / Release)
Una prueba por situación, en una fecha distinta cada una:
- [ ] **Used = 0** → Max = 0 (Release no cambia).
- [ ] **Used > 0** → Max = Used y Release = 9999.
- [ ] **Max < Used** → Max sube a Used (único caso en que Max sube) y Release = 9999.
- [ ] Fecha **ya cerrada** → no escribe, queda `SALTEADO`.
- [ ] **Nunca reabrir**: fecha con Max menor al que se calcularía → no se sube.
- [ ] Fecha **sin fila** en la grilla (posterior a lo cargado) → se informa, no falla.
- [ ] Rango largo de fechas (más de una pantalla de grilla): lee/escribe todas (scroll virtual de días).
- [ ] Fecha en otro mes / cruce de año.
- [ ] **Idempotencia**: correr el mismo pedido dos veces → la segunda queda todo `SALTEADO`.
- [ ] Varias allocations en un mismo pedido (una vacía, una normal, una con grupos de columnas).
- [ ] Allocation con grupos de columnas distintos de GENERAL (el caso Carles): se lee bien y no frena por error.
- [ ] Allocation con código parecido a otra (verificación de código + descripción + habitación exactas).
- [ ] «Show Release As Date» activo / inactivo.
- [ ] Verificar en Tourplan, abriendo el hotel a mano, que los valores quedaron guardados (relectura propia, no la de la app).
- [ ] Filtro «Date To» del diálogo: fechas más allá del filtro por defecto se leen.
- [ ] Save no se habilita / diálogo no cierra: la app informa y no deja cambios a medias (Discard). **[E7]**

## 4. Rates (tarifas)
### 4.1 Elección de habitaciones
- [ ] `LINKEADA`: cierra solo la habitación linkeada.
- [ ] `TODAS`: cierra todas las HT del hotel (nunca `600HTL` ni `ROOMS`).
- [ ] `OTRO` + «Habitaciones a cerrar» con 1, 2 y varios códigos (separados por coma, punto y coma, salto de línea; con mayúsculas/minúsculas mezcladas).
- [ ] `OTRO` con código inexistente / de otro hotel / service type distinto de HT / `600HTL` / `ROOMS` → se frena con mensaje claro.
- [ ] Varias allocations del pedido que piden la misma habitación → se cierra una sola vez.
- [ ] Allocation con «Cierra tarifa» = No → fase tarifa `SALTEADO` («no cierra tarifa»).
- [ ] Habitación linkeada = `Multiple Options` con `LINKEADA` → error claro.

### 4.2 Reglas por status y price code
Objetivo: TR / ND / EM → **Manual**; el resto → **Closed**.
- [ ] TR, ND, EM en **Confirmed** → Manual.
- [ ] Otros price codes en **Confirmed** → Closed.
- [ ] **Provisional**: igual que Confirmed (TR/ND/EM → Manual, otros → Closed).
- [ ] **Terminal**: igual que Confirmed: TR / ND / EM → Manual; el resto → Closed.
- [ ] Ya en **Closed** → se saltea y **nunca** pasa a Manual (ni TR/ND/EM).
- [ ] Ya en **Manual** → TR/ND/EM se saltea; otros → Closed.
- [ ] **FX**: nunca se edita (ni tarifa ni status), aunque esté Confirmed.
- [ ] Status ambiguo / desconocido → frena con error claro.
- [ ] **Rate Name** distinto de Standard: no influye (se cierra igual).
- [ ] Tarifas quedan en **0** (Twin/Double, Single, Additional Adult, Child, Infant) donde corresponde.
- [ ] Período con tarifa en 0 ya puesta y status distinto: solo se corrige lo que falta.
- [ ] Idempotencia: segunda corrida → todo `SALTEADO` («ya estaba todo cerrado»).

### 4.2b Rate sets
- [ ] Período con **2 rate sets** (status «A, B»): ambos pasan a su destino, tarifa en 0 en los dos, un solo Save.
- [ ] Período con **3+ rate sets**; el selector llega al último y la flecha derecha queda deshabilitada.
- [ ] Rate sets con status distintos («Manual, Confirmed» en TR/ND/EM): se corrige el que falta y todos quedan en Manual.
- [ ] Status mezclado con un Closed («Manual, Closed» en TR): el Manual pasa a Closed (un Closed no se reabre) y quedan todos iguales.
- [ ] Período con rate sets ya cerrados en todos: se saltea.
- [ ] Verificar a mano en Tourplan el status y la tarifa de **cada** rate set después de ejecutar.

### 4.3 Cortes (splits)
- [ ] Fecha única dentro de un período → 1 corte (el día queda como período propio de 1 día).
- [ ] Rango de fechas dentro de un período largo → 2 cortes encadenados en **una sola apertura**.
- [ ] Varias fechas sueltas en el mismo período (ej. 15/10 y 16/10) → todas en una apertura; la lista «New Date Ranges» coincide.
- [ ] Rango que coincide exactamente con un período → sin corte, solo edición.
- [ ] Rango que cubre varios períodos consecutivos → sin cortes innecesarios.
- [ ] Fecha en el **primer** día y en el **último** día de un período.
- [ ] Fecha en borde entre dos períodos (fin de uno / inicio del siguiente).
- [ ] Price codes con **cortes distintos** entre sí en las mismas fechas.
- [ ] Casilla «Split All Applicable Price Codes»: **aparece** (se tilda y se verifica) y **no aparece** (un solo price code con ese período: se corta sin ella).
- [ ] El corte también parte el período de **FX** y FX queda sin editar.
- [ ] Después de OK del split: el diálogo del período queda abierto, Save se habilita (con retraso) y se guarda; si no se habilita, se reintenta sin repetir el corte. **[E7]**
- [ ] Grilla que se recarga y trae menos filas tras guardar: la app relee y no falla con «0 filas coinciden».
- [ ] Período sin cobertura (fecha sin período en Rates) → se informa «SIN PERÍODO».

### 4.4 Lectura de la grilla
- [ ] Hotel con pocos períodos (todo visible) y con muchos (scroll vertical de la grilla).
- [ ] Fecha cercana: el scroll se corta cerca (margen de 5 meses) y no recorre todo.
- [ ] Fecha lejana y pedido con fechas muy dispersas: lee lo necesario.
- [ ] Una fila solo visible tras hacer scroll se encuentra y se abre correctamente.
- [ ] `TOURPLAN_RATES_ESCANEO_COMPLETO=1`: lee todo y da el mismo resultado.
- [ ] Períodos largos con inicio antiguo (revisar si el corte anticipado trunca). **[E7]**
- [ ] Mismo período + mismo price code con Rate Names distintos: desempata por Rate Name; si sigue ambiguo, frena.

### 4.5 Regla HG
- [ ] Allocation con descripción **`HG - …`** y «Vigente hasta» → tarifas cerradas **solo hasta esa fecha** (inclusive); fechas posteriores no se tocan en Rates.
- [ ] Allocation **sin HG** → se cierran todas las fechas indicadas.
- [ ] Fecha igual a «Vigente hasta» (entra) y un día después (no entra).
- [ ] HG con **todas** las fechas fuera de vigencia → la habitación queda salteada con mensaje.
- [ ] HG con «Vigente hasta» vacío o no-fecha → falla la fase tarifa con mensaje claro (no adivina).
- [ ] Habitación pedida por una HG y por una no-HG a la vez → se cierran todas las fechas.
- [ ] Descripción tipo `HGX…` o `Hotel HG` → **no** se trata como HG.
- [ ] La fase de allocation **no** cambia por HG (se cierra según lo pedido).

## 5. Pedidos combinados y casos reales
- [ ] Pedido real completo de un hotel con linkeada + otra habitación (el 1MERC1 que falló): termina `OK` en ambas fases.
- [ ] Pedido con 3+ allocations, mezcla de vacías, HG, linkeadas y `TODAS`.
- [ ] Pedido con muchas fechas (un mes entero) y con fechas en dos años.
- [ ] Reintento de un pedido que falló a mitad: retoma sin duplicar cortes ni reabrir nada.
- [ ] Lote con 3–5 pedidos seguidos: una falla no frena a los demás.
- [ ] Sesión larga (30+ min): el login se mantiene; si expira, ver qué pasa. **[E7]**
- [ ] Logout al terminar y al abortar (no quedan licencias de Tourplan tomadas).

## 6. Errores forzados (insumo de la etapa 7)
Provocarlos a propósito y anotar qué ve el usuario, qué queda en la hoja y si se puede retomar:
- [ ] Clave de Tourplan incorrecta.
- [ ] Sin licencias libres de Tourplan.
- [ ] Corte de internet / VPN en medio de un pedido.
- [ ] Token de Google vencido o sin permisos sobre el Sheet.
- [ ] Hoja COLA con encabezado renombrado o columna faltante.
- [ ] Hotel inexistente en Tourplan (código mal escrito).
- [ ] Dialogo inesperado de Tourplan (aviso, error del servidor) en medio de un guardado.
- [ ] Chrome cerrado a mano durante la ejecución.
- [ ] Disco lleno / sin permisos de escritura en `~/.tourplan-allocation/`.
- [ ] Para cada uno: ¿el mensaje es claro?, ¿hay captura/log guardado?, ¿la fila queda retomable? **[E7]**

## 7. Seguridad de Producción (antes de usarla)
- [ ] **[B]** La app **bloquea** aplicar en Producción mientras no esté confirmada la opción en Configuración.
- [ ] **[B]** Con la URL de Producción y sin `TOURPLAN_PERMITIR_PRODUCCION=1`, el runner se niega a aplicar.
- [ ] **[B]** La UI muestra claramente que el entorno es Producción (color/rótulo) antes de «Enviar y ejecutar».
- [ ] **[B]** Primera corrida en Producción: un solo pedido chico, un hotel conocido, verificado a mano después.
- [ ] **[B]** Plan de reversa: cómo volver a abrir lo cerrado por error (manual en Tourplan) y quién lo hace.
- [ ] Registro de quién ejecutó qué (columna «Quién» / HISTORIAL) se completa.
- [ ] Revisar el Sheet de producción vs. el de pruebas (si son distintos): mismos encabezados y pestañas.

## 8. Criterio de salida
- [ ] Todas las secciones 3, 4 y 5 en verde sin intervención manual, **dos corridas seguidas**.
- [ ] Todos los ítems **[B]** en verde.
- [ ] Lista de fallos **[E7]** consolidada → define el alcance de la etapa 7 (errores, logs, reintentos, mensajes).
- [ ] Recién entonces: etapa 7 y luego primer pedido en Producción.
