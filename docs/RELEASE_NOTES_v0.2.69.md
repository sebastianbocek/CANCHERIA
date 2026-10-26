# CANCHERIA v0.2.69

Esta versión completa la edición manual de **Escuelita** con borrado seguro de alumnos y grupos.

## Cambios

- Los diálogos **Editar alumno** y **Editar grupo** incorporan el botón gris **Borrar**.
- Antes de eliminar se muestra una confirmación que explica exactamente qué datos asociados se quitarán.
- Borrar un grupo libera sus horarios recurrentes y limpia inscripciones, asistencias y cuotas, sin borrar a los alumnos.
- Borrar un alumno limpia sus relaciones propias de Escuelita.
- Las preinscripciones de un grupo eliminado se conservan como contactos pendientes, pero quedan sin grupo asignado.
- Los movimientos históricos de Caja no se eliminan aunque se borre el alumno o grupo que originó el cobro.
- Cada eliminación queda asentada en el historial interno de Escuelita.

## Verificación

- 217 pruebas automatizadas aprobadas en el árbol limpio de publicación; 1 prueba visual omitida porque Tk no estaba disponible en ese entorno.
- Cobertura automatizada de borrado transaccional, liberación de horarios, ausencia de datos huérfanos y conservación de Caja.
