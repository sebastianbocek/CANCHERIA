# CANCHERIA v0.2.12

Esta versión corrige la reconstrucción contextual de reservas cuando existe memoria histórica o un hold anterior vencido.

## Contexto conversacional completo

- El Orchestrator recibe el historial JSON reciente, la última decisión, la pregunta pendiente y el estado operativo verificado.
- Una respuesta breve completa sólo el dato contestado y conserva los demás datos aportados en mensajes anteriores.
- Los holds vencidos dejan de ser operaciones activas, sin contaminar el pedido nuevo del cliente.
- Una consulta con día y hora exactos avanza como objetivo de reserva: si falta el deporte, el agente pregunta únicamente ese dato.

## Caso corregido

Ante `Hola tenes cancha para las 21`, el agente toma la fecha operativa de hoy y responde:

`¿Qué querés reservar: Futbol 5, Tenis o Pádel?`

Si un estado de una versión anterior ya había preguntado el día y el cliente responde `Hoy`, CANCHERIA conserva `21:00`, pregunta solamente el deporte y continúa con el hold cuando lo recibe.

La actualización conserva la configuración, API key, reservas, torneos, inscripciones y sesión de WhatsApp.
