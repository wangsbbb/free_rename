@echo off
setlocal
cd /d "%~dp0"

set "PYEXE="
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"
if not defined PYEXE if exist "venv\Scripts\python.exe" set "PYEXE=venv\Scripts\python.exe"
if not defined PYEXE where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"

if not defined PYEXE (
  echo Python not found.
  pause
  exit /b 1
)

if not exist "src\free_rename.py" (
  echo src\free_rename.py not found.
  pause
  exit /b 1
)

echo Using Python: %PYEXE%
%PYEXE% -m pip install --disable-pip-version-check -q -r requirements_free_rename.txt >nul 2>nul
%PYEXE% src\free_rename.py
if errorlevel 1 pause
endlocal
