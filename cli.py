#!/usr/bin/env python3
"""CLI presentation layer for PDF page counting.

Uses multiprocessing to parallelize work and tqdm for progress display.
All core logic is delegated to services.py.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import time
from dataclasses import dataclass
from functools import partial

from tqdm import tqdm

from services import (
    FileResult,
    ProcessingMode,
    find_files,
    init_details_file,
    process_archive,
    process_pdf,
    verify_pymupdf,
)


@dataclass
class CliArgs:
    """Typed CLI arguments."""

    target_dir: str
    jobs: int | None
    mode: ProcessingMode
    details: str | None


def _parse_args(argv: list[str] | None = None) -> CliArgs:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Parallel page counter for PDFs — archives or loose files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  archive  (default)  Recursively find .tar.zst files and count PDFs inside
  pdf                Recursively find .pdf files and count pages directly

Examples:
  %(prog)s /data/pdfs/                    # archive mode, current dir
  %(prog)s /data/pdfs/ -j 16             # 16 workers
  %(prog)s /data/pdfs/ --mode pdf         # loose PDF mode
  %(prog)s /data/pdfs/ --details out.txt  # save per-PDF details
        """,
    )
    parser.add_argument(
        "target_dir",
        type=str,
        nargs="?",
        default=".",
        help="Target root directory (default: current directory)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel workers (default: CPU count)",
    )
    parser.add_argument(
        "--mode",
        choices=["archive", "pdf"],
        default="archive",
        help="Processing mode: 'archive' for .tar.zst, 'pdf' for loose .pdf files (default: archive)",
    )
    parser.add_argument(
        "--details",
        type=str,
        default=None,
        metavar="FILE",
        help="Write per-PDF details to FILE",
    )
    ns = parser.parse_args(argv)
    return CliArgs(
        target_dir=ns.target_dir,
        jobs=ns.jobs,
        mode=ns.mode,
        details=ns.details,
    )


def _select_worker(mode: ProcessingMode, details_file_path: str | None):
    """Return the appropriate worker function for the given mode."""
    if mode == "archive":
        return partial(process_archive, details_file_path=details_file_path)
    return partial(process_pdf, details_file_path=details_file_path)


def _print_result(
    result: FileResult,
    start_time: float,
) -> None:
    """Print a single file result to the console."""
    elapsed = time.time() - start_time
    print(f"\n{os.path.basename(result.file_path)}  ({elapsed:.1f}s elapsed)")
    print(f"  PDFs: {result.pdf_count}  |  Pages: {result.total_pages}")
    print("-" * 40)


def _print_summary(
    files_processed: int,
    total_pdfs: int,
    total_pages: int,
    elapsed: float,
) -> None:
    """Print the final summary to the console."""
    print()
    print("=" * 60)
    print("Grand Totals")
    print("=" * 60)
    print(f"  Files processed    : {files_processed}")
    print(f"  Total PDFs found   : {total_pdfs}")
    print(f"  Total pages        : {total_pages}")
    print(f"  Execution time     : {elapsed:.2f}s")
    print("=" * 60)


def run(argv: list[str] | None = None) -> None:
    """Entry point for CLI mode.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = _parse_args(argv)

    # Verify pymupdf works (compiled extension, can fail on some systems)
    try:
        verify_pymupdf()
    except Exception as e:
        print(f"ERROR: pymupdf failed to initialize: {e}", file=sys.stderr)
        sys.exit(1)

    start_time = time.time()

    # Collect matching target files
    mode: ProcessingMode = args.mode  # type: ignore[assignment]
    target_files = find_files(args.target_dir, mode)

    ext_label = ".tar.zst archives" if mode == "archive" else ".pdf files"
    if not target_files:
        elapsed = time.time() - start_time
        print(f"No {ext_label} found. (Completed in {elapsed:.2f}s)")
        return

    if mode == "archive":
        print(f"Found {len(target_files)} archives. Spawning execution pool...")
    else:
        print(f"Found {len(target_files)} PDFs. Spawning execution pool...")

    num_workers = args.jobs or multiprocessing.cpu_count()
    print(f"Using {num_workers} worker(s).")

    # Prepare details file
    details_file_path: str | None = None
    if args.details:
        init_details_file(args.details)
        details_file_path = args.details

    # Select worker function based on mode
    worker_func = _select_worker(mode, details_file_path)

    # imap_unordered yields results as soon as each worker finishes
    chunksize = max(1, len(target_files) // (num_workers * 4))
    with multiprocessing.Pool(processes=num_workers) as pool:
        results_iter = pool.imap_unordered(
            worker_func,
            target_files,
            chunksize=chunksize,
        )

        grand_total_pages = 0
        grand_total_pdfs = 0

        print()
        print("=" * 60)
        print("Execution Results")
        print("=" * 60)

        # tqdm progress bar wraps the iterator
        for result in tqdm(
            results_iter,
            total=len(target_files),
            desc="Files processed",
            unit="file",
            leave=False,
        ):
            _print_result(result, start_time)
            grand_total_pages += result.total_pages
            grand_total_pdfs += result.pdf_count

    elapsed = time.time() - start_time
    _print_summary(len(target_files), grand_total_pdfs, grand_total_pages, elapsed)

    if args.details:
        print(f"\nPer-PDF details written to: {args.details}")


def main() -> None:
    """CLI entry point."""
    run()


if __name__ == "__main__":
    main()
