# CANCHERIA v0.1.9

Actualización enfocada en conservar de forma obligatoria toda la configuración
del cliente al instalar una versión nueva.

## Corrección principal

- Windows guarda temporalmente el `config.py` operativo y el
  `src/cancheria/config/legacy_config.py` completo antes de copiar el programa.
- Al terminar la actualización, Windows restaura explícitamente ambos archivos;
  ya no depende solamente de que el instalador decida no reemplazarlos.
- Los dos archivos quedan marcados para no ser eliminados por el desinstalador.
- Debian conserva ambos archivos antes de copiar la versión nueva, los restaura
  después y verifica que el contenido restaurado sea idéntico al original.
- Continúa generándose un ZIP en `Backups` antes de actualizar. Si el respaldo o
  la preservación de la configuración falla, la actualización se cancela.

Esto conserva, entre otros datos:

- Nombre del negocio y nombre del agente IA.
- API key de OpenAI.
- Dirección, alias de pago y administradores autorizados.
- Canchas, deportes, precios y duraciones.
- Días y horarios de atención.
- Señas, quinchos, recordatorios y demás preferencias del configurador.

## Descargas

- `InstaladorCancheria.exe`: Windows 10/11.
- `InstaladorCancheriaLinux.run`: Debian 12 o posterior con escritorio gráfico.
- `SHA256SUMS.txt`: hashes de integridad.

## Actualización

No desinstales la versión anterior. Cerrá CANCHERIA y ejecutá directamente el
instalador v0.1.9 sobre la instalación existente.

## SHA-256

```text
3198917207453619A5B730A991ADA651A80DEC81CF3E40A411233C9775C147DD  InstaladorCancheria.exe
6680100944E98FD6A6FE7500A53BE9F1608E7D9050DFDB8A9ED1BA1DADD04816  InstaladorCancheriaLinux.run
```
