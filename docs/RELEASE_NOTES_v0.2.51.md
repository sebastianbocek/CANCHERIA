# CANCHERIA v0.2.51

## Correcciones

- La adjudicación temporal trabaja únicamente con los mensajes del turno físico actual, evitando que una frase histórica invalide referencias como “hoy”.
- Si el modelo entrega evidencia temporal ajena al turno actual, CANCHERIA realiza una relectura IA focalizada antes de decidir o solicitar datos.
- La consulta “hola tenes cancha para hoy” conserva `query_availability`, resuelve la fecha actual y consulta disponibilidad en lugar de preguntar nuevamente el día.
- El proceso de WhatsApp se ejecuta sin buffering y fuerza escritura inmediata de `stdout`/`stderr`, por lo que el log del escritorio se actualiza línea por línea.
- El drenaje visual del log usa lotes acotados para mantener la interfaz responsiva incluso durante ráfagas extensas.

## Verificación

- 179 pruebas automatizadas aprobadas.
- 1 prueba visual omitida únicamente por falta de display Tk en el entorno de pruebas.
