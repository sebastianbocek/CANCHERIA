# CANCHERIA v0.2.34

## Finalización automática de turnos

- Las reservas dejan de figurar como activas cuando termina el bloque completo contratado.
- El cálculo usa la zona horaria configurada y respeta la duración del turno.
- Los turnos finalizados pasan al historial sin perder pagos, saldos ni datos de la reserva.
- El dashboard excluye defensivamente los turnos vencidos y cuenta cada reserva de varias horas una sola vez.
- `Confirmar total` continúa siendo una acción financiera: una reserva pagada sigue operativamente activa hasta que termina su horario.
- La columna de pago muestra `total pagado` cuando el saldo confirmado es cero.
