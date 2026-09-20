#!/usr/bin/env python3
"""Interactive installer: make an Xcursor theme usable in KDE with multiple sizes.

Supports Linux Xcursor themes and Windows .cur/.ani packs (with optional install.inf).
Requires: xcur2png, xcursorgen, ImageMagick (magick).
"""

from __future__ import annotations

import csv
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

VERSION = "1.1.0"
DEFAULT_SIZES = (24, 32, 48, 64)
ICONS_DIR = Path.home() / ".local" / "share" / "icons"

# Windows scheme roles (install.inf order) -> Linux Xcursor names (first is canonical).
WINDOWS_ROLE_ALIASES: dict[str, list[str]] = {
    "arrow": ["left_ptr", "default", "arrow", "top_left_arrow", "left-arrow"],
    "help": ["help", "left_ptr_help", "question_arrow", "whats_this"],
    "working": ["left_ptr_watch", "progress", "half-busy"],
    "wait": ["wait", "watch"],
    "crosshair": ["crosshair", "cross", "tcross", "cross_reverse", "diamond_cross"],
    "text": ["xterm", "text", "ibeam"],
    "pen": ["pencil", "draft"],
    "unavailable": ["circle", "crossed_circle", "forbidden", "not-allowed", "no-drop"],
    "size_ns": ["sb_v_double_arrow", "v_double_arrow", "ns-resize", "row-resize", "split_v", "size_ver"],
    "size_ew": ["sb_h_double_arrow", "h_double_arrow", "ew-resize", "col-resize", "split_h", "size_hor"],
    "size_nwse": ["bd_double_arrow", "nwse-resize", "size_fdiag", "bottom_left_corner", "top_right_corner"],
    "size_nesw": ["fd_double_arrow", "nesw-resize", "size_bdiag", "bottom_right_corner", "top_left_corner"],
    "move": ["fleur", "size_all", "all-scroll", "move", "grabbing", "closedhand", "dnd-move"],
    "up_arrow": ["center_ptr", "up-arrow", "sb_up_arrow", "right_ptr"],
    "link": ["pointing_hand", "hand2", "hand1", "hand", "pointer"],
    "location": ["pin"],
    "person": ["person"],
}

WINDOWS_SCHEME_ROLES = list(WINDOWS_ROLE_ALIASES.keys())

FILENAME_ROLE_HINTS: dict[str, str] = {
    "normal": "arrow",
    "arrow": "arrow",
    "pointer": "arrow",
    "help": "help",
    "working": "working",
    "appstarting": "working",
    "busy": "wait",
    "wait": "wait",
    "precision": "crosshair",
    "crosshair": "crosshair",
    "cross": "crosshair",
    "text": "text",
    "ibeam": "text",
    "handwriting": "pen",
    "pen": "pen",
    "unavailable": "unavailable",
    "no": "unavailable",
    "vertical": "size_ns",
    "horiz": "size_ew",
    "horizontal": "size_ew",
    "diagonal1": "size_nwse",
    "diagonal2": "size_nesw",
    "move": "move",
    "alternate": "up_arrow",
    "uparrow": "up_arrow",
    "link": "link",
    "hand": "link",
    "person": "person",
    "pin": "location",
}


@dataclass(frozen=True)
class Frame:
    nominal_size: int
    xhot: int
    yhot: int
    image: Path
    delay_ms: int | None


@dataclass(frozen=True)
class PngFrame:
    width: int
    height: int
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
    text = replace_or_append("Directories", "cursors", text)
    index_theme.write_text(text.rstrip() + "\n", encoding="utf-8")


def file_magic(path: Path, size: int = 12) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def is_xcursor_file(path: Path) -> bool:
    try:
        return file_magic(path, 4) == b"Xcur"
    except OSError:
        return False


def is_windows_cursor_file(path: Path) -> bool:
    try:
        magic = file_magic(path, 12)
    except OSError:
        return False
    if magic[:4] == b"\0\0\x02\0":
        return True
    return magic[:4] == b"RIFF" and magic[8:12] == b"ACON"


def list_cursor_files(cursors: Path) -> list[Path]:
    return sorted(
        (p for p in cursors.iterdir() if p.is_file() and not p.is_symlink()),
        key=lambda p: p.name.casefold(),
    )


def detect_theme_kind(theme: Path) -> str:
    cursors = theme / "cursors"
    files = list_cursor_files(cursors)
    if not files:
        raise RuntimeError(f"В {cursors} нет файлов курсоров")
    win = sum(1 for p in files if is_windows_cursor_file(p))
    xcur = sum(1 for p in files if is_xcursor_file(p))
    if win and not xcur:
        return "windows"
    if xcur:
        return "xcursor"
    # Extension fallback for odd packs.
    if any(p.suffix.lower() in {".ani", ".cur"} for p in files):
        return "windows"
    return "unknown"


