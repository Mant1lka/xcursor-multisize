import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "xcursor-multisize.py"
spec = importlib.util.spec_from_file_location("xcursor_multisize", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ParserTests(unittest.TestCase):
    def test_parse_tab_delimited_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "cursor.conf"
            conf.write_text(
                "#size\txhot\tyhot\tPath to PNG image\tdelay\n"
                "32\t1\t2\t/tmp/Text Select_000.png\t83\n",
                encoding="utf-8",
            )
            frames = mod.parse_xcur2png_config(conf)

        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].nominal_size, 32)
        self.assertEqual(frames[0].xhot, 1)
        self.assertEqual(frames[0].yhot, 2)
        self.assertEqual(frames[0].image, Path("/tmp/Text Select_000.png"))
        self.assertEqual(frames[0].delay_ms, 83)

    def test_parse_static_cursor_without_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "cursor.conf"
            conf.write_text(
                "32\t3\t4\t/tmp/default.png\n",
                encoding="utf-8",
            )
            frames = mod.parse_xcur2png_config(conf)

        self.assertEqual(frames[0].delay_ms, None)

    def test_choose_closest_source_size(self):
        frames = [
            mod.Frame(24, 0, 0, Path("a"), None),
            mod.Frame(32, 0, 0, Path("b"), None),
            mod.Frame(48, 0, 0, Path("c"), None),
        ]
        self.assertEqual(mod.choose_source_group(frames, 30)[0].nominal_size, 32)
        self.assertEqual(mod.choose_source_group(frames, 46)[0].nominal_size, 48)

    def test_index_theme_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.theme"
            index.write_text(
                "[Icon Theme]\n"
                "Name=Old Theme\n"
                "Inherits=core\n",
                encoding="utf-8",
            )
            mod.set_index_theme(index, "New Theme", "A comment", "Adwaita")
            text = index.read_text(encoding="utf-8")

        self.assertIn("Name=New Theme", text)
        self.assertIn("Comment=A comment", text)
        self.assertIn("Inherits=Adwaita", text)
        self.assertIn("Directories=cursors", text)

    def test_sanitize_folder_name(self):
        self.assertEqual(mod.sanitize_folder_name("Gold Ship"), "Gold-Ship")
        self.assertEqual(mod.sanitize_folder_name("  HaruUrara  "), "HaruUrara")
        with self.assertRaises(ValueError):
            mod.sanitize_folder_name("???")

    def test_resolve_theme_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyTheme"
            cursors = root / "cursors"
            cursors.mkdir(parents=True)
            self.assertEqual(mod.resolve_theme_root(root), root.resolve())
            self.assertEqual(mod.resolve_theme_root(cursors), root.resolve())

    def test_cleanup_removes_backups_and_build_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = root / "MyTheme"
            keep.mkdir()
            junk_build = root / ".MyTheme.build-abc"
            junk_build.mkdir()
            junk_backup = root / "MyTheme.backup-20260101-000000"
            junk_backup.mkdir()
            junk_old = root / ".MyTheme.cursors-original"
            junk_old.mkdir()
            other = root / "OtherTheme"
            other.mkdir()

            removed = mod.cleanup_junk(root, theme_names={"MyTheme"})

            self.assertTrue(keep.exists())
            self.assertTrue(other.exists())
            self.assertFalse(junk_build.exists())
            self.assertFalse(junk_backup.exists())
            self.assertFalse(junk_old.exists())
            self.assertEqual(len(removed), 3)


if __name__ == "__main__":
    unittest.main()
