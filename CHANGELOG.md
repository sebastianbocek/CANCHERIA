# Changelog

## 0.2.26 - 2026-10-09

- Incorpora `WhatsApp Business` a la blacklist predeterminada, incluso cuando el archivo de blacklist del negocio está vacío.
- Si ese contacto abre un chat pendiente, CANCHERIA no responde ni procesa la conversación como una reserva: sale del chat y vuelve al filtro `Todos`.
- Mantiene la protección tanto en la detección temprana por identidad del chat como en la validación posterior por nombre del contacto.

## 0.2.25 - 2026-10-09

- Compacta exclusivamente la pestaña `Horas` para recuperar seis horarios completos visibles simultáneamente en el tamaño habitual del panel.
- Reduce de forma proporcionada márgenes, controles, píldoras, encabezados y alto de las filas sin perder el diseño moderno de `v0.2.24`.
- Mantiene intactos la disponibilidad real, los callbacks de la grilla, el calendario, el menú contextual y los desplazamientos vertical y horizontal.

## 0.2.24 - 2026-10-09

- Rediseña exclusivamente la pestaña `Horas` con un contenedor moderno, controles de fecha redondeados y navegación más clara.
- Convierte la leyenda de disponibilidad en indicadores tipo píldora y agrega un resumen dinámico de fecha, horarios y canchas.
- Moderniza la grilla con encabezados suaves, celdas redondeadas, degradado verde y mayor separación visual.
- Conserva la selección de calendario, los callbacks de cada celda, el menú contextual de deportes y los desplazamientos horizontal y vertical.
- Adapta la distribución a ventanas angostas sin ocultar el botón `Ver horarios` ni los datos del resumen.
- Elimina las consultas automáticas de actualización al iniciar y por temporizador; la comprobación silenciosa se activa únicamente mediante una interacción del operador.
- Agrupa los clics durante quince minutos para evitar agotar el límite anónimo de GitHub, manteniendo disponible la búsqueda manual inmediata.

## 0.2.23 - 2026-10-09

- La pestaña `Torneos` reparte dinámicamente el alto entre torneos e inscripciones para mantener visibles ambas tablas y todas las acciones.
- La agenda de `Horas` admite desplazamiento vertical con la rueda del mouse sobre cualquier celda, botón o superficie de la grilla.
- `Shift` + rueda desplaza horizontalmente la agenda cuando existen más canchas que ancho disponible.

## 0.2.22 - 2026-10-09

- La ventana del panel de administración usa explícitamente el icono oficial de CANCHERIA en lugar del icono predeterminado de Tkinter.
- Los diálogos secundarios abiertos desde Administración heredan también el icono oficial.

## 0.2.21 - 2026-10-09

- Rediseño visual completo de la ventana principal con cabecera de marca, barra de estado real, botones redondeados con iconos locales y distribución adaptable.
- Consola de actividad modernizada con scrollbar, marcas de tiempo visuales y colores por severidad sin alterar los mensajes originales.
- Perfil activo mostrado dinámicamente y estados Apagado, Encendido, Pausado y Error vinculados al funcionamiento real.
- Nuevo recurso optimizado del logotipo oficial para conservar nitidez y proporción tanto en Python como en el ejecutable empaquetado.
- Rediseño visual completo del panel de administración con la identidad moderna de CANCHERIA.
- Nueva barra personalizada para las ocho pestañas, con iconos, selección azul, hover y desplazamiento horizontal automático en ventanas angostas.
- Encabezado, tarjetas estadísticas y botones de operación modernizados sin alterar sus datos ni callbacks.
- Tablas con mayor altura de fila, encabezados coherentes, selección visible y scrollbars en todos los listados extensos.
- Distribución adaptable validada desde 940×620, incluida la sección de inscripciones de torneos.

## 0.2.20 - 2026-10-09

