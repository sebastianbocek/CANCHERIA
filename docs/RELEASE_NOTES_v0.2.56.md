# CANCHERIA v0.2.56

## Confirmación manual de holds vencidos

- **Confirmar seña** y **Confirmar total** ahora pueden recuperar una reserva con estado `hold_expirado` aunque el pago original no haya sido marcado como efectivo.
- Antes de confirmar, CANCHERIA verifica de forma atómica que la cancha y todo el bloque horario continúen libres.
- Si otra reserva ya ocupó el horario, la confirmación se rechaza y el hold vencido no se modifica.
- Se conserva el método de pago previamente registrado; cuando no existe, la confirmación manual utiliza efectivo.
- La operación continúa siendo idempotente para impedir cobros o confirmaciones duplicadas.

## Verificación

- Suite automatizada completa: **192 pruebas aprobadas**.
- Se agregaron pruebas específicas para seña, pago total y conflicto de disponibilidad sobre holds vencidos.
