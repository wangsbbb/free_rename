@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "LOG=%ROOT%build_free_rename_log.txt"

echo [INFO] free_rename v1.0.14 onedir build > "%LOG%"
echo [INFO] Working dir: %ROOT%>> "%LOG%"

echo.
echo === free_rename onedir build ===
echo.

if not exist "%ROOT%src\free_rename.py" (
  echo [ERROR] src\free_rename.py not found.
  echo [ERROR] src\free_rename.py not found.>> "%LOG%"
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

for /f "usebackq delims=" %%i in (`%PYTHON_EXE% -c "import sysconfig; print(sysconfig.get_path('scripts') or '')"`) do set "PY_SCRIPTS=%%i"
for /f "usebackq delims=" %%i in (`%PYTHON_EXE% -c "import site,os; ub=site.getuserbase(); print(os.path.join(ub, 'Scripts') if ub else '')"`) do set "PY_USER_SCRIPTS=%%i"
if defined PY_SCRIPTS set "PATH=%PY_SCRIPTS%;%PATH%"
if defined PY_USER_SCRIPTS set "PATH=%PY_USER_SCRIPTS%;%PATH%"

echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Python: %PYTHON_EXE%>> "%LOG%"
echo [INFO] Python Scripts: %PY_SCRIPTS%
echo [INFO] Python Scripts: %PY_SCRIPTS%>> "%LOG%"
echo [INFO] User Scripts: %PY_USER_SCRIPTS%
echo [INFO] User Scripts: %PY_USER_SCRIPTS%>> "%LOG%"

call %PYTHON_EXE% -m pip install --upgrade pip >> "%LOG%" 2>&1
call %PYTHON_EXE% -m pip install -r "%ROOT%requirements_free_rename.txt" pyinstaller >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Failed to install build dependencies. See build_free_rename_log.txt
  echo [ERROR] Failed to install build dependencies.>> "%LOG%"
  pause
  exit /b 1
)

echo [INFO] Syncing version...
echo [INFO] Syncing version...>> "%LOG%"
call %PYTHON_EXE% "%ROOT%src\sync_version.py" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Version sync failed. See build_free_rename_log.txt
  echo [ERROR] Version sync failed.>> "%LOG%"
  pause
  exit /b 1
)

echo [INFO] Building Qt resources...
echo [INFO] Building Qt resources...>> "%LOG%"
call %PYTHON_EXE% "%ROOT%src\build_resources.py" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Qt resource compile failed. See build_free_rename_log.txt
  echo [ERROR] Qt resource compile failed.>> "%LOG%"
  pause
  exit /b 1
)

if exist "%ROOT%build" rmdir /s /q "%ROOT%build"
if exist "%ROOT%dist" rmdir /s /q "%ROOT%dist"

echo [INFO] Running PyInstaller...
echo [INFO] Running PyInstaller...>> "%LOG%"

set "UPX_ARG="
if defined UPX_DIR if exist "%UPX_DIR%\upx.exe" set "UPX_ARG=--upx-dir "%UPX_DIR%""
if not defined UPX_ARG if exist "%ROOT%tools\upx\upx.exe" set "UPX_ARG=--upx-dir "%ROOT%tools\upx""

call %PYTHON_EXE% -m PyInstaller --noconfirm --clean !UPX_ARG! "%ROOT%free_rename.spec" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Build failed. See build_free_rename_log.txt
  echo [ERROR] Build failed.>> "%LOG%"
  pause
  exit /b 1
)

if exist "%ROOT%dist\free_rename\free_rename.exe" (
  copy /y "%ROOT%launch_free_rename.bat" "%ROOT%dist\launch_free_rename.bat" >nul 2>nul
  echo.
  echo [OK] Build complete: dist\free_rename\free_rename.exe
  echo [OK] Build complete: dist\free_rename\free_rename.exe>> "%LOG%"
) else (
  echo [ERROR] Build output not found.
  echo [ERROR] Build output not found.>> "%LOG%"
  pause
  exit /b 1
)

echo.
echo Note: this build uses onedir mode for faster startup.
echo Optional: set UPX_DIR to enable additional executable compression.
pause
exit /b 0
