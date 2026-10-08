# CANCHERIA v0.2.2

## Corrección del actualizador de Windows

Esta versión corrige el error:

```text
SystemError: <built-in function kill> returned a result with an exception set
```

El problema ocurría cuando el auxiliar comprobaba si la GUI anterior ya había
terminado mediante `os.kill(pid, 0)`. En algunos ejecutables congelados de
Windows, el cierre del proceso podía producir una condición de carrera interna.

El auxiliar ahora abre un handle nativo del proceso y espera su finalización con
la API de Windows. Además, las versiones siguientes utilizarán primero el
auxiliar nuevo y verificado que venga dentro del paquete descargado.

## Paso único para versiones anteriores

Como el fallo se encuentra dentro del auxiliar ya instalado, una versión 0.2.0
o 0.2.1 afectada no puede reemplazar por sí misma ese archivo. En ese caso:

1. cerrá CANCHERIA;
2. ejecutá `InstaladorCancheria.exe` v0.2.2 sobre la instalación existente;
3. no desinstales la versión anterior.

El instalador conserva la configuración, la API key, las reservas y la sesión
de WhatsApp. Este paso es necesario una sola vez; las próximas versiones podrán
instalarse nuevamente desde **⚙ Ajustes**.

## Verificación

- Prueba nativa de espera con un proceso vivo y otro finalizado en Windows.
- Simulación completa del auxiliar compilado después del cierre de la GUI.
- Verificación de rollback y conservación de datos privados.
- Suite automatizada completa sobre la copia pública sanitizada.

```text
DA701988D93D6F0F666BD5EFC7423A08245DA23FBABDA44C8F1BB52922B44424  InstaladorCancheria.exe
971B7F9060339B5C1D42E34F1D8F0F921EA0901817CCB0D769167579D4E1687C  InstaladorCancheriaLinux.run
DEE5C0B84B4467A5FE75EE4019A9BBC2E2C1A4440CFE74707CA46F44854CEC54  CANCHERIA-update-windows.zip
2804EB702CDB2B5FA8269FD37ACFBD99092ADE5AA216798E5D21BA3B09C7CDD8  CANCHERIA-update-linux.zip
```
