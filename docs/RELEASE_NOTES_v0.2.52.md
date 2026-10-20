# CANCHERIA v0.2.52

## Correcciones

- Una hora aislada continúa el día de la disponibilidad consultada previamente para el mismo teléfono.
- Una inferencia implícita de “hoy” ya no puede sobrescribir un día cuando la memoria persistida y el orquestador coinciden.
- La recuperación de un hold inexistente conserva la disponibilidad verificada y la pregunta pendiente no transaccional.
- El contexto de disponibilidad se mantiene separado del estado transaccional de una reserva, evitando borrar memoria válida durante la recuperación.

## Caso verificado

1. El cliente consulta disponibilidad para hoy.
2. Luego pregunta “¿y mañana?”.
3. Finalmente responde “a las 12”.
4. CANCHERIA conserva mañana como día activo y valida las 12:00 de ese día.

## Pruebas

- 182 pruebas automatizadas aprobadas.
