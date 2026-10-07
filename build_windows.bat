@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%CD%"
set "BUILD_VENV=%ROOT%\.build-venv"
set "BUILD_PY=%BUILD_VENV%\Scripts\python.exe"
set "ICON=%ROOT%\assets\cancheria.ico"
set "SRC=%ROOT%\src"
set "SPEC_DIR=%ROOT%\build\spec"

echo ============================================================
echo   CANCHERIA - Build Windows
echo   cancheria.exe + configurador_cancheria.exe en la RAIZ
echo ============================================================
echo.

if not exist "%ICON%" (
  echo ERROR: No se encontro el icono:
  echo   %ICON%
  pause
  exit /b 1
)
if not exist "%ROOT%\cancheria_desktop.py" (
  echo ERROR: No se encontro cancheria_desktop.py en la raiz.
  pause
  exit /b 1
)
if not exist "%ROOT%\configurador_cancheria.py" (
  echo ERROR: No se encontro configurador_cancheria.py en la raiz.
  pause
  exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: No se encontro el launcher "py" de Python.
  echo Instala Python 3.10+ y marca "Add Python to PATH".
  pause
  exit /b 1
)

rem Build aislado: evita heredar torch/onnx/pandas del Python global.
if not exist "%BUILD_PY%" (
  echo [1/8] Creando entorno aislado de compilacion...
  py -m venv "%BUILD_VENV%"
  if errorlevel 1 goto :error
) else (
  echo [1/8] Entorno aislado de compilacion encontrado.
)

echo [2/8] Instalando/actualizando dependencias de build...
"%BUILD_PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error
"%BUILD_PY%" -m pip install -e ".[build]"
if errorlevel 1 goto :error

echo [3/8] Limpiando build anterior...
rmdir /s /q "%ROOT%\build" 2>nul
rmdir /s /q "%ROOT%\dist" 2>nul
mkdir "%SPEC_DIR%" 2>nul
del /q "%ROOT%\cancheria.exe" 2>nul
del /q "%ROOT%\configurador_cancheria.exe" 2>nul

echo [4/8] Compilando cancheria.exe...
"%BUILD_PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name cancheria ^
  --distpath "." ^
  --workpath "%ROOT%\build\pyinstaller-cancheria" ^
  --specpath "%SPEC_DIR%" ^
  --icon "%ICON%" ^
  --paths "%SRC%" ^
  --hidden-import json ^
  --hidden-import sqlite3 ^
  --hidden-import _sqlite3 ^
  --hidden-import decimal ^
  --hidden-import zoneinfo ^
  --hidden-import email.mime.image ^
  --hidden-import email.mime.multipart ^
  --hidden-import email.mime.text ^
  --hidden-import openai ^
  --hidden-import playwright.async_api ^
  --hidden-import pytz ^
  --hidden-import dotenv ^
  --hidden-import cancheria.legacy_bridge ^
  --hidden-import cancheria.paths ^
  --hidden-import cancheria.config.legacy_config ^
  --hidden-import cancheria.domain.events.registration ^
  --hidden-import cancheria.domain.reservations.calendar ^
  "%ROOT%\cancheria_desktop.py"
if errorlevel 1 goto :error

echo [5/8] Compilando configurador_cancheria.exe...
"%BUILD_PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name configurador_cancheria ^
  --distpath "." ^
  --workpath "%ROOT%\build\pyinstaller-configurador" ^
  --specpath "%SPEC_DIR%" ^
  --icon "%ICON%" ^
  --paths "%SRC%" ^
  --hidden-import json ^
  --hidden-import sqlite3 ^
  --hidden-import _sqlite3 ^
  --hidden-import decimal ^
  --hidden-import zoneinfo ^
  --hidden-import cancheria.paths ^
  --hidden-import cancheria.config.legacy_config ^
  "%ROOT%\configurador_cancheria.py"
if errorlevel 1 goto :error

if not exist "%ROOT%\cancheria.exe" (
  echo ERROR: PyInstaller termino pero no existe %ROOT%\cancheria.exe
  goto :error
)
if not exist "%ROOT%\configurador_cancheria.exe" (
  echo ERROR: PyInstaller termino pero no existe %ROOT%\configurador_cancheria.exe
  goto :error
)

echo [6/8] Verificando runtime congelado de cancheria.exe...
"%ROOT%\cancheria.exe" --self-test
if errorlevel 1 (
  echo ERROR: cancheria.exe no contiene todos los modulos de runtime.
  if exist "%ROOT%\build\runtime-selftest-cancheria.txt" type "%ROOT%\build\runtime-selftest-cancheria.txt"
  goto :error
)

echo [7/8] Verificando runtime congelado del configurador...
"%ROOT%\configurador_cancheria.exe" --self-test
if errorlevel 1 (
  echo ERROR: configurador_cancheria.exe no contiene todos los modulos de runtime.
  if exist "%ROOT%\build\runtime-selftest-configurador.txt" type "%ROOT%\build\runtime-selftest-configurador.txt"
  goto :error
)

echo [8/8] Armando paquete de distribucion...
"%BUILD_PY%" "%ROOT%\scripts\assemble_windows_release.py"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo BUILD COMPLETADO CORRECTAMENTE
echo.
echo EXE PRINCIPAL:
echo   %ROOT%\cancheria.exe
echo.
echo CONFIGURADOR:
echo   %ROOT%\configurador_cancheria.exe
echo.
echo PAQUETE PARA DISTRIBUIR:
echo   %ROOT%\release\CANCHERIA_WINDOWS.zip
echo ============================================================
echo.
echo Los EXE se usan desde la carpeta raiz. No uses dist.
pause
exit /b 0

:error
echo.
echo ============================================================
echo ERROR durante el build.
echo Revisa las ultimas lineas mostradas arriba.
echo ============================================================
pause
exit /b 1
