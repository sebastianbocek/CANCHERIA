@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BUILD_PY=%CD%\.build-venv\Scripts\python.exe"
set "OUTPUT=%CD%\Crear_Backup_Fresco_CANCHERIA.exe"
set "WORK=%CD%\build\backup-creator"

if not exist "%BUILD_PY%" (
  echo ERROR: No existe %BUILD_PY%
  echo Ejecuta build_windows.bat una vez y volve a intentar.
  pause
  exit /b 1
)

"%BUILD_PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --console ^
  --name Crear_Backup_Fresco_CANCHERIA ^
  --distpath "%CD%" ^
  --workpath "%WORK%\pyinstaller" ^
  --specpath "%WORK%\spec" ^
  --icon "%CD%\assets\cancheria.ico" ^
  "%CD%\scripts\create_fresh_client_zip.py"

if errorlevel 1 (
  echo ERROR: No se pudo compilar el creador de backups.
  pause
  exit /b 1
)

echo.
echo CREADO: %OUTPUT%
pause
exit /b 0
