"""Core domain logic for PDF page counting.

Hexagonal architecture: this module contains all business logic and is the
only layer that knows about PyMuPDF, zstandard, tarfile, etc. Both the CLI
and GUI consume these functions without any knowledge of each other.

Design principles:
  - Pure functions where possible (no side effects beyond what's documented).
  - No UI, CLI, or framework imports (no argparse, tkinter, tqdm, etc.).
  - Streaming I/O for large files (never loads entire archive into RAM).
  - NamedTemporaryFile for PDF extraction so large PDFs spill to disk.
"""

from __future__ import annotations

import os
import sys
import tarfile
from dataclasses import dataclass, field
from tempfile import NamedTemporaryFile
from typing import IO, Literal

import fitz  # PyMuPDF  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

ProcessingMode = Literal["archive", "pdf"]


@dataclass(frozen=True)
class FileResult:
    """Result of processing a single file (archive or loose PDF)."""

    file_path: str
    total_pages: int
    pdf_count: int


@dataclass
class ProcessingSummary:
    """Aggregated result across all files."""

    files_processed: int = 0
    total_pdfs: int = 0
    total_pages: int = 0
    results: list[FileResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _count_pdf_from_stream(file_obj: IO[bytes]) -> int:
    """Count pages in a PDF read from a file-like object.

    Streams the content to a temporary file on disk to avoid loading
    the entire PDF into RAM. Returns 0 on any error.

    Args:
        file_obj: Readable binary file-like object positioned at start of PDF.

    Returns:
        Page count, or 0 if the PDF could not be parsed.
    """
    try:
        tmp = NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            _stream_to_file(file_obj, tmp)
            doc = fitz.open(tmp.name)  # type: ignore[union-attr]
            if doc is None:
                return 0
            try:
                return doc.page_count
            finally:
                doc.close()  # type: ignore[union-attr]
        finally:
            tmp.close()
            _remove_temp(tmp.name)
    except Exception:
        return 0


def _stream_to_file(src: IO[bytes], dst: IO[bytes]) -> None:
    """Stream data from source to destination in 1 MB chunks."""
    while True:
        chunk = src.read(1_000_000)
        if not chunk:
            break
        dst.write(chunk)
    dst.flush()


def _remove_temp(path: str) -> None:
    """Remove a temporary file, ignoring errors."""
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_pymupdf() -> None:
    """Check that PyMuPDF is functional. Raises on failure."""
    _ = fitz.open


def process_archive(
    archive_path: str,
    details_file_path: str | None = None,
) -> FileResult:
    """Process a single .tar.zst archive.

    Streams zstd decompression + tar iteration — never loads the full
    archive into RAM. Uses temporary files for PDF extraction.

    NOTE: zstandard is imported inside this function to avoid pickling
    errors with multiprocessing (the module holds internal thread locks).

    Args:
        archive_path: Path to the .tar.zst file on disk.
        details_file_path: If provided, append per-PDF details to this file.

    Returns:
        FileResult with page count and PDF count.
    """
    # Lazy import to avoid multiprocessing pickle errors.
    import zstandard as zstd

    total_pages: int = 0
    pdf_count: int = 0

    details_fh: IO[str] | None = None
    if details_file_path is not None:
        details_fh = open(details_file_path, "a", encoding="utf-8")

    detail_lines: list[str] = []
    flush_threshold = 500

    try:
        with open(archive_path, "rb") as compressed_file:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(compressed_file) as decompressed_stream:
                with tarfile.open(fileobj=decompressed_stream, mode="r|") as tar:
                    for member in tar:
                        if member.isfile() and member.name.endswith(".pdf"):
                            file_obj = tar.extractfile(member)
                            if file_obj is not None:
                                page_count = _count_pdf_from_stream(file_obj)

                                if page_count > 0:
                                    if details_fh is not None:
                                        detail_lines.append(
                                            f"  {member.name}: {page_count} pages\n"
                                        )
                                    total_pages += page_count
                                    pdf_count += 1

                                    if len(detail_lines) >= flush_threshold:
                                        if details_fh is not None:
                                            details_fh.writelines(detail_lines)
                                        detail_lines.clear()

    except Exception as e:
        print(f"[ERROR] Failed to process {archive_path}: {e}", file=sys.stderr)
    finally:
        if detail_lines and details_fh is not None:
            details_fh.writelines(detail_lines)
        if details_fh is not None:
            details_fh.close()

    return FileResult(
        file_path=archive_path,
        total_pages=total_pages,
        pdf_count=pdf_count,
    )


def process_pdf(
    pdf_path: str,
    details_file_path: str | None = None,
) -> FileResult:
    """Count pages in a single loose PDF file.

    Args:
        pdf_path: Path to the .pdf file on disk.
        details_file_path: If provided, append per-PDF details to this file.

    Returns:
        FileResult with page count.
    """
    page_count: int = 0
    try:
        doc = fitz.open(pdf_path)  # type: ignore[union-attr]
        if doc is None:
            return FileResult(
                file_path=pdf_path,
                total_pages=0,
                pdf_count=0,
            )
        try:
            page_count = doc.page_count
        finally:
            doc.close()  # type: ignore[union-attr]
    except Exception as e:
        print(f"  [WARN] Could not parse PDF: {pdf_path} ({e})")

    if page_count > 0 and details_file_path is not None:
        with open(details_file_path, "a", encoding="utf-8") as f:
            f.write(f"  {pdf_path}: {page_count} pages\n")

    return FileResult(
        file_path=pdf_path,
        total_pages=page_count,
        pdf_count=1 if page_count > 0 else 0,
    )


def find_files(root_dir: str, mode: ProcessingMode) -> list[str]:
    """Recursively find matching files under root_dir.

    Args:
        root_dir: Root directory to search.
        mode: 'archive' for .tar.zst files, 'pdf' for .pdf files.

    Returns:
        Sorted list of absolute paths to matching files.
    """
    target_files: list[str] = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if mode == "archive" and filename.endswith(".tar.zst"):
                target_files.append(os.path.join(dirpath, filename))
            elif mode == "pdf" and filename.lower().endswith(".pdf"):
                target_files.append(os.path.join(dirpath, filename))

    return sorted(target_files)


def init_details_file(path: str) -> None:
    """Create or truncate a details output file.

    Call this before starting parallel processing to ensure a clean file.

    Args:
        path: File path to create/truncate.
    """
    with open(path, "w", encoding="utf-8"):
        pass
