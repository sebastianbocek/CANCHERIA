# CANCHERIA v0.2.58

## Limpieza de comprobantes desde Administración

- Se agregó **🗑 Borrar comprobantes JSON** junto a **Abrir configuración** en la pestaña **Comandos y configuración**.
- La acción reutiliza el mismo mantenimiento compartido por el agente y elimina `used_payment_receipts.json` y su archivo temporal.
- Antes del borrado se muestra una confirmación explícita e irreversible.
- La confirmación advierte que comprobantes anteriores podrán volver a ser evaluados después del reinicio del registro.
- No se eliminan reservas, pagos contabilizados ni movimientos de **Caja**.
- Los errores de acceso o archivos bloqueados se muestran en la interfaz sin ocultarlos.

## Verificación

- Se agregaron pruebas automatizadas para el éxito y el error del borrado desde el servicio de Administración.
- Se verificó el contrato visual del nuevo botón y su callback.
