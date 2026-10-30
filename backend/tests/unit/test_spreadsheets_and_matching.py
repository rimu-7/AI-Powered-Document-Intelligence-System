from __future__ import annotations

import csv
import io
import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.modules.comparison.mapping import suggest_mapping, validate_mapping
from app.modules.comparison.matching import ComparableRecord, MatchOptions, match_records
from app.modules.comparison.service import csv_safe, findings_to_csv
from app.modules.parsing.spreadsheet_parser import build_tables, detect_encoding
from app.shared.enums import FileKind, FindingStatus
from app.shared.text import normalize_invoice_number, normalize_supplier
from evaluation.synthetic import random_invoice, register_csv_bytes, register_rows, register_xls_bytes, register_xlsx_bytes


def _tables(path: Path, kind: FileKind) -> list[tuple[Any, list[tuple[int, dict[str, Any]]]]]:
    return [(t, list(rows)) for t, rows in build_tables(str(path), kind)]


def test_xlsx_register_header_detection_and_provenance(tmp_path: Path) -> None:
    specs = [random_invoice(random.Random(i), i + 1) for i in range(3)]
    path = tmp_path / "r.xlsx"
    path.write_bytes(register_xlsx_bytes(register_rows(specs)))
    [(table, rows)] = _tables(path, FileKind.XLSX)
    assert table.header_row_number == 3 and table.looks_like_register
    assert [r[0] for r in rows] == [4, 5, 6]
    first = rows[0][1]
    assert first["Invoice No"]["v"] == specs[0].invoice_number and first["Invoice No"]["c"] == "A4"
    assert Decimal(first["Invoice Total"]["v"]) == specs[0].total_amount


def test_xlsx_formulas_are_not_evaluated(tmp_path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Invoice No", "Vendor", "Net", "VAT", "Invoice Total"])
    ws.append(["A1", "X Ltd", 100, 10, "=C2+D2"])
    path = tmp_path / "f.xlsx"
    wb.save(path)
    [(table, rows)] = _tables(path, FileKind.XLSX)
    cell = rows[0][1]["Invoice Total"]
    assert cell["f"] == "=C2+D2" and cell["v"] is None and cell["missing_cached"] is True
    assert any(i["code"] == "FORMULA_CACHE_MISSING" for i in table.issues)


def test_legacy_xls(tmp_path: Path) -> None:
    specs = [random_invoice(random.Random(9), 1)]
    path = tmp_path / "r.xls"
    path.write_bytes(register_xls_bytes(register_rows(specs)))
    [(table, rows)] = _tables(path, FileKind.XLS)
    assert table.header_row_number == 1
    assert rows[0][1]["Invoice No"]["v"] == specs[0].invoice_number


def test_csv_encodings_delimiters_and_ragged_rows(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_bytes('invoice_no;vendor;invoice_total\n"A-1";"Müller; Söhne";"1.234,50"\nA-2;Baz\n'.encode("utf-8-sig"))
    [(table, rows)] = _tables(path, FileKind.CSV)
    assert table.headers == ["invoice_no", "vendor", "invoice_total"]
    assert rows[0][1]["vendor"]["v"] == "Müller; Söhne"
    assert any(i["code"] == "INCONSISTENT_ROW_LENGTH" for i in table.issues)
    assert detect_encoding("Montréal".encode("cp1252")) == "cp1252"
    p2 = tmp_path / "b.csv"
    p2.write_bytes(register_csv_bytes(register_rows([random_invoice(random.Random(3), 7)]), delimiter="\t"))
    [(_, rows2)] = _tables(p2, FileKind.CSV)
    assert rows2[0][1]["Invoice No"]["v"] == "INV-2026-0007"


def test_row_limit(tmp_path: Path, monkeypatch: Any) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "max_spreadsheet_rows", 5)
    path = tmp_path / "big.csv"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["invoice_no", "total"])
    for i in range(20):
        w.writerow([f"A{i}", i])
    path.write_text(buf.getvalue())
    [(table, rows)] = _tables(path, FileKind.CSV)
    assert len(rows) == 5 and table.truncated


def test_mapping_suggestions() -> None:
    s = suggest_mapping(["Invoice No", "Vendor", "Invoice Date", "Currency", "Net Amount", "VAT", "Invoice Total", "Notes"])
    assert s.suggested_mapping["invoice_number"] == "Invoice No"
    assert s.suggested_mapping["supplier_name"] == "Vendor"
    assert s.suggested_mapping["total_amount"] == "Invoice Total"
    assert s.suggested_mapping["tax_amount"] == "VAT"
    assert not s.missing_required
    assert validate_mapping({"invoice_number": "Nope"}, {"Invoice No"})


