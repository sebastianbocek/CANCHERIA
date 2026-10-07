@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   CANCHERIA - Instalador Windows limpio
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\build_fresh_installer.ps1"
if errorlevel 1 (
  echo.
  echo ERROR: no se pudo generar InstaladorCancheria.exe
  exit /b 1
)

echo.
echo Instalador generado:
echo   %CD%\release\InstaladorCancheria.exe
exit /b 0

