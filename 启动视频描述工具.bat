@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Launcher: starts guard.py (pythonw, no window) which runs and
rem auto-restarts the main tool on abnormal exit; normal close exits both.
rem Every branch ends with "exit" (not "exit /b") so the cmd window always closes.

rem 1) pythonw in PATH
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0guard.py"
    exit
)

rem 2) Doubao-bundled pythonw: newest sandbox base under AppData
set "PYB="
for /f "delims=" %%d in ('dir /b /o-d /ad "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\*" 2^>nul') do if not defined PYB set "PYB=%%d"
if defined PYB (
    if exist "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\%PYB%\python\pythonw.exe" (
        start "" "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\%PYB%\python\pythonw.exe" "%~dp0guard.py"
        exit
    )
)

rem 3) python in PATH (will show a console window briefly)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "%~dp0guard.py"
    exit
)

echo.
echo Python not found (pythonw / python). Install Python 3 and check "Add Python to PATH", then retry.
pause