def parse_cur_hotspots(blob: bytes) -> list[tuple[int, int, int, int]]:
    """Return list of (width, height, xhot, yhot) for each CUR image."""
    if len(blob) < 6 or blob[:4] != b"\0\0\x02\0":
        raise RuntimeError("Файл не похож на Windows .cur")
    _reserved, _ico_type, count = struct.unpack_from("<HHH", blob, 0)
    offset = 6
    entries: list[tuple[int, int, int, int]] = []
    for _ in range(count):
        width, height, _palette, _reserved2, hx, hy, _size, _file_offset = struct.unpack_from(
            "<BBBBHHII", blob, offset
        )
        entries.append((width or 256, height or 256, hx, hy))
        offset += 16
    return entries


def jiffies_to_ms(jiffies: int) -> int:
    return max(1, int(round(jiffies * 1000 / 60)))


def extract_ani_cur_frames(blob: bytes) -> list[tuple[bytes, int]]:
    """Return ordered list of (cur_blob, delay_ms) from an .ani file."""
    if not (blob[:4] == b"RIFF" and blob[8:12] == b"ACON"):
        raise RuntimeError("Файл не похож на Windows .ani")

    chunk_hdr = struct.Struct("<4sI")
    anih = struct.Struct("<IIIIIIIII")
    icons: list[bytes] = []
    display_rate = 5
    frame_count = 0
    step_count = 0
    rates: list[int] | None = None
    order: list[int] | None = None

    offset = 12
    while offset + 8 <= len(blob):
        name, size = chunk_hdr.unpack(blob[offset : offset + 8])
        offset += 8
        data_end = offset + size
        if data_end > len(blob):
            break
        if name == b"anih" and size >= anih.size:
            (
                _hdr_size,
                frame_count,
                step_count,
                _width,
                _height,
                _bit_count,
                _planes,
                display_rate,
                flags,
            ) = anih.unpack(blob[offset : offset + anih.size])
            if not flags & 0x1:
                raise RuntimeError("ANI без ICON-кадров не поддерживается")
        elif name == b"LIST" and blob[offset : offset + 4] == b"fram":
            pos = offset + 4
            while pos + 8 <= data_end:
                cname, csize = chunk_hdr.unpack(blob[pos : pos + 8])
                pos += 8
                if cname == b"icon":
                    icons.append(blob[pos : pos + csize])
                pos += csize
                if pos & 1:
                    pos += 1
        elif name == b"rate":
            rates = [value for (value,) in struct.iter_unpack("<I", blob[offset:data_end])]
        elif name == b"seq ":
            order = [value for (value,) in struct.iter_unpack("<I", blob[offset:data_end])]
        offset = data_end + (data_end & 1)

    if not icons:
        raise RuntimeError("В ANI нет кадров icon")
    if order is None:
        order = list(range(len(icons) if frame_count <= 0 else frame_count))
    if rates is None:
        rates = [display_rate] * len(order)
    if len(order) != len(rates):
        raise RuntimeError("В ANI не совпадают seq/rate")

    frames: list[tuple[bytes, int]] = []
    for index, delay in zip(order, rates):
        if index < 0 or index >= len(icons):
            raise RuntimeError(f"В ANI неверный индекс кадра: {index}")
        frames.append((icons[index], jiffies_to_ms(delay)))
    return frames


def cur_blob_to_png_frames(cur_blob: bytes, work: Path, prefix: str, delay_ms: int | None) -> list[PngFrame]:
    hotspots = parse_cur_hotspots(cur_blob)
    cur_path = work / f"{prefix}.cur"
    cur_path.write_bytes(cur_blob)
    pattern = work / f"{prefix}-%02d.png"
    run(["magick", str(cur_path), "+adjoin", str(pattern)])
    pngs = sorted(work.glob(f"{prefix}-*.png"))
    if not pngs:
        # Single-image fallback.
        single = work / f"{prefix}.png"
        run(["magick", str(cur_path), str(single)])
        pngs = [single]
    if len(pngs) != len(hotspots):
        # Some CUR variants expose one raster; keep first hotspot.
        if len(pngs) == 1 and hotspots:
            hotspots = [hotspots[0]]
        else:
            raise RuntimeError(
                f"Число PNG ({len(pngs)}) не совпало с числом hotspot ({len(hotspots)}) в {prefix}"
            )

    frames: list[PngFrame] = []
    for png, (width, height, xhot, yhot) in zip(pngs, hotspots):
        # Prefer actual PNG geometry when CUR header lied.
        identify = run(["magick", "identify", "-format", "%w %h", str(png)])
        parts = identify.stdout.strip().split()
        if len(parts) == 2:
            width, height = int(parts[0]), int(parts[1])
        frames.append(PngFrame(width, height, xhot, yhot, png, delay_ms))
    return frames


