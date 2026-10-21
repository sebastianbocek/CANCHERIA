# CANCHERIA v0.2.54

## Correcciones

- Las horas naturales de 12 horas con franja horaria se validan contra su equivalente de 24 horas: “9 de la noche” conserva `21:00` y “3 de la tarde” conserva `15:00`.
- Una hora exacta aportada en el turno actual reemplaza explícitamente la hora del hold anterior; ya no puede ser descartada y sustituida por contexto viejo.
- Los cambios hacia un horario que ya pasó se explican como tales, en vez de informarlos erróneamente como un bloque ocupado.
- Si un cambio de hold no puede concretarse, el hold anterior permanece protegido y la respuesta lo informa claramente.
- Se impide crear reservas en horarios pasados incluso cuando la anticipación mínima configurada es cero.

## Caso corregido

Con un hold para mañana a las 15:00, “no, mejor a las 9 de la noche hoy” cambia simultáneamente el día y la hora a hoy 21:00, verifica ese bloque y reemplaza el hold de forma atómica. En cambio, pedir hoy a las 15:00 después de esa hora informa que el horario ya pasó y mantiene el hold original.

## Pruebas

- La suite automatizada completa fue aprobada; las pruebas visuales dependientes de Tk se omiten cuando ese entorno gráfico no está disponible.
