"""Worker-local, size-bounded cache of original files.

A 1,000-page PDF is split into many page-batch tasks; caching the original
by SHA-256 avoids downloading it once per batch. Downloads are verified
against the stored SHA-256 before use and written atomically.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import PermanentProcessingError
from app.modules.documents.models import Document
from app.modules.documents.storage import get_storage, original_bucket


def cache_dir() -> Path:
    base = get_settings().worker_tmp_dir or tempfile.gettempdir()
    path = Path(base) / "docintel-cache"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _evict(directory: Path, budget: int, keep: Path) -> None:
    cached = [p for p in directory.iterdir() if p.is_file() and not p.name.endswith(".part")]
    files = sorted((p for p in cached if p != keep), key=lambda p: p.stat().st_atime)
    total = sum(p.stat().st_size for p in cached)
    for path in files:
        if total <= budget:
            break
        try:
            size = path.stat().st_size
            path.unlink()
            total -= size
        except FileNotFoundError:
            continue


def local_copy(document: Document) -> str:
    settings = get_settings()
    directory = cache_dir()
    # Keep the real extension: some parsers (openpyxl) dispatch on it.
    target = directory / f"{document.sha256}{document.file_extension}"
    if target.exists():
        os.utime(target)
        return str(target)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".part")
    os.close(fd)
    try:
        get_storage().download_to_file(original_bucket(document.storage_key), document.storage_key, tmp)
        digest = hashlib.sha256()
        with open(tmp, "rb") as fh:
            while chunk := fh.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != document.sha256:
            raise PermanentProcessingError("Stored object failed integrity check", code="INTEGRITY_CHECK_FAILED")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _evict(directory, settings.worker_file_cache_bytes, target)
    return str(target)
