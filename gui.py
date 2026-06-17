#!/usr/bin/env python3
"""GUI presentation layer for PDF page counting.

CustomTkinter application with drag-and-drop, progress bar, and results table.
All core logic is delegated to services.py.
"""

from __future__ import annotations

import multiprocessing
import os
import queue
import sys
import threading
import time
from functools import partial


from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk  # type: ignore[import-untyped]

from services import (
    FileResult,
    ProcessingMode,
    find_files,
    init_details_file,
    process_archive,
    process_pdf,
    verify_pymupdf,
)


# Message queue: (tag, payload...) consumed with explicit typing in _poll_queue
_MsgQueue = queue.Queue


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

def _run_counting(
    files: list[str],
    num_workers: int,
    details_file_path: str | None,
    msg_queue: _MsgQueue,
    stop_event: threading.Event,
    mode: ProcessingMode,
) -> None:
    """Run the multiprocessing pool in a background thread.

    Pushes messages to msg_queue for the GUI thread to consume.
    Message formats:
      ("result", FileResult)
      ("finish", files_done: int, was_interrupted: bool)
      ("error", error_message: str)
    """
    try:
        if mode == "archive":
            worker_func = partial(
                process_archive, details_file_path=details_file_path
            )
        else:
            worker_func = partial(
                process_pdf, details_file_path=details_file_path
            )

        chunksize = max(1, len(files) // (num_workers * 4))

        with multiprocessing.Pool(processes=num_workers) as pool:
            results_iter = pool.imap_unordered(
                worker_func, files, chunksize=chunksize
            )

            for result in results_iter:
                if stop_event.is_set():
                    pool.terminate()
                    msg_queue.put(("finish", 0, True))
                    return
                msg_queue.put(("result", result))

            msg_queue.put(("finish", len(files), False))
    except Exception as e:
        msg_queue.put(("error", str(e)))
        msg_queue.put(("finish", 0, True))


# ---------------------------------------------------------------------------
# GUI application
# ---------------------------------------------------------------------------

class PagesCounterApp(ctk.CTk):
    """CustomTkinter GUI for counting PDF pages."""

    def __init__(self) -> None:
        super().__init__()
        self.title("PDF Pages Counter")
        self.geometry("860x640")
        self.minsize(700, 500)

        # Theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State
        self.mode: ProcessingMode = "archive"
        self.files: list[str] = []
        self.grand_total_pages: int = 0
        self.grand_total_pdfs: int = 0
        self.is_running: bool = False
        self.stop_event: threading.Event = threading.Event()
        self.msg_queue: _MsgQueue = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.start_time: float = 0.0
        self.details_file_path: str | None = None

        # UI widget references
        self.subtitle_var: ctk.StringVar
        self.mode_var: ctk.StringVar
        self.rb_archive: ctk.CTkRadioButton
        self.rb_pdf: ctk.CTkRadioButton
        self.source_var: ctk.StringVar
        self.source_label: ctk.CTkEntry
        self.btn_folder: ctk.CTkButton
        self.btn_files: ctk.CTkButton
        self.workers_var: ctk.IntVar
        self.save_details_var: ctk.BooleanVar
        self.btn_details: ctk.CTkButton
        self.details_path_var: ctk.StringVar
        self.details_path_entry: ctk.CTkEntry
        self.btn_start: ctk.CTkButton
        self.btn_stop: ctk.CTkButton
        self.btn_clear: ctk.CTkButton
        self.progress_var: ctk.DoubleVar
        self.progress: ctk.CTkProgressBar
        self.status_var: ctk.StringVar
        self.results_tree: ttk.Treeview
        self.summary_var: ctk.StringVar

        self._build_ui()
        self._poll_queue()

    # ----- UI construction ------------------------------------------------

    def _build_ui(self) -> None:
        main = ctk.CTkFrame(self, corner_radius=0)
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # --- Title ---
        title = ctk.CTkLabel(
            main,
            text="PDF Pages Counter",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(anchor="w", pady=(4, 2))
        self.subtitle_var = ctk.StringVar(
            value="Count pages in PDFs inside .tar.zst archives"
        )
        subtitle = ctk.CTkLabel(
            main,
            textvariable=self.subtitle_var,
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        subtitle.pack(anchor="w", pady=(0, 10))

        # --- Mode selector ---
        mode_frame = ctk.CTkFrame(main)
        mode_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            mode_frame, text="Mode:", font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=(0, 8))

        self.mode_var = ctk.StringVar(value="archive")
        self.rb_archive = ctk.CTkRadioButton(
            mode_frame,
            text="Archives (.tar.zst)",
            value="archive",
            variable=self.mode_var,
            command=self._on_mode_change,
            font=ctk.CTkFont(size=11),
        )
        self.rb_archive.pack(side="left", padx=(0, 12))

        self.rb_pdf = ctk.CTkRadioButton(
            mode_frame,
            text="Loose PDFs",
            value="pdf",
            variable=self.mode_var,
            command=self._on_mode_change,
            font=ctk.CTkFont(size=11),
        )
        self.rb_pdf.pack(side="left")

        # --- Source selection ---
        src_frame = ctk.CTkFrame(main)
        src_frame.pack(fill="x", pady=(0, 8))

        self.source_var = ctk.StringVar(value="")
        self.source_label = ctk.CTkEntry(
            src_frame,
            textvariable=self.source_var,
            placeholder_text="No folder or file selected",
            font=ctk.CTkFont(size=12),
        )
        self.source_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_row = ctk.CTkFrame(src_frame)
        btn_row.pack(side="right")

        self.btn_folder = ctk.CTkButton(
            btn_row,
            text="Select Folder",
            width=110,
            height=30,
            command=self._pick_folder,
            font=ctk.CTkFont(size=11),
        )
        self.btn_folder.pack(side="left", padx=(0, 4))

        self.btn_files = ctk.CTkButton(
            btn_row,
            text="Select File(s)",
            width=110,
            height=30,
            command=self._pick_files,
            font=ctk.CTkFont(size=11),
        )
        self.btn_files.pack(side="left")

        # --- Options row ---
        opt_frame = ctk.CTkFrame(main)
        opt_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(opt_frame, text="Workers:", font=ctk.CTkFont(size=11)).pack(
            side="left", padx=(0, 4)
        )
        self.workers_var = ctk.IntVar(value=multiprocessing.cpu_count())
        workers_spin = ctk.CTkEntry(
            opt_frame,
            textvariable=self.workers_var,
            width=50,
            height=28,
            font=ctk.CTkFont(size=11),
        )
        workers_spin.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            opt_frame,
            text=f"Max: {multiprocessing.cpu_count()}",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(side="left", padx=(0, 16))

        self.save_details_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opt_frame,
            text="Save per-PDF details to file",
            variable=self.save_details_var,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(0, 12))

        self.btn_details = ctk.CTkButton(
            opt_frame,
            text="Details Path",
            width=90,
            height=26,
            command=self._pick_details_path,
            font=ctk.CTkFont(size=10),
            state="disabled",
        )
        self.btn_details.pack(side="left", padx=(0, 4))

        self.details_path_var = ctk.StringVar(value="")
        self.details_path_entry = ctk.CTkEntry(
            opt_frame,
            textvariable=self.details_path_var,
            width=180,
            height=26,
            font=ctk.CTkFont(size=10),
            state="disabled",
        )
        self.details_path_entry.pack(side="left")

        # Link checkbox to details controls
        self._on_details_toggle()
        self.save_details_var.trace_add("write", lambda *_: self._on_details_toggle())

        # --- Action buttons ---
        act_frame = ctk.CTkFrame(main)
        act_frame.pack(fill="x", pady=(0, 8))

        self.btn_start = ctk.CTkButton(
            act_frame,
            text="\u25b6  Start Counting",
            width=160,
            height=34,
            fg_color="green",
            hover_color="darkgreen",
            command=self._start_counting,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            act_frame,
            text="\u25a0  Stop",
            width=100,
            height=34,
            fg_color="red",
            hover_color="darkred",
            command=self._stop_counting,
            state="disabled",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.btn_stop.pack(side="left")

        self.btn_clear = ctk.CTkButton(
            act_frame,
            text="Clear Results",
            width=110,
            height=30,
            command=self._clear_results,
            font=ctk.CTkFont(size=11),
        )
        self.btn_clear.pack(side="right")

        # --- Progress ---
        self.progress_var = ctk.DoubleVar(value=0)
        self.progress = ctk.CTkProgressBar(
            main, variable=self.progress_var, height=10,
        )
        self.progress.pack(fill="x", pady=(0, 4))

        self.status_var = ctk.StringVar(value="Ready.")
        ctk.CTkLabel(
            main,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w")

        # --- Results area ---
        results_frame = ctk.CTkScrollableFrame(
            main, label_text="Results", height=220
        )
        results_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.results_tree = ttk.Treeview(
            results_frame,
            columns=("file", "pdfs", "pages", "time"),
            show="headings",
        )
        self.results_tree.heading("file", text="File")
        self.results_tree.heading("pdfs", text="PDFs")
        self.results_tree.heading("pages", text="Pages")
        self.results_tree.heading("time", text="Time")
        self.results_tree.column("file", width=400, minwidth=200)
        self.results_tree.column("pdfs", width=80, minwidth=50)
        self.results_tree.column("pages", width=80, minwidth=50)
        self.results_tree.column("time", width=80, minwidth=50)
        self.results_tree.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Summary bar ---
        self.summary_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            main,
            textvariable=self.summary_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

    # ----- Mode switching -------------------------------------------------

    def _on_mode_change(self) -> None:
        """Update UI when mode changes between archive and loose PDF."""
        raw_mode = self.mode_var.get()
        if raw_mode in ("archive", "pdf"):
            self.mode = raw_mode
        self.files = []
        self.source_var.set("")
        self.summary_var.set("")
        self.progress_var.set(0)

        if self.mode == "archive":
            self.subtitle_var.set(
                "Count pages in PDFs inside .tar.zst archives"
            )
            self.btn_folder.configure(text="Select Folder")
            self.btn_files.configure(text="Select File(s)")
            self.results_tree.heading("file", text="Archive")
        else:
            self.subtitle_var.set("Count pages in loose PDF files")
            self.btn_folder.configure(text="Select Folder")
            self.btn_files.configure(text="Select File(s)")
            self.results_tree.heading("file", text="PDF File")

    # ----- Helpers --------------------------------------------------------

    def _on_details_toggle(self) -> None:
        """Enable/disable details path controls based on checkbox."""
        enabled = "normal" if self.save_details_var.get() else "disabled"
        self.btn_details.configure(state=enabled)
        self.details_path_entry.configure(state=enabled)
        if not self.save_details_var.get():
            self.details_path_var.set("")
            self.details_file_path = None

    def _pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder")
        if folder:
            self.files = find_files(folder, self.mode)
            ext = ".tar.zst archive" if self.mode == "archive" else "PDF"
            self.status_var.set(
                f"Found {len(self.files)} {ext}(s) in "
                + f"'{os.path.basename(folder)}'."
            )
            self.source_var.set(folder)

    def _pick_files(self) -> None:
        if self.mode == "archive":
            filetypes = [("Zstandard archives", "*.tar.zst"), ("All files", "*.*")]
            title = "Select .tar.zst file(s)"
        else:
            filetypes = [("PDF files", "*.pdf"), ("All files", "*.*")]
            title = "Select PDF file(s)"

        files = filedialog.askopenfilenames(title=title, filetypes=filetypes)
        if files:
            self.files = list(files)
            if len(files) > 1:
                self.source_var.set(f"{len(files)} file(s) selected")
            else:
                first_file = files[0]  # type: ignore[index]
                self.source_var.set(os.path.basename(first_file))
            ext = ".tar.zst" if self.mode == "archive" else "PDF"
            self.status_var.set(f"Selected {len(files)} {ext}(s).")

    def _pick_details_path(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save per-PDF details to...",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.details_path_var.set(path)
            self.details_file_path = path

    # ----- Actions --------------------------------------------------------

    def _start_counting(self) -> None:
        if not self.files:
            messagebox.showwarning(
                "No files",
                "Please select a folder or files first.",
            )
            return

        self.stop_event.clear()
        self.is_running = True
        self.grand_total_pages = 0
        self.grand_total_pdfs = 0
        self.start_time = time.time()

        # Clear previous results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        # UI state
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.progress_var.set(0)
        self.summary_var.set("")
        self.status_var.set("Processing...")

        # Details file
        details_path = self.details_file_path
        if details_path:
            init_details_file(details_path)

        # Launch background thread
        self.worker_thread = threading.Thread(
            target=_run_counting,
            args=(
                self.files,
                self.workers_var.get(),
                details_path,
                self.msg_queue,
                self.stop_event,
                self.mode,
            ),
            daemon=True,
        )
        self.worker_thread.start()

        # Schedule next poll
        self.after(100, self._poll_queue)

    def _stop_counting(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping...")

    def _clear_results(self) -> None:
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        self.grand_total_pages = 0
        self.grand_total_pdfs = 0
        self.summary_var.set("")
        self.status_var.set("Results cleared.")
        self.progress_var.set(0)

    # ----- Queue polling --------------------------------------------------

    def _poll_queue(self) -> None:
        """Process all queued messages, then schedule next poll if still running."""
        while not self.msg_queue.empty():
            try:
                msg = self.msg_queue.get_nowait()
            except queue.Empty:
                break

            msg_type = msg[0]

            if msg_type == "result":
                result: FileResult = msg[1]
                elapsed = time.time() - self.start_time
                self.grand_total_pages += result.total_pages
                self.grand_total_pdfs += result.pdf_count

                self.results_tree.insert(
                    "",
                    "end",
                    values=(
                        os.path.basename(result.file_path),
                        f"{result.pdf_count:,}",
                        f"{result.total_pages:,}",
                        f"{elapsed:.1f}s",
                    ),
                )
                self.results_tree.see(self.results_tree.get_children()[-1])

                # Update progress
                done = len(self.results_tree.get_children())
                total = len(self.files)
                self.progress_var.set(done / total if total else 0)
                self.status_var.set(
                    f"Processed {done}/{total} | "
                    + f"{self.grand_total_pdfs:,} PDFs | "
                    + f"{self.grand_total_pages:,} pages"
                )

            elif msg_type == "finish":
                files_done: int = msg[1]
                was_interrupted: bool = msg[2]
                elapsed = time.time() - self.start_time
                self.is_running = False
                self.btn_start.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.progress_var.set(1.0)

                if was_interrupted:
                    self.status_var.set("Stopped by user.")
                else:
                    self.status_var.set("Done!")
                    self.summary_var.set(
                        f"Files: {files_done}  |  "
                        + f"PDFs: {self.grand_total_pdfs:,}  |  "
                        + f"Pages: {self.grand_total_pages:,}  |  "
                        + f"Time: {elapsed:.1f}s"
                    )
                    if self.details_file_path:
                        self.status_var.set(
                            f"Done! Details saved to: {self.details_file_path}"
                        )
                return

            elif msg_type == "error":
                messagebox.showerror("Error", msg[1])

        if self.is_running:
            self.after(100, self._poll_queue)


def main() -> None:
    """GUI entry point."""
    # Verify pymupdf works
    try:
        verify_pymupdf()
    except Exception as e:
        messagebox.showerror(
            "pymupdf error", f"pymupdf failed to initialize: {e}"
        )
        sys.exit(1)

    app = PagesCounterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
