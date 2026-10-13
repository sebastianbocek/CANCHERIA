# CANCHERIA v0.2.39

## Restauración del FAST PATH multi-intención

- El router exhaustivo vuelve a ejecutarse antes del Orchestrator canónico cuando el turno contiene varias peticiones.
- Cada solicitud independiente se procesa sin pérdidas y todas las respuestas se entregan en un único mensaje de WhatsApp.
- Corrige específicamente consultas que combinan disponibilidad, horarios generales de atención y préstamo de equipamiento.
- Mantiene el camino canónico moderno para los mensajes que contienen una sola intención.
