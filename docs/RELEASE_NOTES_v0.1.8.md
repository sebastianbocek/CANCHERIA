# CANCHERIA v0.1.8

Actualización de seguridad y diagnóstico de credenciales para Windows y Debian.

## Cambios

- El configurador limpia comillas y espacios accidentales al pegar una API key.
- La API key vuelve a guardarse en el `config.py` operativo, como en el sistema original.
- La API key se verifica directamente con OpenAI antes de guardar.
- Una clave rechazada, una cuenta restringida o un problema de conexión muestran mensajes distintos y claros.
- El botón **ENCENDER** vuelve a verificar la clave antes de iniciar WhatsApp.
- Una credencial inválida ya no deja que el agente arranque para luego crear un falso caso de atención humana.
- La clave nunca se incluye en mensajes de diagnóstico ni en los archivos públicos.
- Se mantienen el respaldo automático y la conservación de datos al actualizar.

## Descargas

- `InstaladorCancheria.exe`: Windows 10/11.
- `InstaladorCancheriaLinux.run`: Debian 12 o posterior con escritorio gráfico.
- `DEMO-CANCHERIA-CHAT.mp4`: demostración de una interacción básica.
- `SHA256SUMS.txt`: hashes para comprobar las descargas.

## Actualización

Ejecutá el instalador nuevo sobre la instalación existente. Antes de reemplazar
archivos, CANCHERIA crea un ZIP en la carpeta `Backups` de la instalación y
conserva la configuración y los datos del cliente.

Después de actualizar, abrí **Configuración**, pegá una API key nueva y válida,
y guardá. La clave que haya sido compartida públicamente debe revocarse.

## SHA-256

```text
A5001D3419909BCF45745CB0AAF99BA37DC86CD2067E7868CAF1FCE24C856841  InstaladorCancheria.exe
A73FF225CDC9D8DD39CFCDC57864D5E9F1218CB3E13CBC35CC5B0441E4345FF0  InstaladorCancheriaLinux.run
```
