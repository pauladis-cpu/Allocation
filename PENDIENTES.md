# Pendientes

## Validado en Tourplan de prueba (todo confirmado funcionando en Test)
- [x] Aplicar allocations (escritura de Max/Release, Save, relectura).
- [x] Rates: Product Find, menú Rates, grilla de períodos, split, edición de período.
- [x] Diálogo del período después de «OK» en Split Date (se espera a que Save se habilite).
- [x] Cortes encadenados en una sola apertura del período.
- [x] Reglas de tarifas: Provisional, Terminal (TR/ND/EM a Manual, el resto a Closed), FX sin editar (sí puede cortarse), Closed no se reabre.
- [x] Regla HG (tarifas solo hasta «Vigente hasta»).
- [x] Dos PCs con la misma cola (toma de pedidos); un TOMADO_POR viejo ya no bloquea reintentos.
- [x] Filtro «Date To» del diálogo de la allocation.
- [x] Estado «NO APLICA» cuando ninguna allocation cierra tarifa.

## Validado en Test: rate sets
- [x] Períodos con varios rate sets: cada uno se procesa igual (tarifa en 0 y status) y se guarda una sola vez.
- [x] Todos los rate sets de un período terminan en el mismo status; un período ya procesado a medias («Manual, Confirmed») se completa.
- [x] Con un Closed que no puede reabrirse, los demás rate sets pasan a Closed.

## Pendiente: Producción
- [ ] A la espera del cierre para probar en Producción. Primera corrida: un solo pedido chico, un hotel conocido,
  verificado a mano en Tourplan después (ver sección 7 de `CHECKLIST_PRUEBAS.md`).
- [ ] Velocidad de espera: en Producción la app usa ×1.5 (fijo en `app.py`). Si aparecen avisos de «dialog de carga» o
  de «la grilla todavía no refleja…», subirla (idea: campo «Velocidad» en Configuración).
- [ ] Plan de reversa y confirmación explícita de Producción en Configuración antes de aplicar.

## Etapa 7 (endurecimiento): propuesta, sin empezar
- [x] Log de cada ejecución con hora por línea. Las corridas lanzadas desde la app tienen su carpeta
  `~/.tourplan-allocation/logs/AAAAMMDD_HHMMSS/` (`corrida.log`, `estado.json`, `screenshots/`; se conservan las últimas 30);
  una corrida manual de `runner.py` sigue dejando `ejecucion_*.log`.
- [x] Historial de corridas: vista «Historial» de la app (inicio, duración, estado, resultados, log y capturas de errores).
- [x] Capturas de pantalla solo cuando se reporta un error (`error_*`, `login_fallido`, `login_sin_*`).
- [x] Login con reintento por licencias agotadas («Maximum Users Exceeded»): 3 intentos, 5 min entre cada uno, cartel con
  cuenta regresiva en la app. Si se agotan, los pedidos siguen PENDIENTE (código de salida 76).
- [x] Sonido al terminar la corrida (Windows; se desactiva en Configuración).
- [x] Observaciones de la COLA con la acción sugerida cuando una fase da ERROR (`Qué hacer: …`).
- [ ] Reintentos de pasos frágiles según lo que muestre Producción (abrir hotel, guardado). El login ya reintenta por licencias.
- [ ] Retomar un pedido si el proceso muere sin abortar (pedido que queda EN CURSO).
- [ ] Historial en la pestaña HISTORIAL del Sheet (a acordar: toca el esquema). El historial local de la app ya existe.

## Revisar solo si aparece un caso
- [ ] Lista de allocations del hotel (`tp-grid[tpid="allocations-grid"]`): hoy se busca solo entre las filas renderizadas (posible scroll virtual).
- [ ] Grilla de tarifas del período (`#tabs-rates #costs-panel`): se asume que las 5 filas están todas en el DOM.
- [ ] Corte anticipado del scroll de Rates (`ini <= límite`): si la grilla se ordena por fecha de inicio descendente
  (como se vio en Test) es correcto; si una habitación da «SIN PERÍODO» y el período existe, usar `TOURPLAN_RATES_ESCANEO_COMPLETO=1`.

## Datos del registro
- [ ] `ID_PEDIDO` con formato fecha-hora (`P-AAAAMMDD-HHMMSS-XXXX`): funciona y es único; cambiar el formato es opcional.

## Hecho (para no perderlo de vista)
- [x] Sin scroll vertical en las pantallas (tamaños compactos y escala automática según el alto de la ventana).
- [x] Interfaz simplificada: sin modo lectura ni casilla de revisión (Volver / Enviar a la cola / Enviar y ejecutar).
- [x] Opción OTRO + columna «Habitaciones a cerrar».
