# CANCHERIA v0.2.29

Esta versión repara la actualización parcial detectada en `v0.2.28`.

- El botón superior **Actualizar** de Administración marca efectivamente las insignias rojas como leídas y la lectura persiste después del sondeo automático.
- La actualización cierra el configurador de CANCHERIA antes de reemplazar su ejecutable.
- Antes de modificar la instalación se comprueba que todos los ejecutables puedan reemplazarse, evitando mezclar archivos de dos versiones.
- El paquete vuelve a instalar los módulos Python externos que habían quedado en `v0.2.27` aunque la ventana informara `v0.2.28`.

Los datos del negocio, la configuración, las reservas y la sesión de WhatsApp se conservan.
