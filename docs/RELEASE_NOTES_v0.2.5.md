# CANCHERIA v0.2.5

Esta versión corrige la continuidad de una reserva cuando el agente ya conoce
el día y la hora, pregunta únicamente el deporte y el cliente responde con una
palabra como `Futbol`.

## Corrección principal

- El estado canónico pendiente conserva día, hora, duración e intención de crear la reserva.
- Un borrador viejo del puente legado ya no puede reemplazar ese slot reciente.
- La respuesta al último dato faltante continúa como `create_booking`: consulta el slot exacto, crea el hold y solicita el comprobante de la seña.
- Si el cliente escribe una fecha u hora nuevas de forma explícita, esos datos nuevos mantienen prioridad y no se reutiliza el slot anterior.

## Validación

Se agregó una prueba artificial del diálogo:

1. `Hola tenes cancha para las 4`
2. El agente pregunta el deporte.
3. `Futbol`
4. El agente consulta hoy a las 16:00, crea el hold y pide el comprobante.

También se verifica que un draft legado anterior (`Miércoles 07/10 18:00`) no
reemplace el slot canónico nuevo (`Jueves 08/10 16:00`).

## Actualización

Puede actualizarse desde la rueda de ajustes de CANCHERIA o instalando esta
versión encima de la anterior. La configuración y los datos persistentes se
conservan durante la actualización.
