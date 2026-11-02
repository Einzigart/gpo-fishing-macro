@echo off
setlocal
cd /d "%~dp0"

rem Any Python will do for the report, also one the macro cannot use.
call src\find_python.bat >nul
set "DPY=%PY%"
if not defined DPY (
    py -3 -c "pass" >nul 2>&1 && set "DPY=py -3"
)
if not defined DPY (
    python -c "pass" >nul 2>&1 && set "DPY=python"
)

if defined DPY (
    %DPY% src\diagnose.py > diagnose-log.txt 2>&1
) else (
    echo No Python was found on this PC.> diagnose-log.txt
    ver >> diagnose-log.txt
)
type diagnose-log.txt

echo.
echo   Written to diagnose-log.txt next to this file. Send that file.
echo.
pause
