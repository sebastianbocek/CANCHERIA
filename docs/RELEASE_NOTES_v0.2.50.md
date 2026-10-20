# CANCHERIA v0.2.50

## FAST PATH dinámico + CANÓNICO multiobjetivo

El FAST PATH vuelve a ser el descubridor exhaustivo del turno: identifica una o
varias intenciones y las entrega como objetivos independientes. Cada objetivo se
interpreta y ejecuta con el CANÓNICO, usando el contexto conversacional y las
mismas validaciones de negocio.

El contrato no está limitado a disponibilidad. Se aplica dinámicamente a
reservas, pagos parciales o en efectivo, comprobantes, torneos, información del
negocio y handoff explícito. Las respuestas parciales se combinan en un solo
mensaje únicamente cuando la auditoría confirma que todos los objetivos fueron
ejecutados y respondidos.

Cada acción adicional debe estar respaldada por evidencia literal del fragmento
del usuario. Esto evita que una disponibilidad válida termine en handoff porque
el orquestador agregó una consulta `business_info` que nadie hizo.

## Alertas administrativas

Abrir Administración ya no marca todas las notificaciones como leídas. El
indicador rojo permanece visible en la pestaña que originó la alerta —por
ejemplo, `Atención humana`— hasta que el operador abre explícitamente esa
sección.

## Verificación

- Regresión del mensaje real “hola tenes cancha para hoy”.
- Verificación de que una y múltiples intenciones recorren el mismo ledger.
- Verificación de cobertura completa y descarte de acciones sin evidencia.
- Verificación de persistencia del badge hasta abrir su pestaña de origen.
