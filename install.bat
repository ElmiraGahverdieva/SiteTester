@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════╗
echo  ║      SiteTester — Установка          ║
echo  ╚══════════════════════════════════════╝
echo.

REM Переходим в папку скрипта
cd /d "%~dp0"

REM ── Проверяем Python ─────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Python не найден!
    echo.
    echo  Скачайте и установите Python 3.11 или новее:
    echo  https://www.python.org/downloads/
    echo.
    echo  ВАЖНО: при установке отметьте галочку
    echo         "Add Python to PATH"
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo  Python: %%i

REM ── Создаём виртуальное окружение ────────────────────────────────────────
echo.
echo  [1/4] Создание виртуального окружения...
if exist venv (
    echo        Уже существует, пропускаем.
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ОШИБКА] Не удалось создать окружение
        pause & exit /b 1
    )
)

REM ── Устанавливаем зависимости ─────────────────────────────────────────────
echo.
echo  [2/4] Установка зависимостей...
call venv\Scripts\activate
pip install --upgrade pip -q
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Ошибка установки зависимостей
    pause & exit /b 1
)

REM ── Устанавливаем браузер ─────────────────────────────────────────────────
echo.
echo  [3/4] Установка браузера Chromium...
playwright install chromium
if %errorlevel% neq 0 (
    echo  [ОШИБКА] Не удалось установить Chromium
    pause & exit /b 1
)

REM ── Готово ───────────────────────────────────────────────────────────────
echo.
echo  [4/4] Проверка установки...
python -c "import playwright, flask, PIL, numpy; print('  OK')"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   ✅  Установка завершена!           ║
echo  ║                                      ║
echo  ║   Для запуска дважды кликните на:    ║
echo  ║   SiteTester.bat                     ║
echo  ╚══════════════════════════════════════╝
echo.
pause
