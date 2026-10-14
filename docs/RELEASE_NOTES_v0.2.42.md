# CANCHERIA v0.2.42

## Agente canónico multiobjetivo

Esta versión reemplaza el flujo mutable de subintenciones por un ledger canónico de objetivos y acciones:

- El FAST PATH y su revisión semántica funcionan como fuentes complementarias de descubrimiento.
- La revisión no puede eliminar obligaciones ya detectadas; sólo puede conservarlas, dividirlas o agregar cobertura.
- Cada objetivo se interpreta con el motor canónico y se convierte en acciones verificables antes de ejecutar efectos.
- Los contratos canónicos equivalentes se deduplican sin volver a interpretar texto mediante reglas de palabras.
- La respuesta sólo se envía cuando todas las acciones y todos los objetivos tienen una respuesta comprobada.
- Una duración inválida ya no puede desplazar una consulta independiente de disponibilidad.

## Caso de regresión principal

El lote con estas cuatro obligaciones se conserva completo:

1. Consultar disponibilidad de una cancha de fútbol para hoy.
2. Informar los horarios de atención.
3. Informar si se presta pelota.
4. Validar si pueden reservarse dos canchas durante tres horas.

La política de duración puede rechazar las tres horas, pero la consulta de disponibilidad sigue ejecutándose y respondiéndose de forma independiente.

## Verificación

- 173 pruebas automatizadas aprobadas.
- 1 prueba visual omitida porque el entorno de ejecución no dispone de Tk.
- El módulo principal compila correctamente con `py_compile`.
- La prueba semántica contra la API real no se ejecutó en este checkout porque contiene una clave placeholder; no se afirma validación live de OpenAI ni WhatsApp.
