# CANCHERIA v0.2.41

## Arquitectura multiobjetivo unificada

- FAST PATH se utiliza únicamente para descubrir exhaustivamente las obligaciones del turno.
- Canonical es el único motor que interpreta, valida y ejecuta cada objetivo con contexto compartido.
- Todas las decisiones se planifican antes del primer efecto y se auditan 1:1 antes de responder.
- Si un objetivo no puede planificarse de manera segura, el turno se deriva sin respuestas parciales y sin recurrir a otro ejecutor.
- Las respuestas verificadas se combinan en un único mensaje natural de WhatsApp.
