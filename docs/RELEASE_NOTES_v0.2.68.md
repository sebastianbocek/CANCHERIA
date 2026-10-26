# CANCHERIA v0.2.68

Esta versión mejora la operación en vivo de la pestaña **Horas** y el envío manual de promociones.

## Cambios

- Los turnos cambian automáticamente a **En curso** y **Recién terminado** sin presionar Actualizar.
- La comprobación ocurre cada tres segundos, pero la grilla sólo se redibuja cuando cambia su estado.
- El botón ahora se llama **Enviar Mensaje**.
- El mensaje se entrega desde la sesión y el perfil de WhatsApp que CANCHERIA ya tiene encendidos; no se abre otro Chrome.
- La solicitud se guarda de forma durable y el mismo ejecutor de alertas la incorpora y envía cuando el inbox está libre.
- Si CANCHERIA está apagado, el panel lo informa y no genera una solicitud que pueda confundir al operador.
- **Escuelita** incorpora **Editar seleccionado** y doble clic: permite modificar alumnos y grupos también desde las filas de clases de hoy y cuotas pendientes.
- Las ediciones conservan las validaciones de cupos, canchas y superposición de horarios, y actualizan Horas y Caja al guardar.
- Una consulta genérica como “jugar al fútbol” ya no se reduce arbitrariamente a Fútbol 5: la IA entrega todas las modalidades configuradas compatibles, como Fútbol 5 y Fútbol 7, a la herramienta de disponibilidad.
- Las consultas específicas, por ejemplo “fútbol 7”, mantienen el filtro exacto.

## Verificación

- 217 pruebas automatizadas aprobadas en el árbol limpio de publicación.
- Cobertura específica para la solicitud atómica de mensajes, la entrega desde la cola activa, edición persistente de Escuelita y alcance genérico/específico de deportes.
