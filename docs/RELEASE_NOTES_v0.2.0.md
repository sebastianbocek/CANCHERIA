# CANCHERIA v0.2.0

## Actualización directa desde la aplicación

Esta versión incorpora una sección **⚙ Ajustes** en la pantalla principal.
Desde allí se puede buscar e instalar la última versión oficial publicada en
GitHub sin descargar manualmente otro instalador.

El proceso:

1. consulta la publicación estable más reciente;
2. selecciona el paquete correcto para Windows o Debian;
3. verifica el tamaño, el SHA-256 publicado por GitHub y el manifiesto interno;
4. detiene el agente y el navegador;
5. crea un ZIP de respaldo dentro de `Backups`;
6. instala la versión mediante un auxiliar independiente;
7. restaura la versión anterior si algún archivo falla;
8. reinicia CANCHERIA y muestra el resultado.

Los paquetes de actualización nunca incluyen ni reemplazan `config.py`,
`legacy_config.py`, `runtime`, `wa_profile`, `sessions`, `Backups`,
comprobantes, torneos, bases de datos o archivos operativos del cliente.

## Primera actualización

Para obtener esta nueva función hay que instalar CANCHERIA v0.2.0 una vez con
el instalador de Windows o Debian sobre la versión existente. No hay que
desinstalar la versión anterior. Desde las próximas versiones se podrá usar
directamente **⚙ Ajustes → Actualizar versión**.

## Verificación

- Suite automatizada del proyecto.
- Simulación local de actualización preservando configuración y datos privados.
- Verificación SHA-256 del paquete completo y de cada archivo interno.

```text
31458548B8ED39AFB7737C06990F78A1317854BD711496973C8FE794C2EB692B  InstaladorCancheria.exe
748E6BA9746F92A157B816DDE108E2597094F1B9FD71E2928E4E425C4ABFFAD2  InstaladorCancheriaLinux.run
5924E7A0F446BB21016EB265D23E984134F2941085FAD36E0A67A939377973B8  CANCHERIA-update-windows.zip
C55FC0913E6B5D2082ED142A97F29AA179C97E4CDBD061EC64F6F794664DF4E4  CANCHERIA-update-linux.zip
```
