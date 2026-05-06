#!/bin/bash
# Двойной клик на Mac — запускает SiteTester
cd "$(dirname "$0")"

if [ ! -f venv/bin/activate ]; then
    echo "Окружение не найдено. Сначала запустите install.sh"
    read -p "Нажмите Enter..."
    exit 1
fi

source venv/bin/activate
python gui_app.py
