#!/bin/sh
set -eu

APP_NAME="CANCHERIA"
APP_VERSION="0.2.26"
PAYLOAD_MARKER="__CANCHERIA_PAYLOAD_BELOW__"

say() {
    printf '%s\n' "$*"
}

fail() {
    say ""
    say "ERROR: $*"
    exit 1
}

if [ "$(id -u)" -eq 0 ]; then
    fail "Ejecutá este instalador con tu usuario normal, no con sudo. El instalador pedirá la contraseña cuando la necesite."
fi

command -v apt-get >/dev/null 2>&1 || fail "Este instalador requiere Debian o una distribución basada en Debian con apt-get."
command -v sudo >/dev/null 2>&1 || fail "No encontré sudo. Instalalo o agregá este usuario al grupo sudo."

say "============================================================"
say "  Instalador de $APP_NAME para Debian - $APP_VERSION"
say "============================================================"
say ""
say "Se instalarán Python, Tkinter, Chromium y los componentes de CANCHERIA."
say "sudo puede pedirte la contraseña del usuario."
say ""

say "[1/7] Instalando dependencias del sistema..."
sudo apt-get update
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-venv python3-pip python3-tk \
    chromium xdg-utils zip ca-certificates

python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || \
    fail "CANCHERIA requiere Python 3.10 o superior. Usá Debian 12 o una versión más nueva."

INSTALL_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$INSTALL_BASE/CANCHERIA"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$INSTALL_BASE/applications"
BACKUP_DIR="$INSTALL_DIR/Backups"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cancheria-installer.XXXXXX")"

cleanup() {
    case "$TEMP_DIR" in
        "${TMPDIR:-/tmp}"/cancheria-installer.*) rm -rf -- "$TEMP_DIR" ;;
    esac
}
trap cleanup EXIT HUP INT TERM

say "[2/7] Extrayendo el paquete fresco..."
PAYLOAD_LINE="$(awk -v marker="$PAYLOAD_MARKER" '$0 == marker { print NR + 1; exit }' "$0")"
[ -n "$PAYLOAD_LINE" ] || fail "El instalador está incompleto: no se encontró el paquete interno."
mkdir -p "$TEMP_DIR/payload"
tail -n "+$PAYLOAD_LINE" "$0" | tar -xzf - -C "$TEMP_DIR/payload" || \
    fail "No se pudo extraer el paquete interno. Volvé a descargar el instalador."

CONFIG_REL="src/cancheria/config/legacy_config.py"
IS_UPDATE=0
if [ -f "$INSTALL_DIR/$CONFIG_REL" ] || [ -d "$INSTALL_DIR/runtime" ] || [ -d "$INSTALL_DIR/wa_profile" ]; then
    IS_UPDATE=1
fi

