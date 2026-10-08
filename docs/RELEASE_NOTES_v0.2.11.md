# CANCHERIA v0.2.11

Esta versión corrige la detección automática de nuevas actualizaciones en la pantalla principal.

## Notificación automática

- La primera comprobación comienza apenas se muestra CANCHERIA.
- Si la conexión falla o GitHub todavía informa la versión anterior, CANCHERIA vuelve a consultar automáticamente durante el arranque.
- Las consultas solicitan información actualizada y evitan utilizar respuestas HTTP cacheadas.
- Cuando existe una versión nueva, la insignia roja `1` aparece sobre **ACTUALIZACIÓN** sin abrir esa ventana.
- Después de los intentos iniciales se conserva la comprobación periódica cada seis horas.

La actualización conserva la configuración, API key, reservas, torneos, inscripciones y sesión de WhatsApp.