- `ENCENDER` ya no queda bloqueado por una API key vacía, inválida o temporalmente imposible de verificar: WhatsApp y las alertas operativas arrancan igualmente.
- La verificación de OpenAI ahora se ejecuta en segundo plano y su resultado se informa en Actividad sin cerrar ni impedir el agente.
- El antiguo botón `PAUSA` ahora se llama `APAGAR` y detiene completamente CANCHERIA conservando la sesión de WhatsApp.
- Nuevo botón `PAUSAR IA` / `REANUDAR IA`: detiene y restablece sólo las respuestas automáticas mientras WhatsApp permanece abierto.
- El estado de pausa queda sincronizado con los comandos de administrador de WhatsApp y se conserva durante actualizaciones.

## 0.2.19 - 2026-10-09

- Agrega la pestaña `Turnos Fijos` antes de `Blacklist` en el panel de administración.
- Permite listar, crear y quitar turnos semanales recurrentes con las mismas operaciones usadas por WhatsApp.
- Al crear un turno fijo, incorpora inmediatamente la próxima fecha disponible a la agenda compartida de `Horas`.
- Muestra para cada turno su próxima fecha y si ya está en agenda, está pendiente o el horario se encuentra ocupado.
- Al quitar una recurrencia conserva la reserva próxima ya generada, evitando cancelaciones accidentales.

## 0.2.18 - 2026-10-09

- Agrega la pestaña `Blacklist` al panel de administración, ubicada antes de `Comandos y configuración`.
- Permite listar, bloquear y desbloquear teléfonos o nombres de contacto desde la GUI.
- Comparte la misma normalización, protección de administradores y archivo de datos que los comandos administrativos de WhatsApp.
- Actualiza automáticamente la tabla mientras la pestaña está abierta para reflejar cambios realizados desde WhatsApp.

## 0.2.17 - 2026-10-09

- Agrega el selector visual de calendario al campo `Fecha` de la pestaña `Operación`.
- Permite abrirlo desde la etiqueta `Fecha 📅`, con doble clic sobre el campo o mediante el botón de calendario.
- Reutiliza el mismo componente y formato ISO que las pestañas `Horas` y `Torneos`.
- Mantiene intactas las acciones de bloqueo y desbloqueo de una cancha o de toda la agenda.

## 0.2.16 - 2026-10-09

- Comprueba silenciosamente si existe una versión nueva cuando el operador interactúa con cualquier control de la aplicación.
- El enlace global cubre la ventana principal y todas las pestañas y botones del panel de administración.
- Actualiza la insignia roja sin exigir que el usuario abra primero el apartado `ACTUALIZACIÓN`.
- Limita las consultas por interacción a una cada diez segundos para evitar solicitudes repetidas a GitHub.
- Si el usuario hace clic mientras la comprobación inicial sigue en curso, deja una nueva comprobación en cola y la ejecuta al finalizar.

## 0.2.15 - 2026-10-09

- Extiende la revisión semántica en dos pasadas de IA a todos los objetivos de reserva, incluso cuando el contacto no tiene un hold anterior.
- La segunda IA recibe el primer borrador como hipótesis y reconstruye operación, datos conocidos y faltantes antes de ejecutar tools.
- Evita que una consulta con fecha y hora exactas se degrade a disponibilidad general o vuelva a preguntar la hora.
- Cuando la tool devuelve simultáneamente el slot consultado y la agenda completa, presenta primero el resultado exacto y pregunta únicamente la dimensión todavía faltante.
- Agrega regresiones del incidente real `Hola tenes cancha para las 21` en un contacto sin estado previo y del renderer con slot exacto más grilla diaria.

## 0.2.14 - 2026-10-09

- Separa por completo un hold vencido del objetivo conversacional vigente antes de volver a interpretar el mensaje.
- Conserva el estado anterior únicamente como contexto histórico descartado, sin permitir que aporte fecha, hora, deporte ni operación al nuevo objetivo.
- Agrega una segunda pasada de IA que audita y corrige la reconstrucción completa antes de responder o ejecutar una reserva.
- Permite que la IA infiera una fecha implícita desde el lenguaje, la hora actual y la conversación, con procedencia explícita, sin una regla Python de «hora sin fecha = hoy».
- Evita que las capas posteriores vuelvan a insertar o purgar la fecha de una reserva vieja después de que la IA reconstruyó el nuevo pedido.
- Añade una regresión artificial exacta del incidente de las 00:45 con una seña pendiente histórica y un hold inexistente.

