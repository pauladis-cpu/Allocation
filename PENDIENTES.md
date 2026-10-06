# Pendientes

## Por validar en Tourplan de prueba (código hecho, sin probar contra Tourplan real)
- [ ] Aplicar allocations (escritura de Max/Release, Save, relectura).
- [ ] Rates: Product Find, menú Rates, grilla de períodos, split, edición de período.
- [ ] Qué pasa con el diálogo del período después de «OK» en Split Date.
- [ ] Dos PCs con la misma cola (toma de pedidos).
- [ ] Filtro «Date To» del diálogo de la allocation (se amplía antes de leer los días).

## Rates: encadenar los cortes (splits) en una sola apertura del período
- [ ] Hoy se hace **un corte por diálogo** (spec 6.5, paso 6): si un período necesita varios cortes
  (ej. 15/10 y 16/10), la app abre el mismo período una vez por cada corte, relee la grilla y repite.
  Tourplan permite agregar **varios splits juntos** en el mismo diálogo Split Date. Cambiar el flujo para:
  abrir el período una sola vez, agregar todos los cortes de ese período (varias veces "Add Split" con
  sus fechas), verificar que `ul.dateranges` quede con los N+1 rangos esperados, y recién ahí «OK».
  - Lógica: `allocation/rates_plan.py` ya calcula todos los cortes de un período (`Plan.cortes`, agrupables por
    `(ini, fin)`); falta agruparlos y pasarle la lista a `tourplan_flujos/rates.py:hacer_corte`.
  - Validar en Test cómo se comporta la lista de rangos con varios cortes y qué pasa con el diálogo del
    período después de «OK».
  - Esto cambia la regla «un solo corte por diálogo» de la especificación: confirmar antes de implementarlo.

## A confirmar en la próxima corrida en Test
- [ ] Que ya no aparezca el aviso repetido de «dialog de carga seguía abierto». Si aparece, el log ahora
  imprime el texto del dialog que lo causa (`⚠ Un dialog de carga seguía abierto tras esperar: [...]`).

## Otras grillas que podrían tener scroll virtual (revisar si aparece un caso)
- [ ] Lista de allocations del hotel (`tp-grid[tpid="allocations-grid"]`): hoy se busca solo entre las filas renderizadas.
- [ ] Grilla de tarifas del período (`#tabs-rates #costs-panel`): hoy se asume que las 5 filas (Twin/Double, Single,
  Additional Adult, Child, Infant) están todas en el DOM.

## Hecho (para no perderlo de vista)
- [x] Sin scroll vertical en las pantallas (tamaños compactos y escala automática según el alto de la ventana).
- [x] Reglas de tarifas actualizadas (ver README): Provisional como Confirmed, Terminal a Closed, FX nunca se edita (sí puede cortarse).

## Validar en Test: reglas nuevas de tarifas
- [ ] Un período Provisional (TR/ND/EM a Manual, otros a Closed) y uno Terminal (a Closed) con el pedido real.
- [ ] Hotel con price code FX que comparte el período: el corte (con «Split All Applicable Price Codes») corta también a FX,
  y después FX queda sin tarifa en 0 ni cambio de status.
