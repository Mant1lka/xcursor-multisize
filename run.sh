#!/bin/bash
# Быстрый запуск xcursor-multisize с аргументами командной строки

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/xcursor-multisize.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Ошибка: Не найден скрипт xcursor-multisize.py"
    exit 1
fi

if [ $# -eq 0 ]; then
    python3 "$PYTHON_SCRIPT"
else
    python3 "$PYTHON_SCRIPT" "$@"
fi
