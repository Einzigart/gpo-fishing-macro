@echo off
setlocal
cd /d "%~dp0"

call src\find_python.bat
if not defined PY goto :hold

%PY% src\bootstrap.py main.py --check
if errorlevel 1 goto :failed

echo.
echo   Setup finished. Start the macro with the "GPO Fishing Macro" shortcut in
echo   this folder. Launch.bat still works too.
goto :hold

:failed
echo.
echo   Setup did not finish. See the messages above and setup-log.txt.
echo   If it is not obvious, run Diagnose.bat and send diagnose-log.txt.

:hold
echo.
pause
