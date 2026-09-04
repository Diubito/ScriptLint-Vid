@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 1) pythonw in PATH (works if Python is installed normally)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw video_desc_tool.py
    exit /b
)

rem 2) Doubao-bundled pythonw: newest sandbox base under AppData
set "PYB="
for /f "delims=" %%d in ('dir /b /o-d /ad "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\*" 2^>nul') do if not defined PYB set "PYB=%%d"
if defined PYB (
    if exist "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\%PYB%\python\pythonw.exe" (
        start "" "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\%PYB%\python\pythonw.exe" video_desc_tool.py
        exit /b
    )
)

rem 3) python in PATH (will show a console window)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python video_desc_tool.py
    exit /b
)

echo.
echo Python not found (pythonw / python). Install Python 3 and check "Add Python to PATH", then retry.
pause
