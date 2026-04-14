@echo off
setlocal
cd /d "%~dp0"
if exist ".\free_rename\free_rename.exe" (
  start "" ".\free_rename\free_rename.exe"
) else (
  echo free_rename\free_rename.exe not found.
  pause
)
endlocal