if [ "$IS_UPDATE" -eq 1 ]; then
    say "[3/7] Creando respaldo automático antes de actualizar..."
    mkdir -p "$BACKUP_DIR"
    BACKUP_STAGE="$TEMP_DIR/update-backup"
    mkdir -p "$BACKUP_STAGE"

    copy_backup_item() {
        RELATIVE_ITEM="$1"
        if [ -e "$INSTALL_DIR/$RELATIVE_ITEM" ]; then
            mkdir -p "$BACKUP_STAGE/$(dirname "$RELATIVE_ITEM")"
            cp -a "$INSTALL_DIR/$RELATIVE_ITEM" "$BACKUP_STAGE/$RELATIVE_ITEM"
        fi
    }

    for item in \
        "config.py" \
        "config_backups" \
        "$CONFIG_REL" \
        "src/cancheria/config/config_backups" \
        runtime wa_profile sessions audios comprobantes torneos agent_learning \
        .env blacklist_numbers.json bot_state.pkl business_events.json \
        calendar_events.db calendario_turnos.csv calendario_turnos.csv.reservation_id.seq \
        client_memory.json conversation_log.jsonl conversation_states.json human_cases.json \
        operations_metrics.jsonl proactive_state.json reservas_contactos.csv \
        selector_adaptation_cache.json selector_health_history.json turnos_terminados.csv
    do
        copy_backup_item "$item"
    done

    printf '%s\n' \
        "CANCHERIA - Respaldo automático antes de actualizar" \
        "Fecha: $(date '+%Y-%m-%d %H:%M:%S')" \
        "Instalación original: $INSTALL_DIR" \
        "" \
        "Este ZIP contiene configuración y datos privados del cliente." \
        "No debe compartirse públicamente." > "$BACKUP_STAGE/LEEME_RESPALDO.txt"

    # ZIP sólo admite fechas entre 1980 y 2107. Se corrige únicamente la copia
    # temporal del respaldo, nunca los archivos originales de la instalación.
    find "$BACKUP_STAGE" -type f ! -newermt '1980-01-01 00:00:00 UTC' \
        -exec touch -d '1980-01-01 00:00:00 UTC' {} +
    find "$BACKUP_STAGE" -type f -newermt '2107-12-31 23:59:58 UTC' \
        -exec touch -d '2107-12-31 23:59:58 UTC' {} +

    BACKUP_FILE="$BACKUP_DIR/CANCHERIA_BACKUP_ANTES_ACTUALIZAR_$(date '+%Y%m%d_%H%M%S').zip"
    (
        cd "$BACKUP_STAGE"
        zip -qr "$BACKUP_FILE" . \
            -x 'wa_profile/*/Cache/*' \
               'wa_profile/*/Code Cache/*' \
               'wa_profile/*/GPUCache/*' \
               'wa_profile/*/DawnCache/*' \
               'wa_profile/*/GrShaderCache/*' \
               'wa_profile/*/ShaderCache/*' \
               'wa_profile/Crashpad/*'
    ) || fail "No se pudo crear el respaldo. La actualización fue cancelada sin modificar CANCHERIA."
    say "      Respaldo: $BACKUP_FILE"
else
    say "[3/7] Instalación nueva: no hay datos anteriores que respaldar."
fi

say "[4/7] Instalando los archivos de CANCHERIA..."
mkdir -p "$INSTALL_DIR" "$BACKUP_DIR"
PRESERVED_CONFIG="$TEMP_DIR/legacy_config.py"
PRESERVED_ROOT_CONFIG="$TEMP_DIR/config.py"
if [ -f "$INSTALL_DIR/$CONFIG_REL" ]; then
    cp -a "$INSTALL_DIR/$CONFIG_REL" "$PRESERVED_CONFIG"
fi
if [ -f "$INSTALL_DIR/config.py" ]; then
    cp -a "$INSTALL_DIR/config.py" "$PRESERVED_ROOT_CONFIG"
fi
cp -a "$TEMP_DIR/payload/." "$INSTALL_DIR/"
if [ -f "$PRESERVED_CONFIG" ]; then
    cp -a "$PRESERVED_CONFIG" "$INSTALL_DIR/$CONFIG_REL"
    cmp -s "$PRESERVED_CONFIG" "$INSTALL_DIR/$CONFIG_REL" || \
        fail "No se pudo verificar la restauración de la configuración anterior."
fi
if [ -f "$PRESERVED_ROOT_CONFIG" ]; then
    cp -a "$PRESERVED_ROOT_CONFIG" "$INSTALL_DIR/config.py"
    cmp -s "$PRESERVED_ROOT_CONFIG" "$INSTALL_DIR/config.py" || \
        fail "No se pudo verificar la restauración del config.py anterior."
fi
mkdir -p "$INSTALL_DIR/runtime" "$INSTALL_DIR/wa_profile" "$INSTALL_DIR/sessions" "$BACKUP_DIR"

say "[5/7] Preparando Python y las dependencias de CANCHERIA..."
if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
"$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade -e "$INSTALL_DIR"

