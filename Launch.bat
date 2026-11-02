@echo off
setlocal
cd /d "%~dp0"

call src\find_python.bat
if not defined PY goto :hold

%PY% src\bootstrap.py main.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo   The macro exited with an error.
echo   Run Diagnose.bat and send the diagnose-log.txt it writes.

:hold
echo.
pause
exit /b 1
