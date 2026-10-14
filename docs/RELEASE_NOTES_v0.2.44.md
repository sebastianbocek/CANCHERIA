# CANCHERIA v0.2.44

## Cantidad de canchas y duración

Esta versión corrige una confusión semántica observada con la consulta:

> ¿Se puede reservar 2 canchas 4 horas?

El plan anterior interpretaba el número 2 como duración y omitía las 4 horas.
Ahora el agente representa y valida ambas dimensiones de manera independiente:

- cantidad solicitada: 2 canchas;
- duración solicitada: 4 horas.

Una revisión transformer especializada asigna cada cantidad a su unidad y
entrega evidencia literal. El código sólo acepta el resultado si esa evidencia
pertenece al turno actual. Si no puede verificarlo, evita emitir una respuesta
cuantitativa potencialmente incorrecta.

La respuesta se construye después desde la configuración real: disponibilidad
de varias canchas, duraciones habilitadas, precios y políticas vigentes.

## Verificación

- Regresión automatizada del contrato incorrecto `duración=2`.
- Verificación del contrato combinado de capacidad y duración.
- Suite completa ejecutada correctamente.
