# CANCHERIA v0.2.72

Esta versión amplía la agenda de **Escuelita** y corrige la finalización del agente.

## Cambios

- **Nuevo grupo** y **Editar grupo** permiten marcar varias horas, además de varios días.
- Las opciones horarias se calculan desde la franja de atención configurada en el negocio.
- Cada combinación de día y hora crea una clase recurrente real y bloquea su cancha.
- Los horarios existentes fuera de la franja actual siguen visibles al editar para evitar pérdidas.
- Se impide guardar horarios del mismo grupo que se superpongan entre sí.
- **APAGAR** verifica que el proceso haya terminado antes de informar el apagado.
- Si el cierre del árbol falla en Windows, CANCHERIA intenta una terminación directa y mantiene el proceso controlado si todavía continúa activo.

## Verificación

- Cobertura automatizada de múltiples días y horas, franja dinámica, conflictos internos y finalización confirmada del proceso.
