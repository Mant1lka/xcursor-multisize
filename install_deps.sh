#!/bin/bash
# Установка зависимостей для xcursor-multisize
# Поддержка Arch Linux, CachyOS и других Arch-based дистрибутивов

set -e

echo "Проверка и установка зависимостей для xcursor-multisize..."

if command -v pacman &> /dev/null; then
    echo "Обнаружена Arch-based система. Установка пакетов..."
    sudo pacman -S --needed --noconfirm xcur2png xorg-xcursorgen imagemagick
else
    echo "Ошибка: Этот скрипт предназначен для Arch Linux и его производных."
    echo "Для других дистрибутивов установите вручную:"
    echo "  - xcur2png"
    echo "  - xorg-xcursorgen (или xcursorgen)"
    echo "  - imagemagick"
    exit 1
fi

echo "Все зависимости установлены успешно!"
echo "Теперь вы можете запустить: python3 xcursor-multisize.py"
