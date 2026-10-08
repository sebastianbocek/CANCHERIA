# Changelog

## 0.2.1 - 2026-10-08

- El botón **ADMINISTRACIÓN** muestra un contador rojo con la suma de pagos
  pendientes y casos que requieren atención humana.
- Las pestañas **Reservas y pagos** y **Atención humana** muestran su propio
  contador rojo para identificar inmediatamente el origen de cada alerta.
- Los contadores se actualizan automáticamente cada tres segundos y desaparecen
  únicamente cuando la tarea queda realmente resuelta.
- Si existe una sola categoría con alertas, el panel se abre directamente en
  esa pestaña para reducir pasos al administrador.

## 0.2.0 - 2026-10-08

- Se agregó **⚙ Ajustes** al panel principal con búsqueda e instalación de
  actualizaciones directamente desde las publicaciones oficiales de GitHub.
- Cada descarga exige el tamaño y el hash SHA-256 informado por GitHub y además
  verifica un manifiesto interno archivo por archivo antes de instalar.
- Un auxiliar independiente reemplaza los ejecutables después de cerrar la GUI,
  restaura automáticamente la versión anterior si ocurre un error y reinicia
  CANCHERIA mostrando el resultado.
- Los paquetes de actualización excluyen configuración, API key, reservas,
  sesión de WhatsApp, comprobantes y demás datos privados del cliente.
- Windows y Debian crean un ZIP en `Backups` antes de aplicar la actualización.

## 0.1.9 - 2026-10-07

- Las actualizaciones de Windows copian `config.py` y `legacy_config.py` a un
  área temporal antes de instalar y los restauran explícitamente al finalizar.
- Los dos archivos de configuración quedan excluidos de la desinstalación.
- Debian conserva ambos archivos antes de copiar la versión nueva y verifica
  byte por byte que hayan sido restaurados correctamente.
- La actualización continúa creando el ZIP de respaldo completo antes de tocar
  la instalación y se cancela si no puede proteger los datos del cliente.

## 0.1.8 - 2026-10-07

- La API key configurada desde la GUI vuelve a guardarse en el `config.py`
  principal y tiene prioridad sobre variables de entorno antiguas.
- El configurador normaliza y verifica la clave directamente con OpenAI antes
  de guardarla; un 401 ya no permite iniciar el agente.
- El panel principal vuelve a comprobar la credencial antes de abrir WhatsApp,
  evitando falsos casos de atención humana por errores de autenticación.
- Los instaladores de Windows y Debian respaldan y conservan `config.py` al
  actualizar, además de mantener la migración desde la configuración anterior.

## Backup fresco para clientes

- Se agregó `Crear_Backup_Fresco_CANCHERIA.exe`, un generador reutilizable de
  ZIP limpios para clientes.
- Reconstruye los ejecutables desde una copia sanitizada, ejecuta sus
  self-tests y excluye `installer`, sesiones, perfiles de WhatsApp, runtime y
  credenciales del propietario.
- Cada ZIP incluye un manifiesto SHA-256 y se guarda en `backups_clientes`.

## Unreleased

- Before every detected upgrade, `InstaladorCancheria.exe` now creates a ZIP
  backup under the installed application's `Backups` directory. It includes the client's
  configuration, operational data and WhatsApp session while excluding browser
  caches. The upgrade is aborted before file replacement if backup creation
  fails. The backup directory is preserved if CANCHERIA is uninstalled.
- The clean Windows installer is now delivered as `InstaladorCancheria.exe`.
  It installs per-user without an administrator prompt, creates Start Menu and
  optional desktop shortcuts, preserves client configuration on upgrades and
  opens the business configurator as the recommended final step.
- Added a new **Horas** tab to the desktop administration panel. It opens on
  today's date, shows every configured slot per court (green when available,
  red when occupied or blocked), and supports previous/next day navigation or
  direct `AAAA-MM-DD` entry.
- Clicking a free hour opens a prefilled manual booking; clicking an occupied
  hour edits the customer, phone, date, start time and court while preserving
  payment fields and preventing overlaps. Administrative blocks can be removed
  directly from the same grid.
- Fixed ambiguous short hours for today: when the literal reading has already
  passed but its 12-hour equivalent is still bookable, `hoy a las 11` at 22:45
  now resolves to 23:00. Explicit meridians such as `11 de la mañana` remain
  unchanged.
- Applied the same short-hour resolution inside the canonical V184/V186 fast
  path before its availability tool call; this prevents that path from freezing
  the already-past 11:00 value while 23:00 is available.
- Fixed silent customer turns caused by a blank `OPENAI_MODEL`; the runtime now
  has a safe default and the configurator rejects an empty model.
- Fixed the configurator so authorized WhatsApp recipients and email settings
  are actually persisted.
- Hardened WhatsApp unread-filter and chat-row selectors against current DOM
  variants and removed the unsafe generic `label_item` click.
- Added an integrated **ADMINISTRACIÓN** panel to `cancheria.exe` for bookings,
  payments, schedule blocks and human-handoff cases, backed by the same
  deterministic admin operations used by WhatsApp.
- Prepared open-source repository structure.
- Moved secrets and admin identifiers to environment variables.
- Isolated runtime data under `runtime/`.
- Extracted calendar and event-registration domains.
- Added modern CLI and legacy compatibility entrypoint.
- Added Agent V2 / WhatsApp public facades for incremental extraction.
- Added documentation, tests and CI.

## Desktop dual EXE

- Added standalone `configurador_cancheria.exe` Windows build.
- Added **CONFIGURACIÓN** button to `cancheria.exe`.
- The main GUI opens the standalone configurator and warns when an agent restart is required.
- Windows build and GitHub Actions now produce both executables.

### Desktop path fix
- Windows builds now emit `cancheria.exe` and `configurador_cancheria.exe` directly in the CANCHERIA root instead of `dist/`.
- Both executables can recover the project root from an old `dist/` location for backwards compatibility.
- Fixes GUI lookups for `WPSetter.py`, the legacy configurator, assets and the PDF manual.

## Build fix - 2026-10-06

- Fixed PyInstaller icon resolution when `--specpath build/spec` is used by passing an absolute `.ico` path.
- `cancheria.exe` and `configurador_cancheria.exe` remain generated directly in the CANCHERIA root.
- Added an isolated `.build-venv` for Windows builds to avoid collecting unrelated global packages such as Torch/ONNX/Pandas.
- Removed broad `--collect-all openai/playwright` flags and added explicit frozen dependency anchors for WPSetter runtime dependencies.
- Updated GitHub Actions to use the same root-output/absolute-icon strategy.

## 0.1.3 - Frozen runtime support

- Fixed `ModuleNotFoundError: sqlite3` when `cancheria.exe` launches the external `WPSetter.py` runtime.
- Fixed `ModuleNotFoundError: json` when `configurador_cancheria.exe` launches the external visual configurator.
- Added explicit PyInstaller import anchors for the standard-library modules used by dynamic legacy scripts.
- Added `--self-test` smoke tests for both Windows executables; the build aborts before packaging if the frozen runtime is incomplete.
## 0.1.4 - 2026-10-07
- Fixed frozen worker import path for external `src/cancheria` modules.
- Fixed `ModuleNotFoundError: cancheria.legacy_bridge` when pressing ENCENDER.
- `CANCHERIA_INSTALL_ROOT` now controls runtime paths in frozen mode.
- Windows self-test now validates the legacy bridge and critical domain modules.

