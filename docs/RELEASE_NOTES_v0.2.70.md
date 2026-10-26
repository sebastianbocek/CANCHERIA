# CANCHERIA v0.2.70

Esta versión corrige el envío de promociones desde clases de **Escuelita** y permite editar turnos que ya están en curso.

## Cambios

- Las clases de Escuelita ya no exponen ni intentan enviar mensajes al identificador interno `SCHOOL:...`.
- CANCHERIA obtiene los teléfonos reales de los responsables de alumnos con inscripción activa en el grupo.
- Los teléfonos repetidos se deduplican y, si hay varios responsables, el mensaje se encola individualmente para cada uno mediante la sesión activa de WhatsApp.
- El diálogo indica cuántos responsables recibirán la promoción.
- Los turnos en curso y recién terminados incorporan **Editar turno**.
- En una reserva común se abre el editor de fecha, hora, cancha, nombre y teléfono.
- En una clase de Escuelita se abre el editor del grupo, desde donde se pueden modificar cancha, horario y datos del grupo.
- Es posible corregir el nombre o teléfono de una reserva en curso sin que la hora ya iniciada bloquee el guardado.

## Verificación

- 221 pruebas automatizadas aprobadas; 1 prueba visual omitida porque Tk no estaba disponible en el entorno.
- Cobertura específica para contactos reales de Escuelita, deduplicación, cola múltiple y edición de una reserva en curso.
