# CANCHERIA v0.2.68

Esta versión mejora la operación en vivo de la pestaña **Horas** y el envío manual de promociones.

## Cambios

- Los turnos cambian automáticamente a **En curso** y **Recién terminado** sin presionar Actualizar.
- La comprobación ocurre cada tres segundos, pero la grilla sólo se redibuja cuando cambia su estado.
- El botón ahora se llama **Enviar Mensaje**.
- El mensaje se entrega desde la sesión y el perfil de WhatsApp que CANCHERIA ya tiene encendidos; no se abre otro Chrome.
- La solicitud se guarda de forma durable y el mismo ejecutor de alertas la incorpora y envía cuando el inbox está libre.
- Si CANCHERIA está apagado, el panel lo informa y no genera una solicitud que pueda confundir al operador.

## Verificación

- 214 pruebas automatizadas aprobadas.
- Cobertura específica para la solicitud atómica de mensajes y el contrato de entrega desde la cola activa.
