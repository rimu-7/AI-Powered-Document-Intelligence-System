from __future__ import annotations

import io
import zipfile

import pytest

from app.core.config import get_settings
from app.modules.documents.fingerprint import FileRejected, check_office_archive, identify
from app.shared.enums import FileKind


def test_identify_accepts_matching_signatures() -> None:
    assert identify("a.pdf", b"%PDF-1.7\n...").kind == FileKind.PDF
    assert identify("a.PNG", b"\x89PNG\r\n\x1a\n....").kind == FileKind.IMAGE
    assert identify("a.tif", b"II*\x00....").kind == FileKind.TIFF
    assert identify("a.csv", b"invoice_no,total\nA1,10\n").kind == FileKind.CSV
    assert identify("a.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1....").kind == FileKind.XLS


@pytest.mark.parametrize(
    ("name", "head", "code"),
    [
        ("invoice.pdf", b"MZ\x90\x00 this is an exe", "CONTENT_SIGNATURE_MISMATCH"),
        ("invoice.exe", b"MZ\x90\x00", "UNSUPPORTED_FILE_TYPE"),
        ("invoice", b"%PDF-1.4", "UNSUPPORTED_FILE_TYPE"),
        ("data.csv", b"\x00\x01\x02binary", "CONTENT_SIGNATURE_MISMATCH"),
        ("photo.png", b"%PDF-1.4", "CONTENT_SIGNATURE_MISMATCH"),
    ],
)
def test_identify_rejects(name: str, head: bytes, code: str) -> None:
    with pytest.raises(FileRejected) as exc:
        identify(name, head)
    assert exc.value.code == code


def _zip(entries: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_office_archive_checks() -> None:
    settings = get_settings()
    valid = {"[Content_Types].xml": b"<x/>", "xl/workbook.xml": b"<w/>"}
    check_office_archive(_zip(valid), settings)

    with pytest.raises(FileRejected) as exc:
        check_office_archive(_zip({**valid, "xl/vbaProject.bin": b"macro"}), settings)
    assert exc.value.code == "MACRO_CONTENT_NOT_ALLOWED"

    with pytest.raises(FileRejected) as exc:
        check_office_archive(_zip({**valid, "xl/bomb.xml": b"0" * 5_000_000}), settings)
    assert exc.value.code == "ARCHIVE_BOMB_SUSPECTED"

    with pytest.raises(FileRejected) as exc:
        check_office_archive(_zip({"hello.txt": b"x"}), settings)
    assert exc.value.code == "INVALID_WORKBOOK"

    with pytest.raises(FileRejected) as exc:
        check_office_archive(io.BytesIO(b"PK\x03\x04garbage"), settings)
    assert exc.value.code == "INVALID_WORKBOOK"
