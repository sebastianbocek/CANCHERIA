# CANCHERIA v0.2.15

Esta versión corrige el caso en que el cliente brindaba una fecha contextual y una hora exacta, pero el agente mostraba toda la disponibilidad del día y volvía a preguntar la hora.

## Revisión IA para todo objetivo de reserva

- La reconstrucción en dos pasadas de IA ahora también se utiliza en pedidos nuevos, aunque no exista un hold anterior.
- La primera interpretación se entrega a una segunda IA como borrador revisable, no como una decisión congelada.
- La segunda revisión vuelve a leer el mensaje actual, el historial JSON, el estado canónico, la hora local y los hechos operativos.
- La IA decide el objetivo pragmático, conserva todos los datos ya conocidos e informa exclusivamente los datos que siguen faltando.
- Python no convierte consultas en reservas ni completa campos mediante reglas de orden.

## Presentación correcta de una hora exacta

- La respuesta de disponibilidad respeta el alcance exacto validado por el calendario.
- Si la herramienta devuelve 21:00 junto con la grilla completa del día, se presenta 21:00 y no la lista de todos los horarios.
- El agente no vuelve a preguntar la hora y puede pedir únicamente el deporte faltante.

La regresión reproduce el incidente del 09/10/2026 a las 05:32 con `Hola tenes cancha para las 21`.

La actualización conserva la configuración, API key, reservas, torneos, inscripciones y sesión de WhatsApp.
