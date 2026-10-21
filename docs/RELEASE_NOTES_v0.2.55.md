# CANCHERIA v0.2.55

## Reservas y pagos

- Los encabezados **Fecha** y **Hora** ahora son interactivos.
- Cada clic alterna el orden ascendente y descendente y muestra una flecha `▲` o `▼`.
- El orden de Fecha usa fechas reales, no el texto del día de la semana; por eso el turno cronológicamente más próximo aparece primero por defecto.
- El orden de Hora compara la hora real y permite verla de menor a mayor o de mayor a menor.
- Las reservas canceladas dejan de ocupar la vista prioritaria.
- Al activar **Ver reservas pasadas**, las canceladas vuelven a mostrarse como registros históricos de sólo lectura.
- Los registros cancelados no se eliminan y conservan su información administrativa.

## Pruebas

- La suite automatizada completa fue aprobada; una prueba visual dependiente de Tk se omite cuando ese entorno gráfico no está disponible.