def rec(
    rid: str, number: str | None, supplier: str | None, total: str | None, currency: str | None = "USD", day: int = 1, source: str = "row"
) -> ComparableRecord:
    from datetime import date

    return ComparableRecord(
        record_id=rid,
        source=source,
        document_id="d",
        invoice_number=number,
        normalized_number=normalize_invoice_number(number),
        supplier=supplier,
        normalized_supplier=normalize_supplier(supplier),
        invoice_date=date(2026, 10, day),
        currency=currency,
        total_amount=Decimal(total) if total else None,
        reference={"id": rid},
    )


def record_status(findings: list[Any], key_contains: str) -> FindingStatus:
    return next(f.status for f in findings if f.field_name == "__record__" and (f.record_key or "").startswith(key_contains))


def test_reconciliation_cases() -> None:
    pdf = [
        rec("p1", "INV-1", "ABC Ltd", "100.00", source="invoice"),  # exact match
        rec("p2", "INV-2", "ABC Ltd", "200.00", source="invoice"),  # amount differs
        rec("p3", "INV-3", "ABC Ltd", "300.00", source="invoice"),  # missing in sheet
        rec("p4", "INV-4", "XYZ GmbH", "400.00", source="invoice"),  # same number, other supplier in sheet
        rec("p5", "INV-5", "ABC Ltd", "500.00", source="invoice"),  # two candidates → ambiguous
        rec("p6", "INV-6", "ABC Ltd", "600.00", currency="EUR", source="invoice"),  # currency differs
        rec("p7", "INV-7", "ABC Ltd", "700.00", day=1, source="invoice"),  # date differs
    ]
    sheet = [
        rec("r1", "INV-1", "A.B.C. Limited", "100.00"),
        rec("r2", "INV-2", "ABC Ltd", "250.00"),
        rec("r4", "INV-4", "Other Supplier Inc", "400.00"),
        rec("r5a", "INV-5", "ABC Ltd", "510.00", day=2),
        rec("r5b", "INV-5", "ABC Ltd", "520.00", day=3),
        rec("r6", "INV-6", "ABC Ltd", "600.00", currency="USD"),
        rec("r7", "INV-7", "ABC Ltd", "700.00", day=9),
        rec("r8", "INV-8", "ABC Ltd", "800.00"),  # missing in PDFs
        rec("r9", "INV-8", "ABC Ltd", "800.00"),  # duplicate row (e.g. second sheet)
    ]
    result = match_records(pdf, sheet, MatchOptions(supplier_fuzzy_threshold=70, fuzzy_invoice_numbers=False))
    f = result.findings
    assert record_status(f, "INV-1 ") == FindingStatus.MATCH  # "ABC Ltd" == "A.B.C. Limited" after normalization
    assert record_status(f, "INV-2 ") == FindingStatus.MISMATCH
    assert record_status(f, "INV-3 ") == FindingStatus.MISSING_RIGHT
    assert record_status(f, "INV-5 ") == FindingStatus.AMBIGUOUS
    assert record_status(f, "INV-6 ") == FindingStatus.MISMATCH
    total6 = next(x for x in f if x.field_name == "total_amount" and "INV-6 " in (x.record_key or ""))
    assert total6.status == FindingStatus.NOT_COMPARABLE  # never compare across currencies
    date7 = next(x for x in f if x.field_name == "invoice_date" and "INV-7 " in (x.record_key or ""))
    assert date7.status == FindingStatus.MISMATCH and date7.difference == {"days": 8}
    # Same number from another supplier is reported on the record itself, not as a loose finding.
    inv4 = next(x for x in f if x.field_name == "__record__" and (x.record_key or "").startswith("INV-4 ") and x.left)
    assert inv4.status == FindingStatus.MISSING_RIGHT and "different supplier" in str(inv4.difference)
    assert inv4.difference["suppliers"] == ["Other Supplier Inc"]
    # Every finding that is not a record belongs to the record before it.
    keys = [x.record_key for x in f if x.field_name == "__record__"]
    assert all(x.field_name == "__record__" or x.record_key in keys for x in f)
    s = result.summary
    assert s["duplicate_count"] == 2  # INV-5 and INV-8 each appear twice in the register
    assert s["missing_left_count"] >= 2  # INV-8 and the INV-4 row from the other supplier
    assert s["missing_right_count"] >= 2  # INV-3 and INV-4


