# CANCHERIA v0.2.4

## Corrección del respaldo automático

Esta versión corrige el error:

```text
ZIP does not support timestamps before 1980
```

Algunas sesiones de WhatsApp, perfiles migrados o archivos restaurados pueden
tener internamente una fecha como 1970 o 1601. El formato ZIP no permite fechas
anteriores a 1980 y el respaldo previo a la actualización se cancelaba.

CANCHERIA ahora limita esas fechas a `1980-01-01` solamente dentro de la copia
ZIP. Los archivos originales, la configuración y la sesión del cliente no se
modifican.

La protección se aplica a:

- actualizaciones iniciadas desde **⚙ Ajustes**;
- instalador completo de Windows;
- instalador completo de Debian;
- construcción de los paquetes de actualización.

## Instalaciones afectadas

Si la versión actualmente instalada ya muestra este error, ejecutá una vez el
instalador completo v0.2.4 sobre la instalación existente y no desinstales la
versión anterior. El instalador conserva la configuración, reservas y sesión de
WhatsApp. A partir de entonces se podrá volver a actualizar desde la GUI.

## Verificación

- Prueba automática con un archivo real fechado en Unix epoch (`1970-01-01`).
- El respaldo se crea, conserva el contenido y registra `1980-01-01` dentro del
  ZIP.
- Se verifica que la fecha del archivo original no cambie.
- Suite completa sobre la copia pública sanitizada.

```text
09FE992D000D1A43CD16A296AB6314A42ABB27F851E13F375CE51F54482948FA  InstaladorCancheria.exe
61E96F47CAA6363C9DAD68CAC514BAA2499A4865CA4C4FDF4CA12CC44FE583FE  InstaladorCancheriaLinux.run
1196FB90FE0C7952BD5EF20475BEEEC008FE42B71A462BEDDFDE37B606976AD9  CANCHERIA-update-windows.zip
CAE4BD332E692909C3D7097F4D5E6E5FFCB14B90EF4A1F69D73FA3220358EC1B  CANCHERIA-update-linux.zip
ABFDCEDED5E455CCB6E845879B8252AC6C05161C84677FFF2A62C3FFBEC134CE  DEMO-CANCHERIA-CHAT.mp4
```
