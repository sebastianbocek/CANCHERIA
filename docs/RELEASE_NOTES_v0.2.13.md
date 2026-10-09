# CANCHERIA v0.2.13

Esta versión hace que la IA reconstruya el objetivo completo de la conversación antes de responder o ejecutar una reserva.

## Reconstrucción contextual por IA

- El Orchestrator recibe el mensaje actual, el historial JSON reciente del contacto, el estado canónico y las acciones operativas previas.
- La IA identifica qué datos pertenecen al objetivo vigente, cuáles ya fueron aportados y cuáles faltan realmente.
- No existe una secuencia programada de fecha, hora, deporte o duración.
- Las respuestas breves se interpretan dentro del objetivo conversacional completo, sin reiniciar la disponibilidad ni borrar datos anteriores.
- Cuando el objetivo queda completo, se valida la disponibilidad real, se crea el hold y se solicita el comprobante.
- Python conserva sólo las validaciones de hechos operativos; no reinterpreta el lenguaje ni completa campos por el orden de llegada.

La actualización conserva la configuración, API key, reservas, torneos, inscripciones y sesión de WhatsApp.
