# CANCHERIA v0.2.7

Esta versión corrige el flujo de pago mixto de una reserva cuando el cliente ya
transfirió una parte de la seña y elige pagar la diferencia en efectivo.

## Pago parcial + efectivo

- `Pago el resto en efectivo` se vincula a la reserva parcial real del cliente.
- El turno queda firme sin marcar el efectivo como dinero recibido.
- Se conserva el monto transferido y se registra por separado la diferencia de
  la seña que se cobrará en el complejo.
- El saldo total del turno continúa siendo informado correctamente.

## Separación entre reservas y torneos

El agente resuelve el destino mediante el estado transaccional verificado. Si
la única obligación parcial es una reserva, no puede derivarla al flujo de
torneos. Si la única obligación parcial es una inscripción, conserva ese flujo.
Ante un estado ambiguo, no adivina.

También se eliminó la respuesta genérica `¿A qué torneo te referís?` para una
elección de efectivo que no tenga una inscripción real identificada.

## Seguridad

Se verificó que el código y los instaladores públicos no incluyan API keys
reales. Las credenciales de cada instalación siguen almacenándose en la
configuración privada creada por el configurador.

## Validación

- Reproducción artificial completa del incidente real de las 14:09.
- Verificación de la mutación de calendario y de los importes parciales.
- Pruebas de reserva parcial, torneo parcial, contexto ambiguo y bloqueo del
  fallback genérico.
- Suite completa: 92 pruebas aprobadas.
