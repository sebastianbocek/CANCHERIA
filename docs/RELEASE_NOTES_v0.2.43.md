# CANCHERIA v0.2.43

## Corrección del agente multiobjetivo

Esta versión corrige el caso en que el FAST PATH detectaba correctamente una
consulta de disponibilidad, pero el planificador canónico la reinterpretaba
como información general y terminaba respondiendo sólo horarios de atención,
servicios y políticas.

La integración ahora aplica un contrato de cobertura entre el descubrimiento
exhaustivo y el plan canónico. Para objetivos inequívocos de lectura, el plan
debe conservar la operación correspondiente. Si no lo hace, CANCHERIA vuelve a
planificar semánticamente ese objetivo con contexto explícito, combina las
preguntas complementarias y no permite una respuesta parcial si la obligación
sigue ausente.

El caso real reportado quedó cubierto por una prueba automatizada que exige una
única respuesta con:

- disponibilidad de canchas para hoy;
- horarios generales de atención;
- política de préstamo de pelota;
- validación de una duración no habilitada.

## Compatibilidad

- Windows 10/11.
- Debian/Ubuntu compatibles con el instalador Linux publicado.
- Actualización sobre instalaciones existentes preservando configuración,
  sesión, calendario y datos operativos.
