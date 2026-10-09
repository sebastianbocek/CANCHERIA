# CANCHERIA v0.2.14

Esta versión corrige la contaminación de un pedido nuevo con una reserva o seña pendiente cuyo hold ya no existe.

## Reconstrucción contextual autocorregida por IA

- Cuando el calendario confirma que el hold anterior desapareció, su estado deja de ser una fuente válida para completar el nuevo objetivo.
- La conversación y las acciones anteriores siguen disponibles para la IA, pero el hold vencido se identifica expresamente como historia descartada.
- Una primera IA reconstruye el objetivo completo con los datos conocidos, los faltantes y la procedencia de cada dato.
- Una segunda pasada de IA revisa el borrador contra el mensaje actual, la hora local, el historial JSON y los hechos operativos; puede corregir fecha, hora, deporte, operación y datos faltantes.
- La interpretación de una fecha implícita queda en la IA. No se agregó una regla fija que convierta automáticamente cualquier hora sin fecha en «hoy».
- Python conserva solamente la verificación de hechos: existencia del hold, disponibilidad real, calendario, pagos e identificadores.

La regresión reproduce el incidente del 09/10/2026 a las 00:45: con una seña antigua en memoria, `Hola tenes cancha para las 21` se reconstruye como el pedido vigente y el agente pregunta sólo el deporte faltante.

La actualización conserva la configuración, API key, reservas, torneos, inscripciones y sesión de WhatsApp.
