# CANCHERIA v0.2.60

## Estadísticas completas de Caja

- **Por cancha** dejó de limitarse a tres filas en ventanas compactas y ahora muestra todas las canchas configuradas, incluso cuando todavía no registran ingresos durante el período.
- **Ingresos por día** incorpora información emergente sobre cada barra azul.
- Al colocar el mouse sobre una barra se muestra la fecha completa y la facturación total correspondiente a ese día.
- También se puede consultar una barra cuyo total sea cero.

## Verificación

- Se agregó una prueba que confirma la representación simultánea de cuatro canchas.
- Se verificó que cada barra diaria registre sus eventos de entrada y salida del mouse.
- Se comprobó el contenido del tooltip con una fecha y un importe real.
