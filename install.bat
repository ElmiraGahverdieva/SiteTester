@echo off
cd /d "%~dp0"

echo ======================================
echo   SiteTester - Installation
echo ======================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo.
    echo Please download and install Python 3.11+:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: check "Add Python to PATH" during install
    echo.
    pause
    exit /b 1
)

python --version

echo.
echo [1/4] Creating virtual environment...
if exist venv (
    echo        Already exists, skipping.
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv
        pause & exit /b 1
    )
)

echo.
echo [2/4] Installing dependencies...
call venv\Scripts\activate
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause & exit /b 1
)

echo.
echo [3/4] Installing Chromium browser...
playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Chromium
    pause & exit /b 1
)

echo.
echo [4/4] Checking installation...
python -c "import playwright, flask, PIL, numpy; print('  All OK')"

echo.
echo ======================================
echo   Installation complete!
echo.
echo   To start: double-click SiteTester.bat
echo ======================================
echo.
pause
