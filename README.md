# Pages Counter

Count pages in PDFs inside `.tar.zst` compressed archives or loose PDF files — without extracting to disk.

## Features

- **Streaming decompression** — zstd + tar streamed in memory, never fully loaded into RAM
- **Disk-spilling PDF reads** — large PDFs written to temp files, not held in memory
- **Parallel processing** — multiprocessing pool with configurable worker count
- **Two modes** — archive mode (`.tar.zst`) or loose PDF mode (`.pdf`)
- **CLI and GUI** — choose the interface you prefer
- **Per-PDF details** — optional output file listing every PDF and its page count

## Architecture

Hexagonal (ports-and-adapters) layout — core logic is isolated in `services.py`, consumed independently by the CLI and GUI layers:

```
services.py   ← domain logic (PyMuPDF, zstandard, tarfile)
    ↑           no UI, no CLI, no framework imports
    │
cli.py        ← argparse + multiprocessing + tqdm
gui.py        ← CustomTkinter + threading
main.py       ← unified entry point
```

## Requirements

- Python >= 3.13
- [uv](https://github.com/astral-sh/uv) for dependency management

## Installation

```bash
cd pages_counter
uv sync
```

## Usage

### CLI

```bash
# Archive mode (default) — count PDFs inside .tar.zst files
uv run cli.py /data/pdfs/

# Specify worker count
uv run cli.py /data/pdfs/ -j 16

# Loose PDF mode — count pages in .pdf files directly
uv run cli.py /data/pdfs/ --mode pdf

# Save per-PDF details to a file
uv run cli.py /data/pdfs/ --details out.txt
```

### GUI

```bash
uv run main.py --gui
```

### Unified entry point

```bash
uv run main.py              # CLI mode
uv run main.py --gui        # GUI mode
```

## Project structure

| File | Purpose |
|---|---|
| `services.py` | Core domain logic — archive/PDF processing, file discovery |
| `cli.py` | CLI presentation layer — argument parsing, multiprocessing, progress bar |
| `gui.py` | GUI presentation layer — CustomTkinter application |
| `main.py` | Unified entry point — dispatches to CLI or GUI |
| `count_pages.spec` | PyInstaller build spec — CLI executable |
| `gui.spec` | PyInstaller build spec — GUI executable (windowed) |
| `pyproject.toml` | Project metadata and dependencies |

## Type checking

```bash
uv run basedpyright services.py cli.py gui.py main.py
```

## Building standalone executables

Both the CLI and GUI can be frozen into a single self-contained executable with
PyInstaller (included in the `dev` dependency group, so `uv sync` installs it).

> **PyInstaller does not cross-compile.** Build *on* the OS you are targeting:
> build on Windows to get a `.exe`, build on Linux to get a Linux binary.

| Build | Spec | Output (Linux / Windows) |
|---|---|---|
| CLI | `count_pages.spec` | `dist/count_pages` / `dist/count_pages.exe` |
| GUI | `gui.spec` | `dist/PagesCounter` / `dist/PagesCounter.exe` |

### Windows

```bat
uv sync
uv run pyinstaller count_pages.spec   :: CLI  -> dist\count_pages.exe
uv run pyinstaller gui.spec           :: GUI  -> dist\PagesCounter.exe
```

The GUI build is windowed (no console window). Both entry points call
`multiprocessing.freeze_support()`, which is required for the worker pool to
run inside a frozen Windows executable.

If Windows Defender flags the compressed binary (UPX can trigger false
positives), set `upx=False` in the spec and rebuild.

### Linux

```bash
uv sync
uv run pyinstaller count_pages.spec   # CLI -> dist/count_pages
```

The **CLI** build works with any Python, including the default uv-managed one.

The **GUI** build is different: PyInstaller bundles the Tcl/Tk that ships with
the Python doing the build. uv-managed (`python-build-standalone`) interpreters
carry a Tk built *without* Xft, so a GUI frozen with them renders in a fallback
monospace bitmap font. Build the GUI with a **system Python whose Tk has Xft**:

```bash
uv venv --python /usr/bin/python3     # use the distro interpreter (Xft-enabled Tk)
uv sync
uv run pyinstaller gui.spec           # GUI -> dist/PagesCounter
```

### Verify the build

Launch the binary and run an actual count (not just open it) — the
multiprocessing path is only exercised once work starts.