## 0.2.13 - 2026-10-09

- Centraliza en la IA la reconstrucción del objetivo vigente usando el turno actual, el historial JSON, el estado canónico y las acciones operativas.
- Elimina del camino activo los parches Python que promovían operaciones o completaban día, hora y deporte según el campo pendiente.
- Incorpora `goal_reconstruction` al contrato del Orchestrator para declarar datos conocidos, faltantes y si el objetivo está listo para ejecutarse.
- Conserva validaciones deterministas únicamente para hechos operativos: disponibilidad real, calendario, pagos, IDs y procedencia verificable.
- Agrega regresiones que comprueban la reconstrucción por IA cuando distintos datos llegan en mensajes separados, sin codificar una secuencia de campos.

## 0.2.12 - 2026-10-09

- Reconstruye el objetivo de reserva con IA usando el turno actual, el historial JSON del contacto, la última decisión y las acciones operativas persistidas.
- Impide que una respuesta elíptica como `Hoy` borre una hora exacta ya aportada en el mensaje anterior.
- Descarta el hold vencido como objeto transaccional, pero conserva el nuevo pedido autosuficiente y lo vuelve a arbitrar con el contexto completo.
- Interpreta una consulta de slot exacto como objetivo accionable: si sólo falta el deporte, pregunta únicamente el deporte y luego continúa con el hold y el comprobante.
- Evita la disponibilidad general y la pregunta redundante `¿Qué día te gustaría?` en la secuencia `cancha para las 21` → `Hoy`.
- Agrega regresiones artificiales del incidente real de las 19:51 y de compatibilidad con estados pendientes creados por versiones anteriores.

## 0.2.11 - 2026-10-08

- Inicia la comprobación automática de actualizaciones apenas se dibuja la ventana principal.
- Repite la consulta durante el arranque cuando GitHub falla transitoriamente o todavía devuelve la versión anterior.
- Solicita la última release sin usar una respuesta HTTP cacheada.
- Mantiene la comprobación periódica cada seis horas después de completar los intentos iniciales.
- La insignia roja aparece sin abrir manualmente la ventana de Actualización.

## 0.2.10 - 2026-10-08

- Agrega un calendario visual al selector de fecha de la pestaña `Horas`.
- Agrega el mismo calendario al crear o editar la fecha de un torneo.
- Oculta las franjas horarias que ya pasaron para que la agenda de hoy empiece en el próximo horario útil.
- Muestra junto a cada cancha el ícono y el deporte definidos en `COURTS`.
- Permite cambiar el deporte de una cancha con clic derecho sobre su encabezado.
- Unifica el mapeo de íconos entre la GUI y las respuestas de disponibilidad de WhatsApp.
- Los cambios de deporte se guardan mediante la misma configuración con recarga dinámica que usa el administrador de WhatsApp.

## 0.2.9 - 2026-10-08

- Agrega la pestaña `Torneos` junto a `Atención humana` en el panel de administración.
- Permite crear, editar y borrar torneos desde la GUI con fecha, inscripción, premio, capacidad y alias de pago.
- Permite crear y editar inscripciones, confirmar seña o pago total y liberar/cancelar cupos.
- Muestra confirmados, holds y lugares disponibles por torneo, además de pagos y saldos por inscripción.
- Conserva el ID administrativo de una inscripción después de editarla o registrar pagos.
- La pestaña `Torneos` recibe una insignia roja cuando existen inscripciones pendientes de pago.
- `Comandos y configuración` ahora utiliza el catálogo completo de ayuda del administrador de WhatsApp, ordenado visualmente y con desplazamiento.

