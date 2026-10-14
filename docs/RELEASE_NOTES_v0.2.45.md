# CANCHERIA v0.2.45

Esta versión corrige dos fallos observados en producción:

- El agente ya no fragmenta una consulta múltiple en rutas semánticas incompatibles. Una única revisión IA compila el turno completo, enumera todos los objetivos con evidencia literal y entrega el plan de acciones al executor canónico.
- Una revisión semántica incompleta no crea automáticamente un caso de atención humana cuando existe un borrador IA válido y seguro.
- El indicador rojo de Administración ahora conserva el origen de la alerta dentro del panel. Los casos humanos muestran su insignia en la pestaña **Atención humana** hasta que el operador la selecciona.

La regresión principal cubre en un solo turno: disponibilidad de fútbol para hoy, horarios generales de atención, préstamo de pelota y consulta por dos canchas durante cuatro horas.
