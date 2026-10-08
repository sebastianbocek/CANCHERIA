# CANCHERIA v0.2.6

Esta versión elimina la pregunta redundante por el día cuando el cliente ya dio
una hora exacta y no mencionó otra fecha.

## Fast path temporal

- `Hola tenes cancha para las 7` se interpreta como disponibilidad para hoy a las 19:00.
- La regla sigue funcionando aunque una conversación anterior haya dejado otro día en memoria.
- Una fecha explícita como `mañana`, `domingo` o `10/10` continúa teniendo prioridad y nunca es reemplazada por hoy.
- El agente ya no cae en `¿Qué día te gustaría?` para este caso.

## Redacción de alternativas

Las opciones excluyentes se presentan con `o`:

`¿Qué querés reservar: Futbol 5, Tenis o Pádel?`

## Validación

Se agregó una regresión artificial con las mismas condiciones del log del
08/10/2026 a las 13:48, incluyendo un día anterior en memoria y una auditoría
`no_day_context` de baja confianza.
