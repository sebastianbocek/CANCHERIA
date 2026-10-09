# CANCHERIA v0.2.16

Esta versión mejora la detección visible de nuevas actualizaciones en la interfaz de escritorio.

## Insignia de actualización durante el uso normal

- Cualquier clic en la ventana principal puede iniciar una comprobación silenciosa de GitHub.
- También se incluyen los botones, pestañas y controles internos del panel de administración.
- La insignia roja aparece sin tener que abrir primero `ACTUALIZACIÓN`.
- Un límite de diez segundos evita múltiples consultas causadas por clics consecutivos.
- Si la comprobación inicial todavía está trabajando, la interacción queda registrada y provoca otra consulta apenas termina.
- La comprobación periódica de seis horas y los reintentos del inicio continúan funcionando.

La actualización conserva la configuración, API key, reservas, torneos, inscripciones y sesión de WhatsApp.
