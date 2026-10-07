@echo off
setlocal
cd /d "%~dp0"

python scripts\build_linux_installer.py --source "%CD%"
if errorlevel 1 (
    echo.
    echo No se pudo crear el instalador Linux.
    pause
    exit /b 1
)

echo.
echo Instalador listo en release\InstaladorCancheriaLinux.run
pause