def windows_cursor_to_png_frames(source: Path, work: Path) -> list[PngFrame]:
    blob = source.read_bytes()
    work.mkdir(parents=True, exist_ok=True)
    if blob[:4] == b"RIFF" and blob[8:12] == b"ACON":
        frames: list[PngFrame] = []
        for index, (cur_blob, delay_ms) in enumerate(extract_ani_cur_frames(blob)):
            frames.extend(cur_blob_to_png_frames(cur_blob, work, f"ani-{index:04d}", delay_ms))
        return frames
    if blob[:4] == b"\0\0\x02\0":
        return cur_blob_to_png_frames(blob, work, "cur", None)
    raise RuntimeError(f"Неизвестный формат Windows-курсора: {source.name}")


def write_xcursor_from_png_frames(frames: list[PngFrame], output: Path) -> None:
    if not frames:
        raise RuntimeError("Нет кадров для сборки Xcursor")
    config = output.parent / f".{output.name}.conf"
    with config.open("w", encoding="utf-8") as handle:
        for frame in frames:
            size = max(frame.width, frame.height)
            handle.write(f"{size}\t{frame.xhot}\t{frame.yhot}\t{frame.image}")
            if frame.delay_ms is not None:
                handle.write(f"\t{frame.delay_ms}")
            handle.write("\n")
    run(["xcursorgen", str(config), str(output)])
    config.unlink(missing_ok=True)


def parse_inf_scheme(inf_path: Path) -> tuple[str | None, dict[str, Path]]:
    """Parse Windows install.inf into (scheme_name, role -> cursor file)."""
    text = inf_path.read_text(encoding="utf-8", errors="replace")
    strings: dict[str, str] = {}
    in_strings = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_strings = line.lower() == "[strings]"
            continue
        if in_strings and "=" in line:
            key, value = line.split("=", 1)
            strings[key.strip().casefold()] = value.strip().strip('"')

    def expand(value: str) -> str:
        def repl(match: re.Match[str]) -> str:
            key = match.group(1).casefold()
            if not key:
                return "%"
            return strings.get(key, match.group(0))

        return re.sub(r"%(\w*)%", repl, value)

    scheme_name = strings.get("scheme_name")
    scheme_line = None
    for raw in text.splitlines():
        low = raw.strip().casefold()
        if "control panel\\cursors\\schemes" in low and "," in raw:
            scheme_line = raw.strip()
            break
    if not scheme_line:
        return scheme_name, {}

    try:
        parsed = next(csv.reader(StringIO(scheme_line), skipinitialspace=True))
    except csv.Error:
        return scheme_name, {}
    if len(parsed) < 5:
        return scheme_name, {}

    value = expand(parsed[4].strip().strip('"'))
    cursor_paths = [part.strip() for part in value.split(",")]
    parent = inf_path.parent
    files = {p.name.casefold(): p for p in parent.iterdir() if p.is_file()}
    role_map: dict[str, Path] = {}
    for role, filename in zip(WINDOWS_SCHEME_ROLES, cursor_paths):
        if not filename:
            continue
        basename = Path(filename.replace("\\", "/")).name
        path = files.get(basename.casefold())
        if path is not None:
            role_map[role] = path
    return scheme_name, role_map


def guess_role_from_filename(path: Path) -> str | None:
    stem = path.stem.casefold()
    if stem in FILENAME_ROLE_HINTS:
        return FILENAME_ROLE_HINTS[stem]
    for key, role in FILENAME_ROLE_HINTS.items():
        if key in stem:
            return role
    return None


def find_install_inf(theme: Path) -> Path | None:
    for candidate in (theme / "cursors" / "install.inf", theme / "install.inf"):
        if candidate.is_file():
            return candidate
    return None


