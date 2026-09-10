@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem Crash-guard launcher: normal close writes the exit flag (no restart);
rem abnormal exit (crash) auto-restarts and restores the session.
rem Stops after 5 consecutive abnormal exits and asks to check the log.

rem 1) pythonw in PATH
where pythonw >nul 2>nul
if %errorlevel%==0 (
    set "PYEXE=pythonw"
    goto run
)

rem 2) Doubao-bundled pythonw: newest sandbox base under AppData
set "PYB="
for /f "delims=" %%d in ('dir /b /o-d /ad "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\*" 2^>nul') do if not defined PYB set "PYB=%%d"
if defined PYB (
    if exist "%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\%PYB%\python\pythonw.exe" (
        set "PYEXE=%LOCALAPPDATA%\Doubao\User Data\sandbox_runtime\bases\%PYB%\python\pythonw.exe"
        goto run
    )
)

rem 3) python in PATH (will show a console window)
where python >nul 2>nul
if %errorlevel%==0 (
    set "PYEXE=python"
    goto run
)

echo.
echo Python not found (pythonw / python). Install Python 3 and check "Add Python to PATH", then retry.
pause
exit /b

:run
set /a n=0
:loop
del "video_desc_normal_exit.flag" 2>nul
start "" /wait "%PYEXE%" video_desc_tool.py
if exist "video_desc_normal_exit.flag" (
    del "video_desc_normal_exit.flag" 2>nul
    exit /b
)
set /a n+=1
if %n% geq 5 (
    echo Tool exited abnormally 5 times. Please check video_desc_tool.log and restart.
    pause
    exit /b
)
timeout /t 2 /nobreak >nul
goto loop
