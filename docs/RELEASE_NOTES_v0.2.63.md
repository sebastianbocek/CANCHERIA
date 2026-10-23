# CANCHERIA v0.2.63

## Escuelita integrada

Esta versión incorpora una nueva pestaña **Escuelita** inmediatamente después de **Torneos**. Incluye alumnos y responsables, profesores, grupos, cupos, horarios recurrentes, inscripciones, asistencia, preinscripciones y cuotas con pagos parciales.

Las clases ocupan las canchas reales en la agenda y en las consultas de disponibilidad del agente. No se crean reservas ficticias. Los pagos confirmados de cuotas se integran con **Caja** mediante movimientos idempotentes con origen `Escuelita`.

## Agente de WhatsApp

Escuelita es un dominio del orquestador canónico, no un conjunto de respuestas hardcodeadas. La IA puede seleccionar dinámicamente herramientas para:

- consultar grupos, edades, categorías, días, horarios, profesores, precios y cupos;
- registrar preinscripciones;
- consultar cuotas asociadas al teléfono del responsable;
- registrar avisos de ausencia.

Un mismo turno puede combinar estas acciones con otras intenciones de CANCHERIA. Si no existe una herramienta adecuada o falta información real del negocio, el turno genera un handoff silencioso y no envía una respuesta genérica al cliente.

## Persistencia y compatibilidad

Los datos se guardan en `runtime/escuelita.db` con SQLite, transacciones, historial y control de duplicados. La actualización conserva reservas, configuración, sesión, Caja, Bar y el resto de los datos existentes.
