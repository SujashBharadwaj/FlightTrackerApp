@echo off
echo ============================================
echo   RJ Airplane Tracker Widget - Launcher
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Download from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install / update dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
echo.

:: Launch the widget
echo Launching RJ Airplane Tracker...
echo.
python tracker_widget.py

pause
