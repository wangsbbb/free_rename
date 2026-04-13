\
@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "LOG=%ROOT%build_free_rename_log.txt"

echo [INFO] free_rename v1.0 onefile build > "%LOG%"
echo [INFO] Working dir: %ROOT%>> "%LOG%"

echo.
echo === free_rename v1.0 onefile build ===
echo.

if not exist "%ROOT%free_rename.py" (
  echo [ERROR] free_rename.py not found.
  echo [ERROR] free_rename.py not found.>> "%LOG%"
  pause
  exit /b 1
)

set "PYTHON_EXE="
if exist "%ROOT%venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%ROOT%.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
  py -3 -c "import sys; print(sys.executable)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=py -3"
)
if not defined PYTHON_EXE (
  python -c "import sys; print(sys.executable)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  echo [ERROR] Python not found.
  echo [ERROR] Python not found.>> "%LOG%"
  pause
  exit /b 1
)

echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Python: %PYTHON_EXE%>> "%LOG%"

if not exist "%ROOT%assets" (
  echo [ERROR] assets folder not found.
  echo [ERROR] assets folder not found.>> "%LOG%"
  pause
  exit /b 1
)

set "ICON_FILE=%ROOT%assets\icons\app_icon_final.ico"
set "VERSION_FILE=%ROOT%version_info.txt"

call %PYTHON_EXE% -m pip install --upgrade pip >> "%LOG%" 2>&1
call %PYTHON_EXE% -m pip install -r "%ROOT%requirements_free_rename.txt" pyinstaller >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Failed to install build dependencies. See build_free_rename_log.txt
  echo [ERROR] Failed to install build dependencies.>> "%LOG%"
  pause
  exit /b 1
)

if exist "%ROOT%build" rmdir /s /q "%ROOT%build"
if exist "%ROOT%dist" rmdir /s /q "%ROOT%dist"

echo [INFO] Running PyInstaller...
echo [INFO] Running PyInstaller...>> "%LOG%"

set "PYI_CMD=%PYTHON_EXE% -m PyInstaller --noconfirm --clean --windowed --onefile --name free_rename --add-data assets;assets"
if exist "%ICON_FILE%" set "PYI_CMD=!PYI_CMD! --icon "%ICON_FILE%""
if exist "%VERSION_FILE%" set "PYI_CMD=!PYI_CMD! --version-file "%VERSION_FILE%""
set "PYI_CMD=!PYI_CMD! "%ROOT%free_rename.py""

call !PYI_CMD! >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Build failed. See build_free_rename_log.txt
  echo [ERROR] Build failed.>> "%LOG%"
  pause
  exit /b 1
)

if exist "%ROOT%dist\free_rename.exe" (
  echo.
  echo [OK] Build complete: dist\free_rename.exe
  echo [OK] Build complete: dist\free_rename.exe>> "%LOG%"
) else (
  echo [ERROR] Build output not found.
  echo [ERROR] Build output not found.>> "%LOG%"
  pause
  exit /b 1
)

echo.
echo Note: onefile EXE extracts runtime files on first launch.
echo If Windows still shows the old icon, delete the old shortcut and create a new one.
pause
exit /b 0
