# CANCHERIA v0.2.1

## Alertas visibles para el administrador

La pantalla principal ahora muestra un contador rojo sobre el botón
**ADMINISTRACIÓN** cuando existe una tarea pendiente. El total combina:

- reservas con seña o saldo pendiente;
- casos derivados a atención humana que todavía no fueron resueltos.

Dentro del panel, cada origen muestra su propio contador rojo en la pestaña
correspondiente. Si solamente existe un tipo de alerta, CANCHERIA abre
directamente esa pestaña.

Los contadores se actualizan automáticamente cada tres segundos. Consultar la
alerta no la elimina: desaparece únicamente al confirmar o liberar el pago, o
al marcar el caso humano como resuelto.

## Actualización

Quienes ya tienen CANCHERIA v0.2.0 pueden instalar esta versión desde
**⚙ Ajustes → Buscar actualizaciones → Actualizar versión**. El actualizador
crea el respaldo habitual y conserva la configuración, la API key, las
reservas y la sesión de WhatsApp.

## Verificación

- Pruebas unitarias del cálculo de alertas.
- Prueba de interfaz con apertura automática de la única pestaña notificada.
- Suite automatizada completa sobre la copia pública sanitizada.
- Prueba de actualización desde v0.2.0 conservando datos privados.

```text
D606888BA7C613554C69676F3B8A96ECA778BDF6B6695FB15938AE4D935A740B  InstaladorCancheria.exe
70BEEC528E0C4508366C6A5CAFAE57ED77073B5BB5A97D3D6A3A8CBA8837C420  InstaladorCancheriaLinux.run
9140965D20D16471E4AD7814357C5B2D0E5C9520303C821AF8DE2CD42A580011  CANCHERIA-update-windows.zip
71DC1ED94618D63B4AD8D100B9964AF2C2D2EE59F1933E4BADF73502D617E9D7  CANCHERIA-update-linux.zip
```
