# CANCHERIA v0.2.19

## Gestión de turnos fijos desde la GUI

- Se agregó la pestaña `Turnos Fijos` inmediatamente antes de `Blacklist`.
- Permite listar, crear y quitar recurrencias semanales desde el panel de administración.
- Cada alta usa la misma memoria y operación administrativa que el comando de WhatsApp.
- La próxima fecha del turno fijo se agrega inmediatamente a la agenda compartida y aparece en `Horas`.
- La tabla indica cliente, teléfono, día semanal, hora, cancha, próxima fecha y estado en agenda.
- Si el próximo horario está ocupado, el turno fijo se guarda y la GUI informa que no pudo incorporarlo todavía.
- Quitar la recurrencia no cancela una reserva ya generada; esa reserva permanece visible y gestionable en `Horas`.