def test_exact_match_and_fuzzy_number_is_only_ambiguous() -> None:
    result = match_records(
        [rec("p", "INV-1", "ABC Ltd", "10.00", source="invoice")], [rec("r", "INV-1", "ABC Ltd", "10.00")], MatchOptions()
    )
    assert result.summary["matched_count"] == 1
    # OCR misread (O vs 0) with the same supplier and total: candidate, but only AMBIGUOUS.
    fuzzy = match_records(
        [rec("p", "INV-2O26-0001", "ABC Ltd", "10.00", source="invoice")], [rec("r", "INV-2026-0001", "ABC Ltd", "10.00")], MatchOptions()
    )
    assert fuzzy.summary["matched_count"] == 0 and fuzzy.summary["ambiguous_count"] == 1
    # Sequential number with a different total: not a candidate at all.
    seq = match_records(
        [rec("p", "INV-2026-0001", "ABC Ltd", "10.00", source="invoice")], [rec("r", "INV-2026-0002", "ABC Ltd", "99.00")], MatchOptions()
    )
    assert seq.summary["ambiguous_count"] == 0 and seq.summary["missing_right_count"] == 1


def test_csv_export_neutralizes_formula_injection() -> None:
    assert csv_safe('=HYPERLINK("http://evil")') == '\'=HYPERLINK("http://evil")'
    assert csv_safe("+cmd") == "'+cmd"
    assert csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("-10.50") == "-10.50"
    assert csv_safe("-2+3") == "'-2+3"

    class F:
        position = 0
        record_key = "=1+1"
        field_name = "total_amount"
        status = FindingStatus.MISMATCH
        left_value_json = "=cmd|' /C calc'!A0"
        right_value_json = "10.00"
        difference_json = None
        evidence_json: dict[str, Any] = {}

    out = findings_to_csv([F()])  # type: ignore[list-item]
    assert "\"'=cmd" in out and '"\'=1+1"' in out


def test_identical_duplicate_rows_match_first_and_report_duplicate() -> None:
    pdf = [rec("p1", "INV-9", "ABC Ltd", "90.00", source="invoice")]
    sheet = [rec("r1", "INV-9", "ABC Ltd", "90.00"), rec("r2", "INV-9", "ABC Ltd", "90.00")]
    s = match_records(pdf, sheet, MatchOptions()).summary
    assert s["matched_count"] == 1 and s["duplicate_count"] == 1 and s["ambiguous_count"] == 0 and s["missing_left_count"] == 0


def test_record_without_number_pairs_only_on_supplier_date_and_total() -> None:
    # The register row has no invoice number: supplier, date and total identify it,
    # but the pair needs confirmation (AMBIGUOUS), never an authoritative MATCH.
    result = match_records([rec("p", "INV-9", "ABC Ltd", "90.00", source="invoice")], [rec("r", None, "ABC Ltd", "90.00")], MatchOptions())
    assert result.summary["ambiguous_count"] == 1
    assert result.summary["missing_left_count"] == 0 and result.summary["missing_right_count"] == 0
    record = next(f for f in result.findings if f.field_name == "__record__")
    assert record.difference["match_quality"] == "no_invoice_number"
    number = next(f for f in result.findings if f.field_name == "invoice_number")
    assert number.status == FindingStatus.NOT_COMPARABLE

    # A different total or an unknown supplier is not enough.
    assert (
        match_records([rec("p", None, "ABC Ltd", "90.00", source="invoice")], [rec("r", None, "ABC Ltd", "91.00")], MatchOptions()).summary[
            "missing_right_count"
        ]
        == 1
    )
    assert (
        match_records([rec("p", None, None, "90.00", source="invoice")], [rec("r", None, "ABC Ltd", "90.00")], MatchOptions()).summary[
            "missing_right_count"
        ]
        == 1
    )

    # Two equally good candidates: ambiguous with both listed, nothing chosen.
    two = match_records(
        [rec("p", None, "ABC Ltd", "90.00", source="invoice")],
        [rec("r1", "A-1", "ABC Ltd", "90.00"), rec("r2", "A-2", "ABC Ltd", "90.00")],
        MatchOptions(fuzzy_invoice_numbers=False),
    )
    amb = next(f for f in two.findings if f.field_name == "__record__" and f.status == FindingStatus.AMBIGUOUS)
    assert len(amb.right) == 2 and two.summary["missing_left_count"] == 2


def test_record_finding_lists_the_fields_that_differ() -> None:
    result = match_records(
        [rec("p", "INV-1", "ABC Ltd", "100.00", source="invoice")], [rec("r", "INV-1", "ABC Ltd", "120.00", day=4)], MatchOptions()
    )
    record = next(f for f in result.findings if f.field_name == "__record__")
    assert record.status == FindingStatus.MISMATCH
    assert set(record.difference["mismatched_fields"]) == {"invoice_date", "total_amount"}