## 0.2.8 - 2026-10-08

- Renombra el acceso principal `AJUSTES` como `ACTUALIZACIÓN` para que su función sea evidente.
- Comprueba automáticamente GitHub al iniciar y cada seis horas, sin interrumpir al operador si no hay conexión.
- Muestra una insignia roja sobre `ACTUALIZACIÓN` cuando existe una versión nueva.
- Conserva una actualización ya detectada si una comprobación posterior falla temporalmente.
- Agrega un apartado visible de autoría para Sebastián Bocek de AIBROTHERS con enlaces a GitHub, email y WhatsApp.

## 0.2.7 - 2026-10-08

- Corrige el enrutamiento contextual de `Pago el resto en efectivo` después de una transferencia parcial de la seña.
- La elección de efectivo se vincula a la única obligación parcial real —reserva o inscripción de torneo— en vez de confiar en una etiqueta de dominio equivocada del modelo.
- Una reserva con seña parcial queda firme, conserva el dinero transferido y registra únicamente la diferencia como efectivo pendiente.
- Una decisión de efectivo para torneo sin una inscripción real identificada ya no responde con el fallback genérico `¿A qué torneo te referís?`.
- El contrato canónico de pago presencial queda congelado y autoriza explícitamente `payment_method=cash` antes de ejecutar la tool.
- Verifica que el código y los instaladores públicos no incluyan API keys reales.

## 0.2.6 - 2026-10-08

- Elimina la pregunta redundante `¿Qué día te gustaría?` cuando el usuario da una hora exacta sin fecha: el fast path usa hoy.
- La regla también funciona si existe un día viejo en memoria y el adjudicador temporal clasifica correctamente `no_day_context` con confianza baja.
- Las preguntas con deportes alternativos ahora usan `o`: `Futbol 5, Tenis o Pádel`.
- Añade regresiones del incidente real `Hola tenes cancha para las 7` de las 13:48.

## 0.2.5 - 2026-10-08

- Conserva el día, la hora y la duración canónicos cuando sólo falta elegir el deporte.
- Una respuesta breve como `Futbol` completa la reserva iniciada, crea el hold y solicita el comprobante, sin volver a listar todos los horarios del día.
- Impide que borradores viejos del puente legado reemplacen el slot recién entendido por el fast path.
- Añade una regresión artificial completa para el diálogo `cancha para las 4` → `Futbol`.

## 0.2.4 - 2026-10-08

- Se corrigió `ZIP does not support timestamps before 1980` al crear el
  respaldo automático desde la actualización de la GUI.
- Los archivos con fechas antiguas se guardan en el ZIP con la fecha mínima
  compatible, sin modificar los originales del cliente.
- La misma protección se agregó a los instaladores completos de Windows y
  Debian y al generador de paquetes de actualización.

## 0.2.3 - 2026-10-08

- Una consulta de disponibilidad con hora exacta y sin fecha, como `tenes
  cancha para las 4`, se interpreta como una consulta para hoy y conserva la
  resolución operacional de reloj (`16:00` a las 12:22).
- Si el agente ya había preguntado el día, una respuesta como `Hoy` conserva la
  hora, deporte y duración pendientes en vez de mostrar toda la agenda diaria.
- Las consultas de disponibilidad reconocidas por el fast path canónico ya no
  pueden caer al executor legacy por baja confianza, error interno o resultado
  no manejado: se aplica el cierre seguro canónico.

## 0.2.2 - 2026-10-08

- Se corrigió el error de Windows `built-in function kill returned a result
  with an exception set` que podía abortar una actualización después de cerrar
  la GUI.
- El auxiliar ahora espera el cierre de CANCHERIA mediante un handle nativo de
  Windows, evitando la condición de carrera de `os.kill(pid, 0)`.
- Las próximas actualizaciones ejecutarán primero el auxiliar nuevo y verificado
  incluido en el paquete descargado, para que el propio actualizador pueda
  repararse antes de reemplazar el programa.

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

