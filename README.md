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
| `count_pages.spec` | PyInstaller build specification |
| `pyproject.toml` | Project metadata and dependencies |

## Type checking

```bash
uv run basedpyright services.py cli.py gui.py main.py
```

## Building a standalone executable

```bash
uv run pyinstaller count_pages.spec
```

The resulting binary is in `dist/count_pages`.
