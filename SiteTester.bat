@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist venv\Scripts\activate (
    echo  Окружение не найдено. Сначала запустите install.bat
    pause
    exit /b 1
)

call venv\Scripts\activate
python gui_app.py
pause
