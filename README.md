# xcursor-multisize

[English](#english) · [Русский](#русский)

Interactive installer for Linux **Xcursor** themes on **KDE Plasma** (Arch / CachyOS and similar).

You download a cursor theme → run the script → answer a few questions in the terminal → the theme appears in Plasma **with a working size slider** (`24 / 32 / 48 / 64` by default).

Supports:

- Linux Xcursor themes
- Windows packs (`.ani` / `.cur`, including `install.inf`)

This repository contains **only the tool**. It does not ship any cursor artwork.

---

## English

### Why you need this

Many cursor packs include only one real size inside the Xcursor files (often `32`).  
Editing `index.theme` is not enough — KDE cannot invent missing sizes.  
This tool rebuilds the cursors with several real sizes.

### What you need first

1. A cursor theme folder that contains a `cursors/` directory (or point at `cursors/` itself).
   - Linux Xcursor themes, **or**
   - Windows packs with `.ani` / `.cur` (optional `install.inf`)
2. Install the required packages (see below).

### Install and run

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Mant1lka/xcursor-multisize.git
   cd xcursor-multisize
   ```

2. **Install dependencies** (Arch / CachyOS):
   ```bash
   sudo pacman -S xcur2png xorg-xcursorgen imagemagick
   ```

3. **Run the installer:**
   ```bash
   python3 xcursor-multisize.py
   ```

### What the script asks

| Prompt | What to enter | Example |
|--------|----------------|---------|
| Path to the cursor folder | Full path to the theme (or its `cursors/` folder) | `~/Downloads/GoldShip` |
| Theme folder name | Name under `~/.local/share/icons/` | `GoldShip` |
| Name in KDE | Label in System Settings | `Gold Ship` |
| Sizes | Comma-separated sizes, or press Enter | `24,32,48,64` |

Then confirm. The script:

1. Extracts frames with `xcur2png`
2. Scales them with ImageMagick
3. Rebuilds Xcursor files with `xcursorgen`
4. Installs into `~/.local/share/icons/<ThemeFolder>/`
5. Cleans temporary build folders and leftovers automatically

### Enable in KDE Plasma

1. Open **System Settings → Appearance → Cursors**
2. Select your theme
3. Choose a size (`24`, `32`, `48`, or `64`)
4. If the size control is stuck: switch to another theme, Apply, then switch back

Optional cache refresh:

```bash
kbuildsycoca6
```

### Notes

- Safe by default: if the install folder already exists, the script asks before overwriting.
- Temporary files created during conversion are removed after success (and on failure when possible).
- Do not commit or redistribute cursor artwork you do not have rights to use.

---

## Русский

### Зачем это нужно

Во многих темах курсора в самих Xcursor-файлах лежит только один размер (часто `32`).  
Правки `index.theme` недостаточно — KDE не может «придумать» недостающие размеры.  
Этот инструмент пересобирает курсоры с несколькими реальными размерами.

### Что нужно заранее

1. Папка темы курсора с каталогом `cursors/` внутри (можно указать сам `cursors/`):
   - Linux Xcursor, **или**
   - Windows-пакет `.ani` / `.cur` (можно с `install.inf`)
2. Установите необходимые пакеты (см. ниже).

### Установка и запуск

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/Mant1lka/xcursor-multisize.git
   cd xcursor-multisize
   ```

2. **Установите зависимости** (Arch / CachyOS):
   ```bash
   sudo pacman -S xcur2png xorg-xcursorgen imagemagick
   ```

3. **Запустите установщик:**
   ```bash
   python3 xcursor-multisize.py
   ```

### Что спросит скрипт

| Вопрос | Что вводить | Пример |
|--------|-------------|--------|
| Путь к папке с курсором | Полный путь к теме (или к её `cursors/`) | `~/Загрузки/GoldShip` |
| Название папки темы | Имя в `~/.local/share/icons/` | `GoldShip` |
| Имя в списке KDE | Как тема будет называться в настройках | `Gold Ship` |
| Размеры | Через запятую, либо просто Enter | `24,32,48,64` |

После подтверждения скрипт:

1. Достаёт кадры через `xcur2png`
2. Масштабирует их через ImageMagick
3. Собирает Xcursor заново через `xcursorgen`
4. Ставит тему в `~/.local/share/icons/<ПапкаТемы>/`
5. Сам удаляет временные папки и мусор после работы

### Включение в KDE Plasma

1. Откройте **Параметры системы → Оформление → Курсоры**
2. Выберите свою тему
3. Выберите размер (`24`, `32`, `48` или `64`)
4. Если слайдер размера «залип»: переключите тему на другую и обратно

По желанию обновите кэш:

```bash
kbuildsycoca6
```

### Важно

- Если папка установки уже есть, скрипт спросит перед перезаписью.
- Временные файлы сборки удаляются автоматически.
- Картинки курсоров в этот репозиторий не входят — используйте только те темы, на которые у вас есть права.

---

## License

MIT — applies to this tool only, not to cursor themes you convert.

## References

- [xcur2png](https://man.archlinux.org/man/xcur2png.1.en)
- [xcursorgen](https://man.archlinux.org/man/xcursorgen.1)
- [ArchWiki: Xcursorgen](https://wiki.archlinux.org/title/Xcursorgen)
