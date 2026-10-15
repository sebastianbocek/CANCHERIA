# CANCHERIA v0.2.48

Esta versión introduce un único `TurnIntentPlan` canónico para representar intención principal, subintenciones, entidades, herramientas requeridas y contratos concretos de respuesta.

El log de producción de `v0.2.47` demostró que el compilador encontraba cuatro objetivos, pero los agrupaba en dos acciones incapaces de producir todas las respuestas: una escritura `replace_pending_booking` y una `query_availability`. La disponibilidad no puede renderizar horarios generales ni préstamo de pelota, y una pregunta sobre políticas no autoriza una escritura.

El nuevo validador no exige una acción por subintención. Permite compartir acciones cuando es correcto —por ejemplo, una única `business_info` puede responder varios hechos— pero comprueba que cada `required_output` sea producido realmente por la capacidad ejecutora seleccionada. También separa explícitamente lecturas y escrituras para impedir que el contexto viejo transforme una consulta en una modificación.

El CANÓNICO permanece como único cerebro. El FAST PATH sólo podrá actuar como acelerador si produce exactamente el mismo contrato; no posee una ruta semántica paralela. Si tres planes canónicos resultan inválidos, CANCHERIA pide reformular el turno y no crea un handoff humano por ese fallo interno.

Las regresiones reproducen el turno con disponibilidad, horarios de atención, préstamo de pelota y la consulta sobre dos canchas durante cuatro horas; prueban además acciones compartidas válidas y el plan inválido observado realmente en `v0.2.47`.

El identificador visible en el próximo log es `2026-10-15_unified_turn_intent_plan_v241`.
