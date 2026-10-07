#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
INSTALLER="$ROOT_DIR/release/InstaladorCancheriaLinux.run"
[ -f "$INSTALLER" ] || {
    printf 'Falta %s\n' "$INSTALLER" >&2
    exit 1
}

TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cancheria-linux-smoke.XXXXXX")"
cleanup() {
    case "$TEST_ROOT" in
        "${TMPDIR:-/tmp}"/cancheria-linux-smoke.*) rm -rf -- "$TEST_ROOT" ;;
    esac
}
trap cleanup EXIT HUP INT TERM

MOCK_BIN="$TEST_ROOT/mock-bin"
TEST_HOME="$TEST_ROOT/home"
mkdir -p "$MOCK_BIN" "$TEST_HOME"

cat > "$MOCK_BIN/sudo" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "env" ]; then
    shift
    while [ "$#" -gt 0 ] && [ "${1#*=}" != "$1" ]; do shift; done
fi
exec "$@"
EOF

cat > "$MOCK_BIN/apt-get" <<'EOF'
#!/bin/sh
exit 0
EOF

cat > "$MOCK_BIN/python3" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
    VENV_DIR="$3"
    mkdir -p "$VENV_DIR/bin"
    cat > "$VENV_DIR/bin/python" <<'INNER'
#!/bin/sh
if [ "${1:-}" = "-c" ]; then printf 'CANCHERIA OK\n'; fi
exit 0
INNER
    chmod 755 "$VENV_DIR/bin/python"
fi
exit 0
EOF

cat > "$MOCK_BIN/chromium" <<'EOF'
#!/bin/sh
exit 0
EOF

cat > "$MOCK_BIN/zip" <<'EOF'
#!/bin/sh
while [ "$#" -gt 0 ]; do
    case "$1" in
        -*) shift ;;
        *) : > "$1"; exit 0 ;;
    esac
done
exit 1
EOF

chmod 755 "$MOCK_BIN/sudo" "$MOCK_BIN/apt-get" "$MOCK_BIN/python3" \
    "$MOCK_BIN/chromium" "$MOCK_BIN/zip"

run_installer() {
    HOME="$TEST_HOME" \
    XDG_DATA_HOME="$TEST_HOME/.local/share" \
    DISPLAY='' \
    WAYLAND_DISPLAY='' \
    PATH="$MOCK_BIN:$PATH" \
    bash "$INSTALLER"
}

run_installer
INSTALL_DIR="$TEST_HOME/.local/share/CANCHERIA"
[ -f "$INSTALL_DIR/WPSetter.py" ]
[ -f "$INSTALL_DIR/src/cancheria/browser_runtime.py" ]
[ -x "$TEST_HOME/.local/bin/cancheria" ]
[ -f "$TEST_HOME/.local/share/applications/cancheria.desktop" ]

printf '# configuración del cliente\n' > "$INSTALL_DIR/src/cancheria/config/legacy_config.py"
printf 'dato operativo\n' > "$INSTALL_DIR/runtime/cliente.txt"
run_installer

grep -q 'configuración del cliente' "$INSTALL_DIR/src/cancheria/config/legacy_config.py"
grep -q 'dato operativo' "$INSTALL_DIR/runtime/cliente.txt"
find "$INSTALL_DIR/Backups" -maxdepth 1 -name 'CANCHERIA_BACKUP_ANTES_ACTUALIZAR_*.zip' | grep -q .

printf 'Smoke test Linux: OK\n'
