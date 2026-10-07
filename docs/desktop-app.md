# CANCHERIA Desktop

The Windows desktop application is a thin operator layer around the existing `WPSetter.py` runtime.

## Controls

- **ENCENDER** starts the worker with `--profile ./wa_profile`.
- **PAUSA** stops the local automation/browser process while preserving `wa_profile`.
- **CERRAR SESIÓN** stops the worker and recreates `wa_profile` empty.
- **NUEVA SESIÓN** performs the same local profile reset and immediately starts the worker so WhatsApp Web presents a new QR.
- **Abrir manual** opens the bundled owner/operator PDF.

Booking state and business runtime data live under `runtime/`; session reset intentionally does not remove that directory.

## Frozen executable design

`cancheria.exe` has two modes:

1. default: Tkinter GUI;
2. `--worker`: executes the external/open-source `WPSetter.py` tree bundled beside the executable.

Keeping the Python project beside the executable is intentional: CANCHERIA remains open source, admin configuration that still edits the compatibility config remains persistent, and users can inspect the exact code they are running.

When the legacy startup invokes `calendario.py` through `sys.executable`, the frozen dispatcher recognizes the `.py` target and executes it with the embedded Python runtime.


## Configuración desde la aplicación

La distribución Windows contiene dos binarios:

- `cancheria.exe`: panel principal del agente.
- `configurador_cancheria.exe`: configurador visual independiente.

El botón **CONFIGURACIÓN** de `cancheria.exe` abre el segundo ejecutable. En modo desarrollo abre `configurador_cancheria.py`. Si el agente está funcionando, la GUI avisa que los cambios deben cargarse reiniciando CANCHERIA.
