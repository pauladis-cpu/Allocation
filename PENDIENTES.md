# Pendientes

## Validado en Tourplan de prueba (todo confirmado funcionando en Test)
- [x] Aplicar allocations (escritura de Max/Release, Save, relectura).
- [x] Rates: Product Find, menú Rates, grilla de períodos, split, edición de período.
- [x] Diálogo del período después de «OK» en Split Date (se espera a que Save se habilite).
- [x] Cortes encadenados en una sola apertura del período.
- [x] Reglas de tarifas: Provisional, Terminal (EM a Manual), FX sin editar (sí puede cortarse), Closed no se reabre.
- [x] Regla HG (tarifas solo hasta «Vigente hasta»).
- [x] Dos PCs con la misma cola (toma de pedidos); un TOMADO_POR viejo ya no bloquea reintentos.
- [x] Filtro «Date To» del diálogo de la allocation.
- [x] Estado «NO APLICA» cuando ninguna allocation cierra tarifa.

## Pendiente: Producción
- [ ] A la espera del cierre para probar en Producción. Primera corrida: un solo pedido chico, un hotel conocido,
  verificado a mano en Tourplan después (ver sección 7 de `CHECKLIST_PRUEBAS.md`).
- [ ] Velocidad de espera: en Producción la app usa ×1.5 (fijo en `app.py`). Si aparecen avisos de «dialog de carga» o
  de «la grilla todavía no refleja…», subirla (idea: campo «Velocidad» en Configuración).
- [ ] Plan de reversa y confirmación explícita de Producción en Configuración antes de aplicar.

## Etapa 7 (endurecimiento): propuesta, sin empezar
- [x] Log de cada ejecución en archivo con hora por línea: `~/.tourplan-allocation/logs/ejecucion_AAAAMMDD_HHMMSS.log` (se conservan los últimos 30).
- [x] Observaciones de la COLA con la acción sugerida cuando una fase da ERROR (`Qué hacer: …`).
- [ ] Reintentos de pasos frágiles según lo que muestre Producción (login, abrir hotel, guardado).
- [ ] Retomar un pedido si el proceso muere sin abortar (pedido que queda EN CURSO).
- [ ] Historial en la pestaña HISTORIAL del Sheet (a acordar: toca el esquema).

## Revisar solo si aparece un caso
- [ ] Lista de allocations del hotel (`tp-grid[tpid="allocations-grid"]`): hoy se busca solo entre las filas renderizadas (posible scroll virtual).
- [ ] Grilla de tarifas del período (`#tabs-rates #costs-panel`): se asume que las 5 filas están todas en el DOM.
- [ ] Corte anticipado del scroll de Rates (`ini <= límite`): si la grilla se ordena por fecha de inicio descendente
  (como se vio en Test) es correcto; si una habitación da «SIN PERÍODO» y el período existe, usar `TOURPLAN_RATES_ESCANEO_COMPLETO=1`.
- [ ] Habitación `IGRHT1INT01MEJVT3` dio «SIN PERÍODO» en Test: confirmar si realmente no tenía períodos para esas fechas.

## Datos del registro
- [ ] Novotel e Ibis Obelisco sin código de hotel; 6 allocations en REVISAR; «Vigente hasta» vacío en algunas filas
  (una allocation HG sin esa fecha frena la fase de tarifa).
- [ ] `ID_PEDIDO` con formato fecha-hora (`P-AAAAMMDD-HHMMSS-XXXX`): funciona y es único; cambiar el formato es opcional.

## Hecho (para no perderlo de vista)
- [x] Sin scroll vertical en las pantallas (tamaños compactos y escala automática según el alto de la ventana).
- [x] Interfaz simplificada: sin modo lectura ni casilla de revisión (Volver / Enviar a la cola / Enviar y ejecutar).
- [x] Opción OTRO + columna «Habitaciones a cerrar».
