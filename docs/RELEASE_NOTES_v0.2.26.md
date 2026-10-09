# CANCHERIA v0.2.26

Esta versión evita que el chat de servicio **WhatsApp Business** sea procesado como si fuera un cliente.

- `WhatsApp Business` está incluido en la blacklist predeterminada aun si la blacklist configurable está vacía.
- Al detectarlo, CANCHERIA sale del chat sin responderlo ni procesarlo como una reserva y vuelve al filtro **Todos**.
- La protección se aplica por identidad directa del chat y también por el nombre recuperado del contacto.

No se modificaron la lógica de reservas, los datos del negocio ni la sesión de WhatsApp.
