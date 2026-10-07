# Instalación de CANCHERIA en Debian con escritorio

Requisitos:

- Debian 12 o posterior, de 64 bits.
- Un escritorio gráfico ya instalado y una sesión iniciada con el usuario que usará CANCHERIA.
- Acceso a Internet.
- El usuario debe poder usar `sudo`.

Copiar `InstaladorCancheriaLinux.run` a la computadora Debian, abrir una terminal en esa carpeta y ejecutar:

```bash
bash InstaladorCancheriaLinux.run
```

El instalador agrega CANCHERIA al menú de aplicaciones y, cuando el escritorio lo permite, crea también un acceso directo. La aplicación queda en:

```text
~/.local/share/CANCHERIA
```

La primera vez hay que abrir **Configurar CANCHERIA**, completar los datos del negocio y después abrir **CANCHERIA** para iniciar sesión en WhatsApp mediante QR.

## Actualizaciones

Para actualizar se vuelve a ejecutar el nuevo `InstaladorCancheriaLinux.run` con el mismo usuario. Antes de reemplazar archivos, el instalador crea un ZIP automático en:

```text
~/.local/share/CANCHERIA/Backups
```

La configuración, los datos operativos y la sesión de WhatsApp se conservan.
