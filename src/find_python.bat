@echo off
rem Sets PY to a Python 3.10-3.14 that has tkinter and venv, for Setup.bat and
rem Launch.bat. The Windows "py" launcher comes with every python.org install.
set "PY="
set "PY_CHECK=import sys, tkinter, venv; sys.exit(0 if (3, 10) <= sys.version_info < (3, 15) else 1)"
for %%v in (3.12 3.11 3.13 3.10 3.14) do (
    if not defined PY (
        py -%%v -c "%PY_CHECK%" >nul 2>&1 && set "PY=py -%%v"
    )
)
rem "python" can be the Microsoft Store stub, which fails this check.
if not defined PY (
    python -c "%PY_CHECK%" >nul 2>&1 && set "PY=python"
)
if defined PY exit /b 0

echo.
echo   No usable Python was found on this PC.
echo.
echo   This macro needs Python 3.10 to 3.14 from python.org; 3.12 is the safest.
echo   Download the "Windows installer (64-bit)" from
echo       https://www.python.org/downloads/windows/
echo   In the installer, tick "Add python.exe to PATH" and keep "py launcher"
echo   and "tcl/tk" on. Then run this again.
echo.
exit /b 1
