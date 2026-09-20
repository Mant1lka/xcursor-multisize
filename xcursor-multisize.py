#!/usr/bin/env python3
"""Interactive installer: make an Xcursor theme usable in KDE with multiple sizes.

Requires: xcur2png, xcursorgen, ImageMagick (magick).
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

VERSION = "1.0.0"
DEFAULT_SIZES = (24, 32, 48, 64)
ICONS_DIR = Path.home() / ".local" / "share" / "icons"


@dataclass(frozen=True)
class Frame:
    nominal_size: int
    xhot: int
    yhot: int
    image: Path
    delay_ms: int | None


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Не найдена команда: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        message = f"Команда завершилась с ошибкой ({exc.returncode}): {' '.join(cmd)}"
        if details:
            message += f"\n{details}"
        raise RuntimeError(message) from exc


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def check_dependencies() -> None:
    missing = [cmd for cmd in ("xcur2png", "xcursorgen", "magick") if not command_exists(cmd)]
    if missing:
        raise RuntimeError(
            "Не хватает программ: "
            + ", ".join(missing)
            + "\nУстановите: sudo pacman -S xcur2png xorg-xcursorgen imagemagick"
        )


def ask(prompt: str, default: str | None = None) -> str:
    """Ask the user in the terminal. Empty input keeps the default."""
    if default is None:
        suffix = ": "
    else:
        suffix = f" [{default}]: "
    while True:
        try:
            value = input(prompt + suffix).strip()
        except EOFError as exc:
            raise RuntimeError("Ввод прерван.") from exc
        if value:
            return value
        if default is not None:
            return default
        print("Нужно что-то ввести.")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        value = ask(f"{prompt} ({hint})", "y" if default else "n").casefold()
        if value in {"y", "yes", "д", "да"}:
            return True
        if value in {"n", "no", "н", "нет"}:
            return False
        print("Введите y/да или n/нет.")


def parse_sizes(value: str) -> tuple[int, ...]:
    try:
        sizes = tuple(sorted({int(part.strip()) for part in value.split(",") if part.strip()}))
    except ValueError as exc:
        raise ValueError("Размеры должны быть числами через запятую, например 24,32,48,64") from exc
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("Размеры должны быть положительными числами")
    return sizes


def sanitize_folder_name(name: str) -> str:
    cleaned = name.strip().replace(" ", "-")
    cleaned = re.sub(r"[^\w.+-]+", "-", cleaned, flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip(".-")
    if not cleaned:
        raise ValueError("Название папки пустое или состоит только из недопустимых символов")
    return cleaned


def resolve_theme_root(path: Path) -> Path:
    """Accept a theme root or a cursors/ directory."""
    path = path.expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"Путь не найден: {path}")
    if not path.is_dir():
        raise RuntimeError(f"Это не папка: {path}")
    if (path / "cursors").is_dir():
        return path
    if path.name == "cursors" and path.is_dir():
        return path.parent
    raise RuntimeError(
        f"В папке нет каталога cursors/: {path}\n"
        "Укажите папку темы (внутри неё должен быть cursors/) "
        "или сам каталог cursors/."
    )


def read_index_name(theme: Path) -> str | None:
    index = theme / "index.theme"
    if not index.is_file():
        return None
    for line in index.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("name="):
            value = line.split("=", 1)[1].strip()
            return value or None
    return None


def set_index_theme(
    index_theme: Path,
    name: str | None,
    comment: str | None,
    inherits: str | None,
) -> None:
    text = index_theme.read_text(encoding="utf-8") if index_theme.exists() else "[Icon Theme]\n"
    if "[Icon Theme]" not in text:
        text = "[Icon Theme]\n" + text

    def replace_or_append(key: str, value: str, content: str) -> str:
        pattern = re.compile(rf"(?mi)^{re.escape(key)}\s*=.*$")
        replacement = f"{key}={value}"
        if pattern.search(content):
            return pattern.sub(replacement, content, count=1)
        marker = "[Icon Theme]"
        pos = content.find(marker) + len(marker)
        return content[:pos] + "\n" + replacement + content[pos:]

    if name is not None:
        text = replace_or_append("Name", name, text)
    if comment is not None:
        text = replace_or_append("Comment", comment, text)
    if inherits is not None:
        text = replace_or_append("Inherits", inherits, text)

    # Help Plasma / icon theme tooling notice available cursor sizes.
    text = replace_or_append("Directories", "cursors", text)

    index_theme.write_text(text.rstrip() + "\n", encoding="utf-8")


def parse_xcur2png_config(config: Path) -> list[Frame]:
    frames: list[Frame] = []
    for line_no, raw in enumerate(config.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) not in (4, 5):
            parts = line.split(maxsplit=4)
        if len(parts) not in (4, 5):
            raise RuntimeError(f"Не разобрать {config.name}:{line_no}: {raw!r}")
        try:
            nominal_size = int(parts[0])
            xhot = int(parts[1])
            yhot = int(parts[2])
        except ValueError as exc:
            raise RuntimeError(f"Неверные числа в {config.name}:{line_no}: {raw!r}") from exc
        image = Path(parts[3])
        delay = None
        if len(parts) == 5:
            try:
                delay = int(parts[4])
            except ValueError as exc:
                raise RuntimeError(f"Неверная задержка в {config.name}:{line_no}: {raw!r}") from exc
        frames.append(Frame(nominal_size, xhot, yhot, image, delay))
    if not frames:
        raise RuntimeError(f"В {config} нет кадров")
    return frames


def choose_source_group(frames: list[Frame], target_size: int) -> list[Frame]:
    groups: dict[int, list[Frame]] = {}
    for frame in frames:
        groups.setdefault(frame.nominal_size, []).append(frame)
    source_size = min(groups, key=lambda size: abs(math.log(target_size / size)))
    return groups[source_size]


def extract_cursor(source: Path, work: Path) -> list[Frame]:
    png_dir = work / "png"
    png_dir.mkdir(parents=True)
    config = work / "cursor.conf"
    try:
        result = subprocess.run(
            ["xcur2png", "-q", "-d", str(png_dir), "-c", str(config), str(source)],
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Не найдена команда: xcur2png") from exc

    if result.returncode < 0:
        details = (result.stderr or result.stdout or "").strip()
        message = f"xcur2png не смог обработать {source.name}"
        if details:
            message += f"\n{details}"
        raise RuntimeError(message)
    if not config.exists():
        details = (result.stderr or result.stdout or "").strip()
        message = f"xcur2png не создал конфиг для {source.name}"
        if details:
            message += f"\n{details}"
        raise RuntimeError(message)
    return parse_xcur2png_config(config)


def scale_frame(frame: Frame, target_size: int, output: Path) -> tuple[int, int]:
    scale = target_size / frame.nominal_size
    xhot = max(0, int(math.floor(frame.xhot * scale + 0.5)))
    yhot = max(0, int(math.floor(frame.yhot * scale + 0.5)))
    percent = scale * 100.0
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "magick",
        str(frame.image),
        "-filter", "Lanczos",
        "-resize", f"{percent:.8f}%",
        str(output),
    ])
    return xhot, yhot


def build_cursor(source: Path, output: Path, sizes: tuple[int, ...], work: Path) -> None:
    frames = extract_cursor(source, work)
    config = work / "combined.conf"
    with config.open("w", encoding="utf-8") as handle:
        for size in sizes:
            source_frames = choose_source_group(frames, size)
            for index, frame in enumerate(source_frames):
                png = work / f"size-{size}" / f"frame-{index:04d}.png"
                xhot, yhot = scale_frame(frame, size, png)
                handle.write(f"{size}\t{xhot}\t{yhot}\t{png}")
                if frame.delay_ms is not None:
                    handle.write(f"\t{frame.delay_ms}")
                handle.write("\n")
    run(["xcursorgen", str(config), str(output)])


def is_script_junk_name(name: str, theme_names: set[str] | None = None) -> bool:
    """Detect temporary/backup leftovers created by this tool."""
    if name.startswith(".") and ".build-" in name:
        if theme_names is None:
            return True
        return any(name.startswith(f".{theme}.build-") for theme in theme_names)
    if name.startswith(".") and ".cursors-original" in name:
        if theme_names is None:
            return True
        return any(
            name == f".{theme}.cursors-original"
            or name.startswith(f".{theme}.cursors-original-")
            for theme in theme_names
        )
    if ".backup-" in name:
        if theme_names is None:
            return True
        return any(name.startswith(f"{theme}.backup-") for theme in theme_names)
    return False


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def cleanup_junk(*directories: Path, theme_names: set[str] | None = None) -> list[Path]:
    """Remove build temps, cursor swap leftovers, and backup copies."""
    removed: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        try:
            directory = directory.expanduser().resolve()
        except OSError:
            continue
        if not directory.is_dir() or directory in seen:
            continue
        seen.add(directory)
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not is_script_junk_name(entry.name, theme_names):
                continue
            remove_path(entry)
            if not entry.exists():
                removed.append(entry)
    return removed


def process_theme(
    input_theme: Path,
    output_theme: Path,
    sizes: tuple[int, ...],
    *,
    force: bool,
    in_place: bool,
    name: str | None,
    comment: str | None,
    inherits: str | None,
) -> None:
    cursors = input_theme / "cursors"
    if not cursors.is_dir():
        raise RuntimeError(f"Нет каталога cursors/: {cursors}")

    if in_place and output_theme != input_theme:
        raise RuntimeError("Внутренняя ошибка: при in-place выход должен совпадать со входом")
    if not in_place and output_theme.exists():
        if not force:
            raise RuntimeError(f"Папка уже существует: {output_theme}")
        shutil.rmtree(output_theme)

    output_theme.parent.mkdir(parents=True, exist_ok=True)
    # Drop leftovers from earlier runs before creating a new build dir.
    cleanup_junk(
        output_theme.parent,
        input_theme.parent,
        theme_names={input_theme.name, output_theme.name},
    )

    temp_root = Path(tempfile.mkdtemp(prefix=f".{output_theme.name}.build-", dir=output_theme.parent))
    staged_cursors = temp_root / "cursors"
    staged_cursors.mkdir()

    try:
        regular_files = sorted(
            (p for p in cursors.iterdir() if p.is_file() and not p.is_symlink()),
            key=lambda p: p.name.casefold(),
        )
        if not regular_files:
            raise RuntimeError(f"В {cursors} нет обычных файлов курсоров")

        print()
        print(f"Источник:  {input_theme}")
        print(f"Установка: {output_theme}")
        print(f"Размеры:   {', '.join(map(str, sizes))} px")
        print(f"Файлов:    {len(regular_files)}")
        print()

        for number, source in enumerate(regular_files, 1):
            print(f"[{number}/{len(regular_files)}] {source.name}")
            work = temp_root / "work" / f"{number:04d}"
            build_cursor(source, staged_cursors / source.name, sizes, work)

        for entry in cursors.iterdir():
            if entry.is_symlink():
                (staged_cursors / entry.name).symlink_to(os.readlink(entry))

        if in_place:
            old_cursors = temp_root.with_name(f".{input_theme.name}.cursors-original")
            suffix = 1
            while old_cursors.exists() or old_cursors.is_symlink():
                old_cursors = temp_root.with_name(
                    f".{input_theme.name}.cursors-original-{suffix}"
                )
                suffix += 1

            cursors.rename(old_cursors)
            try:
                staged_cursors.rename(cursors)
                set_index_theme(input_theme / "index.theme", name, comment, inherits)
            except Exception:
                if cursors.exists() or cursors.is_symlink():
                    if cursors.is_dir() and not cursors.is_symlink():
                        shutil.rmtree(cursors)
                    else:
                        cursors.unlink()
                old_cursors.rename(cursors)
                raise
            else:
                remove_path(old_cursors)
                remove_path(temp_root)
                return

        output_theme.mkdir(parents=True, exist_ok=True)
        for entry in input_theme.iterdir():
            if entry.name == "cursors":
                continue
            target = output_theme / entry.name
            if entry.is_symlink():
                target.symlink_to(os.readlink(entry))
            elif entry.is_dir():
                shutil.copytree(entry, target, symlinks=True)
            else:
                shutil.copy2(entry, target)
        staged_cursors.rename(output_theme / "cursors")
        set_index_theme(output_theme / "index.theme", name, comment, inherits)
        remove_path(temp_root)
    except Exception:
        remove_path(temp_root)
        cleanup_junk(
            output_theme.parent,
            input_theme.parent,
            theme_names={input_theme.name, output_theme.name},
        )
        raise
    else:
        removed = cleanup_junk(
            output_theme.parent,
            input_theme.parent,
            ICONS_DIR,
            theme_names={input_theme.name, output_theme.name},
        )
        if removed:
            print(f"Очищено временных объектов: {len(removed)}")


def refresh_kde_cache() -> None:
    for cmd in ("kbuildsycoca6", "kbuildsycoca5"):
        if command_exists(cmd):
            try:
                subprocess.run([cmd], check=False, capture_output=True, text=True)
                print(f"Кэш KDE обновлён ({cmd}).")
            except OSError:
                pass
            return


def interactive_wizard() -> int:
    print(f"xcursor-multisize {VERSION}")
    print("Установит тему курсора в KDE с несколькими размерами.")
    print()

    check_dependencies()

    while True:
        raw = ask("Путь к папке с курсором")
        try:
            source = resolve_theme_root(Path(raw))
            break
        except RuntimeError as exc:
            print(f"Ошибка: {exc}")

    default_folder = sanitize_folder_name(source.name)
    while True:
        try:
            folder_name = sanitize_folder_name(
                ask("Название папки темы в системе", default_folder)
            )
            break
        except ValueError as exc:
            print(f"Ошибка: {exc}")

    default_display = read_index_name(source) or folder_name.replace("-", " ")
    display_name = ask("Имя темы в списке KDE", default_display)

    while True:
        sizes_raw = ask("Размеры курсора через запятую", "24,32,48,64")
        try:
            sizes = parse_sizes(sizes_raw)
            break
        except ValueError as exc:
            print(f"Ошибка: {exc}")

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    output = (ICONS_DIR / folder_name).resolve()
    in_place = output == source.resolve()

    print()
    print(f"Источник:     {source}")
    print(f"Установка в:  {output}")
    print(f"Имя в KDE:    {display_name}")
    print(f"Размеры:      {', '.join(map(str, sizes))} px")
    if in_place:
        print("Режим:        обновление уже установленной темы")
    print()

    if not ask_yes_no("Продолжить?", default=True):
        print("Отменено.")
        return 0

    force = False
    if not in_place and output.exists():
        if not ask_yes_no(f"Папка {output} уже есть. Перезаписать?", default=False):
            print("Отменено.")
            return 0
        force = True

    process_theme(
        source,
        output,
        sizes,
        force=force,
        in_place=in_place,
        name=display_name,
        comment=f"Multi-size Xcursor theme ({', '.join(map(str, sizes))} px)",
        inherits=None,
    )

    refresh_kde_cache()

    print()
    print("Готово.")
    print(f"Тема установлена: {output}")
    print()
    print("Дальше в KDE:")
    print("  1. Параметры системы → Оформление → Курсоры")
    print(f"  2. Выберите «{display_name}»")
    print("  3. Выберите размер (24 / 32 / 48 / 64)")
    print("  4. Если размер не появляется — переключите тему туда-обратно и снова выберите эту")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["-h"], ["--help"]):
        print(
            "Использование:\n"
            "  python3 xcursor-multisize.py\n\n"
            "Скрипт спросит путь к папке курсора и название темы,\n"
            "соберёт размеры 24/32/48/64 и установит тему в:\n"
            f"  {ICONS_DIR}/<название>\n\n"
            "Нужны: xcur2png, xcursorgen, magick\n"
            "Установка на Arch/CachyOS:\n"
            "  sudo pacman -S xcur2png xorg-xcursorgen imagemagick"
        )
        return 0
    if args in (["-V"], ["--version"]):
        print(VERSION)
        return 0
    if args:
        print(
            "Этот скрипт работает в интерактивном режиме.\n"
            "Просто запустите: python3 xcursor-multisize.py\n"
            "Справка: python3 xcursor-multisize.py --help",
            file=sys.stderr,
        )
        return 2

    try:
        return interactive_wizard()
    except KeyboardInterrupt:
        print("\nОтменено.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
