"""Pages Counter — unified entry point.

Run as CLI:  python main.py [args]
Run as GUI:  python main.py --gui
"""

from __future__ import annotations

import multiprocessing
import sys

def main() -> None:
    if "--gui" in sys.argv:
        from gui import main as gui_main  # noqa: PLC0414
        gui_main()
    else:
        from cli import main as cli_main  # noqa: PLC0414
        cli_main()


if __name__ == "__main__":
    # Required for multiprocessing in frozen (PyInstaller) builds on Windows,
    # where workers are spawned by re-running this executable.
    multiprocessing.freeze_support()
    main()
