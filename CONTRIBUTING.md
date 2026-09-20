# Contributing

Issues and pull requests are welcome.

- Keep the default experience interactive (terminal prompts).
- Keep dependencies light (`xcur2png`, `xcursorgen`, ImageMagick).
- Do not add cursor themes or extracted PNG frames to the repository.

Before opening a PR:

```bash
python3 -m py_compile xcursor-multisize.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
