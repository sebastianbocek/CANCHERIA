# CANCHERIA v0.2.61

## Tooltip estable en Ingresos por día

- Se eliminó el ciclo de eventos que creaba y destruía repetidamente el tooltip al pasar el mouse sobre una barra azul.
- El gráfico ahora utiliza un único seguimiento de movimiento a nivel del canvas.
- Se conserva en memoria la barra activa y no se vuelve a dibujar el tooltip mientras el mouse permanezca sobre ella.
- Al salir del gráfico o cambiar de barra, el tooltip anterior se elimina de forma controlada.
- La corrección evita la saturación de eventos que podía dejar la aplicación en estado **No responde**.

## Verificación

- Se agregó una prueba de regresión con movimientos repetidos sobre la misma barra.
- La prueba confirma que se genera una única instancia del tooltip y que el estado se limpia al salir del gráfico.