say "[6/7] Creando accesos directos..."
mkdir -p "$BIN_DIR" "$APPLICATIONS_DIR"

printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/CANCHERIA"' \
    'export CANCHERIA_INSTALL_ROOT="$INSTALL_DIR"' \
    'cd "$INSTALL_DIR"' \
    'exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/cancheria_desktop.py" "$@"' \
    > "$BIN_DIR/cancheria"

printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/CANCHERIA"' \
    'export CANCHERIA_INSTALL_ROOT="$INSTALL_DIR"' \
    'cd "$INSTALL_DIR"' \
    'exec "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/configurador_cancheria.py" "$@"' \
    > "$BIN_DIR/configurar-cancheria"

chmod 755 "$BIN_DIR/cancheria" "$BIN_DIR/configurar-cancheria"

DESKTOP_FILE="$APPLICATIONS_DIR/cancheria.desktop"
printf '%s\n' \
    '[Desktop Entry]' \
    'Type=Application' \
    'Version=1.0' \
    'Name=CANCHERIA' \
    'Comment=Agente de reservas por WhatsApp' \
    "Exec=$BIN_DIR/cancheria" \
    "Icon=$INSTALL_DIR/assets/cancheria-logo.png" \
    'Terminal=false' \
    'Categories=Office;Utility;' \
    'StartupNotify=true' \
    > "$DESKTOP_FILE"
chmod 755 "$DESKTOP_FILE"

CONFIG_DESKTOP_FILE="$APPLICATIONS_DIR/configurar-cancheria.desktop"
printf '%s\n' \
    '[Desktop Entry]' \
    'Type=Application' \
    'Version=1.0' \
    'Name=Configurar CANCHERIA' \
    'Comment=Configuración del complejo deportivo' \
    "Exec=$BIN_DIR/configurar-cancheria" \
    "Icon=$INSTALL_DIR/assets/cancheria-logo.png" \
    'Terminal=false' \
    'Categories=Office;Utility;' \
    'StartupNotify=true' \
    > "$CONFIG_DESKTOP_FILE"
chmod 755 "$CONFIG_DESKTOP_FILE"

DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
elif [ -d "$HOME/Desktop" ]; then
    DESKTOP_DIR="$HOME/Desktop"
elif [ -d "$HOME/Escritorio" ]; then
    DESKTOP_DIR="$HOME/Escritorio"
fi
if [ -n "$DESKTOP_DIR" ] && [ -d "$DESKTOP_DIR" ]; then
    cp -a "$DESKTOP_FILE" "$DESKTOP_DIR/CANCHERIA.desktop"
    chmod 755 "$DESKTOP_DIR/CANCHERIA.desktop"
fi
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true

say "[7/7] Verificando la instalación..."
CANCHERIA_INSTALL_ROOT="$INSTALL_DIR" \
    "$INSTALL_DIR/.venv/bin/python" -c \
    'import cancheria; from cancheria.browser_runtime import persistent_context_options; print("CANCHERIA OK")'
command -v chromium >/dev/null 2>&1 || fail "Chromium no quedó disponible en el sistema."

say ""
say "============================================================"
say "  CANCHERIA quedó instalado correctamente"
say "============================================================"
say "Carpeta: $INSTALL_DIR"
say "Menú de aplicaciones: CANCHERIA"
say "Configuración: Configurar CANCHERIA"
say "Respaldos de actualizaciones: $BACKUP_DIR"
say ""

if { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; } && [ -t 0 ]; then
    printf '¿Querés abrir ahora el configurador? [S/n]: '
    read -r OPEN_CONFIG || OPEN_CONFIG="s"
    case "$OPEN_CONFIG" in
        n|N|no|NO) ;;
        *)
            nohup "$BIN_DIR/configurar-cancheria" >"$TEMP_DIR/configurador.log" 2>&1 &
            say "Configurador abierto."
            ;;
    esac
fi

exit 0
__CANCHERIA_PAYLOAD_BELOW__
