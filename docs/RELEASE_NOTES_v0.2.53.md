# CANCHERIA v0.2.53

## Correcciones

- La IA reconstruye las modificaciones parciales de un turno según su estado real: disponibilidad, hold pendiente o reserva persistida.
- Expresiones discursivas como “no pero” dejan de convertirse en una segunda intención transaccional cuando sólo introducen una corrección.
- Dos fragmentos que describen el mismo estado final se consolidan en una única mutación atómica antes de tocar el calendario.
- Si la planificación por subintenciones no consigue un plan completo, el orquestador canónico vuelve a analizar el turno físico completo en vez de generar un handoff humano por error interno.
- Los cambios de día, hora, duración, deporte, cancha o addon del mismo turno se consideran modificadores de un único objetivo y conservan los campos que el cliente indicó que siguen iguales.

## Caso corregido

Con un hold de Tenis para mañana a las 15:00, el mensaje “no pero cambia el día a hoy por favor, la hora está bien” se interpreta como una sola reprogramación contextual: cambia el día, conserva hora, deporte y duración, verifica disponibilidad y reemplaza el hold de forma atómica.

## Pruebas

- 184 pruebas automatizadas aprobadas.
