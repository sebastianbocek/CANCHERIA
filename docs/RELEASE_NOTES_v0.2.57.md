# CANCHERIA v0.2.57

## Borrado de reservas desde Administración

- Se agregó el botón gris **🗑 Borrar** junto a **Cancelar** en la pestaña **Reservas y pagos**.
- Permite borrar una reserva activa, cancelada o finalizada, incluyendo las visibles mediante **Ver reservas pasadas**.
- La eliminación utiliza el ID lógico y borra todos los bloques horarios pertenecientes a la misma reserva.
- Antes de ejecutar se muestra una confirmación explícita indicando que la acción es irreversible.
- Los movimientos financieros ya asentados en **Caja** no se eliminan, preservando la auditoría contable.
- Si la reserva ya no existe, el sistema informa el problema sin modificar los archivos.

## Verificación

- Suite automatizada: **194 pruebas aprobadas**.
- La prueba visual dependiente de Tk puede omitirse automáticamente en entornos sin pantalla gráfica.
