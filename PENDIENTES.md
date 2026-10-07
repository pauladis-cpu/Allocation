# Pendientes

## Por validar en Tourplan de prueba (código hecho, sin probar contra Tourplan real)
- [ ] Aplicar allocations (escritura de Max/Release, Save, relectura).
- [ ] Rates: Product Find, menú Rates, grilla de períodos, split, edición de período.
- [ ] Qué pasa con el diálogo del período después de «OK» en Split Date.
- [ ] Dos PCs con la misma cola (toma de pedidos).
- [ ] Filtro «Date To» del diálogo de la allocation (se amplía antes de leer los días).

## Rates: cortes encadenados (hecho, falta validar en Test)
- [x] Los cortes de un mismo período se hacen en una sola apertura: se agrega cada fecha con «Add Split»
  (se verifica la lista `ul.dateranges` tras cada una) y recién después «OK» + Save.
- [ ] Validar en Test con un período que necesite 2 o más cortes.

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
