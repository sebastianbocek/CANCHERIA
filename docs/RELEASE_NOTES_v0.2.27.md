# CANCHERIA v0.2.27

Esta versión corrige la comprensión temporal de pedidos nuevos como **“Hola, ¿tenés cancha para las 21?”**.

- La revisión temporal con IA también se ejecuta cuando el objetivo es nuevo y todavía no existe un día histórico.
- La IA vuelve a interpretar el turno completo junto con la hora detectada, la conversación, el estado y la fecha local para decidir si el sentido natural es **hoy**.
- Cuando ya se conocen hoy y las 21:00, CANCHERIA pregunta solamente el deporte que falta.
- Se evita la salida genérica **“¿Qué día te gustaría?”** en este escenario.

No se impone un orden fijo para día, hora o deporte: los datos pueden llegar en cualquier orden y la IA reconstruye el objetivo vigente.