def convert_windows_theme(theme: Path, work_root: Path) -> tuple[Path, str | None]:
    """Convert Windows .ani/.cur theme into a temporary Linux Xcursor theme."""
    cursors_dir = theme / "cursors"
    out_theme = work_root / "windows-linux"
    out_cursors = out_theme / "cursors"
    out_cursors.mkdir(parents=True)

    scheme_name: str | None = None
    role_files: dict[str, Path] = {}
    inf = find_install_inf(theme)
    if inf is not None:
        scheme_name, role_files = parse_inf_scheme(inf)

    if not role_files:
        for path in list_cursor_files(cursors_dir):
            if not is_windows_cursor_file(path):
                continue
            role = guess_role_from_filename(path)
            if role and role not in role_files:
                role_files[role] = path

    if "arrow" not in role_files:
        # Last resort: first windows cursor becomes the default pointer.
        for path in list_cursor_files(cursors_dir):
            if is_windows_cursor_file(path):
                role_files["arrow"] = path
                break

    if "arrow" not in role_files:
        raise RuntimeError(
            "Не найден основной курсор Windows (Arrow/Normal).\n"
            "Нужен .ani/.cur для указателя или install.inf."
        )

    print(f"Обнаружена Windows-тема (.ani/.cur). Конвертация в Xcursor…")
    for role, source in role_files.items():
        aliases = WINDOWS_ROLE_ALIASES.get(role)
        if not aliases:
            continue
        print(f"  {source.name} → {aliases[0]}")
        frame_work = work_root / "winframes" / role
        frames = windows_cursor_to_png_frames(source, frame_work)
        canonical = out_cursors / aliases[0]
        write_xcursor_from_png_frames(frames, canonical)
        for alias in aliases[1:]:
            link = out_cursors / alias
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(aliases[0])

    set_index_theme(
        out_theme / "index.theme",
        scheme_name or theme.name,
        "Converted from Windows cursor theme",
        None,
    )
    return out_theme, scheme_name


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

    details = (result.stderr or result.stdout or "").strip()
    if result.returncode < 0 or not config.exists() or config.stat().st_size == 0:
        message = f"xcur2png не смог обработать {source.name}"
        if details:
            message += f"\n{details}"
        if is_windows_cursor_file(source):
            message += (
                "\nЭто Windows-курсор (.ani/.cur). Скрипт должен был конвертировать "
                "тему заранее — возможно, файл попал в обход конвертации."
            )
        raise RuntimeError(message)

    frames = parse_xcur2png_config(config)
    return frames


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
    print("Поддерживаются Linux Xcursor и Windows .ani/.cur.")
    print()

    check_dependencies()

    while True:
        raw = ask("Путь к папке с курсором")
        try:
            source = resolve_theme_root(Path(raw))
            break
        except RuntimeError as exc:
            print(f"Ошибка: {exc}")

    kind = detect_theme_kind(source)
    if kind == "unknown":
        raise RuntimeError(
            "Не удалось определить формат курсоров.\n"
            "Нужны Linux Xcursor-файлы или Windows .ani/.cur."
        )

    suggested_name = source.name
    suggested_display = read_index_name(source)
    if kind == "windows":
        inf = find_install_inf(source)
        if inf is not None:
            scheme_name, _roles = parse_inf_scheme(inf)
            if scheme_name:
                suggested_display = scheme_name
                suggested_name = sanitize_folder_name(scheme_name.split("_by")[0].split()[0])

    default_folder = sanitize_folder_name(suggested_name)
    while True:
        try:
            folder_name = sanitize_folder_name(
                ask("Название папки темы в системе", default_folder)
            )
            break
        except ValueError as exc:
            print(f"Ошибка: {exc}")

    default_display = suggested_display or folder_name.replace("-", " ")
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
    in_place = output == source.resolve() and kind == "xcursor"

    print()
    print(f"Формат:       {'Windows (.ani/.cur)' if kind == 'windows' else 'Linux Xcursor'}")
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

    convert_tmp: Path | None = None
    try:
        process_source = source
        if kind == "windows":
            if in_place:
                raise RuntimeError("Windows-тему нельзя обновлять in-place; выберите другое имя папки")
            convert_tmp = Path(
                tempfile.mkdtemp(prefix=f".{folder_name}.winconv-", dir=output.parent)
            )
            process_source, _scheme = convert_windows_theme(source, convert_tmp)

        process_theme(
            process_source,
            output,
            sizes,
            force=force,
            in_place=in_place,
            name=display_name,
            comment=f"Multi-size Xcursor theme ({', '.join(map(str, sizes))} px)",
            inherits=None,
        )
    finally:
        if convert_tmp is not None:
            remove_path(convert_tmp)

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
            "Поддерживаются:\n"
            "  • Linux Xcursor-темы\n"
            "  • Windows-пакеты .ani/.cur (в т.ч. с install.inf)\n\n"
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
