# Release Notes — Pages Counter

## v0.1.0 — Initial Release

### Overview

Pages Counter counts pages inside PDF files stored in `.tar.zst` compressed
archives or as loose `.pdf` files -- all without extracting archives to disk.

Built with a hexagonal (ports-and-adapters) architecture: core logic lives in
`services.py`, consumed independently by CLI and GUI presentation layers.

### Features

- **Streaming decompression** -- zstd + tar streamed in memory via
  `zstandard` library; archives are never fully loaded into RAM.
- **Disk-spilling PDF reads** -- large PDFs extracted from archives are
  written to temporary files via `NamedTemporaryFile`, not held in memory.
- **Parallel processing** -- `multiprocessing.Pool` with configurable worker
  count (`-j` / `--jobs`); defaults to CPU count.
- **Two processing modes**:
  - `archive` (default) -- recursively finds `.tar.zst` files, streams each
    archive, and counts PDFs inside.
  - `pdf` -- recursively finds `.pdf` files and counts pages directly.
- **Per-PDF details output** -- optional `--details FILE` flag writes a
  line-by-line breakdown of every PDF and its page count.
- **CLI** -- `argparse`-based interface with `tqdm` progress bar, per-file
  results, and a grand-totals summary.
- **GUI** -- CustomTkinter application with:
  - Folder or multi-file selection dialogs
  - Mode toggle (archives vs loose PDFs)
  - Configurable worker count
  - Start / Stop / Clear controls
  - Progress bar and live results table (dark-themed Treeview)
  - Optional per-PDF details file export
- **Unified entry point** (`main.py`) -- single command for both modes:
  `python main.py` for CLI, `python main.py --gui` for GUI.
- **PyInstaller build specs** -- ready-to-build standalone executables for
  both CLI (`count_pages.spec`) and GUI (`gui.spec`), including Windows
  frozen-support via `multiprocessing.freeze_support()`.

### Architecture

```
services.py   <-- domain logic (PyMuPDF, zstandard, tarfile)
    ^           no UI, no CLI, no framework imports
    |
cli.py        <-- argparse + multiprocessing + tqdm
gui.py        <-- CustomTkinter + threading
main.py       <-- unified entry point
```

### Dependencies

| Package       | Min Version | Purpose                              |
|---------------|-------------|--------------------------------------|
| PyMuPDF       | 1.25.0      | PDF page count                       |
| zstandard     | 0.25.0      | Streaming zstd decompression         |
| customtkinter | 5.2.0       | Modern Tkinter GUI theme             |
| tqdm          | 4.67.0      | CLI progress bar                     |

Dev dependencies: `basedpyright`, `bandit`, `ruff`, `nuitka`, `pyinstaller`.

### Requirements

- Python >= 3.13
- `uv` for dependency management

### Commit Log

```
8b14b5a refactor: move details file I/O to coordinator process
5c59c09 Added Licence file
7c54fe2 chore: add PyInstaller build specifications
fd42a88 feat: add unified entry point
463e7b0 feat: add GUI presentation layer
6d04b99 feat: add CLI presentation layer
e75d155 feat: implement core domain logic in services module
7eca158 docs: add project documentation and dependency manifest
0e63ed2 chore: add project scaffolding
```

### License

AGPL-3.0-or-later
