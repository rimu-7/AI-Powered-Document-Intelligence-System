"""File identification by content signature, plus archive-bomb and macro checks.

The uploaded filename and client-declared MIME type are never trusted; the
extension must agree with the detected content signature.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from typing import IO

from app.core.config import Settings
from app.shared.enums import FileKind

ALLOWED_EXTENSIONS: dict[str, FileKind] = {
    ".pdf": FileKind.PDF,
    ".jpg": FileKind.IMAGE,
    ".jpeg": FileKind.IMAGE,
    ".png": FileKind.IMAGE,
    ".tif": FileKind.TIFF,
    ".tiff": FileKind.TIFF,
    ".xlsx": FileKind.XLSX,
    ".xls": FileKind.XLS,
    ".csv": FileKind.CSV,
}

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "tiff": "image/tiff",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
}

_EXT_SIGNATURE = {
    ".pdf": "pdf",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
}


class FileRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FileIdentity:
    extension: str
    kind: FileKind
    signature: str
    content_type: str


def detect_signature(head: bytes) -> str | None:
    if head[:1024].find(b"%PDF-") != -1:
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")):
        return "tiff"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole2"
    if _looks_like_text(head):
        return "text"
    return None


def _looks_like_text(head: bytes) -> bool:
    if not head or b"\x00" in head:
        return False
    sample = head[:8192]
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = sample.decode(encoding)
        except UnicodeDecodeError as exc:
            # Tolerate only a multi-byte character cut at the sample boundary.
            if exc.reason != "unexpected end of data" or exc.start < len(sample) - 4:
                continue
            text = sample[: exc.start].decode(encoding)
        printable = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
        return printable / max(1, len(text)) > 0.95
    return False


def identify(filename: str, head: bytes) -> FileIdentity:
    lower = filename.lower()
    ext = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise FileRejected("UNSUPPORTED_FILE_TYPE", f"File extension '{ext or '(none)'}' is not allowed")
    signature = detect_signature(head)
    expected = _EXT_SIGNATURE[ext]
    ok = (
        (expected == signature)
        or (expected == "xlsx" and signature == "zip")
        or (expected == "xls" and signature == "ole2")
        or (expected == "csv" and signature == "text")
    )
    if not ok:
        raise FileRejected(
            "CONTENT_SIGNATURE_MISMATCH",
            f"File content does not match its '{ext}' extension",
        )
    return FileIdentity(ext, ALLOWED_EXTENSIONS[ext], expected, CONTENT_TYPES[expected])


def check_office_archive(fileobj: IO[bytes], settings: Settings) -> None:
    """Zip-bomb, structure and macro checks for XLSX before any parser sees it."""
    fileobj.seek(0)
    try:
        with zipfile.ZipFile(fileobj) as zf:
            infos = zf.infolist()
            if len(infos) > settings.xlsx_max_entries:
                raise FileRejected("ARCHIVE_TOO_MANY_ENTRIES", "Workbook archive has too many entries")
            total_uncompressed = 0
            names = set()
            for info in infos:
                names.add(info.filename)
                if info.filename.startswith("/") or ".." in info.filename.split("/"):
                    raise FileRejected("ARCHIVE_PATH_TRAVERSAL", "Workbook archive contains unsafe paths")
                total_uncompressed += info.file_size
                if info.compress_size > 0 and info.file_size / info.compress_size > settings.xlsx_max_compression_ratio:
                    raise FileRejected("ARCHIVE_BOMB_SUSPECTED", "Workbook compression ratio is too high")
            if total_uncompressed > settings.xlsx_max_uncompressed_bytes:
                raise FileRejected("ARCHIVE_TOO_LARGE", "Workbook uncompressed size exceeds the limit")
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise FileRejected("INVALID_WORKBOOK", "File is not a valid XLSX workbook")
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                raise FileRejected("MACRO_CONTENT_NOT_ALLOWED", "Workbooks containing macros are not accepted")
    except zipfile.BadZipFile as exc:
        raise FileRejected("INVALID_WORKBOOK", "Corrupted XLSX archive") from exc
    finally:
        fileobj.seek(0)


def sha256_stream(fileobj: IO[bytes], chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    fileobj.seek(0)
    while chunk := fileobj.read(chunk_size):
        digest.update(chunk)
        size += len(chunk)
    fileobj.seek(0)
    return digest.hexdigest(), size
