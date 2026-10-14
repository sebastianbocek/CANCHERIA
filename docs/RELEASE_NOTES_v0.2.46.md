# CANCHERIA v0.2.46

Esta versión corrige la pérdida de subintenciones que todavía podía ocurrir en `v0.2.45`.

La causa era una condición circular: el compilador semántico del turno completo sólo se ejecutaba cuando el primer borrador ya contenía varias acciones o una consulta cuantitativa. Si ese borrador reducía el mensaje a una única consulta de disponibilidad, la auditoría que debía recuperar las demás peticiones nunca llegaba a ejecutarse.

Desde esta versión, todo turno real atraviesa la auditoría semántica integral. El compilador recibe el texto físico completo, enumera cada objetivo con evidencia literal, vincula las acciones canónicas y valida cobertura antes de ejecutar. Si la auditoría no está disponible, se conserva el borrador IA previamente validado sin crear un handoff humano por un fallo técnico.

La regresión principal reproduce el caso real completo y obliga a conservar cuatro respuestas: disponibilidad de fútbol para hoy, horarios de atención, préstamo de pelota y la política conjunta de dos canchas durante cuatro horas.
