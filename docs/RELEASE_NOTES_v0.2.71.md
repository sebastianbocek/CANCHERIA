# CANCHERIA v0.2.71

Esta versión permite configurar grupos de **Escuelita** con varios días semanales.

## Cambios

- **Nuevo grupo** y **Editar grupo** ahora presentan un selector múltiple de días.
- Se pueden marcar combinaciones como lunes, miércoles y viernes para un mismo grupo.
- La hora y la duración elegidas se aplican a cada día seleccionado.
- Cada recurrencia bloquea realmente la cancha en el calendario operativo.
- Las clases aparecen en **Horas** y **Clases de hoy** en todos los días configurados.
- Los grupos anteriores de un solo día siguen funcionando sin migraciones manuales.
- Al editar un grupo se muestran seleccionados todos sus días actuales.
- No se permite guardar sin al menos un día.

## Verificación

- Cobertura automatizada para lunes, miércoles y viernes, persistencia de las recurrencias y bloqueo de la cancha sólo en los días correspondientes.
