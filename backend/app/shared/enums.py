"""Domain enumerations. Stored as VARCHAR with CHECK constraints."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class OrganizationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class FileKind(StrEnum):
    PDF = "PDF"
    IMAGE = "IMAGE"
    TIFF = "TIFF"
    XLSX = "XLSX"
    XLS = "XLS"
    CSV = "CSV"

    @property
    def is_pdf(self) -> bool:
        return self == FileKind.PDF

    @property
    def is_image(self) -> bool:
        return self in (FileKind.IMAGE, FileKind.TIFF)

    @property
    def is_spreadsheet(self) -> bool:
        return self in (FileKind.XLSX, FileKind.XLS, FileKind.CSV)


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    QUARANTINED = "QUARANTINED"
    DELETED = "DELETED"


class ScanStatus(StrEnum):
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"
    CREDIT_NOTE = "CREDIT_NOTE"
    FINANCIAL_STATEMENT = "FINANCIAL_STATEMENT"
    SPREADSHEET_REGISTER = "SPREADSHEET_REGISTER"
    UNKNOWN = "UNKNOWN"

    @property
    def is_invoice_like(self) -> bool:
        return self in (DocumentType.INVOICE, DocumentType.RECEIPT, DocumentType.CREDIT_NOTE)


class PageType(StrEnum):
    NATIVE_TEXT = "NATIVE_TEXT"
    SCANNED = "SCANNED"
    MIXED = "MIXED"
    IMAGE = "IMAGE"
    EMPTY = "EMPTY"


class PageStatus(StrEnum):
    PENDING = "PENDING"
    DONE = "DONE"
    FAILED = "FAILED"


class JobType(StrEnum):
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    REVALIDATION = "REVALIDATION"
    REINDEX = "REINDEX"
    COMPARISON = "COMPARISON"
    RECONCILIATION = "RECONCILIATION"


class RunState(StrEnum):
    QUEUED = "QUEUED"
    PREPROCESSING = "PREPROCESSING"
    PARSING = "PARSING"
    EXTRACTING = "EXTRACTING"
    VALIDATING = "VALIDATING"
    INDEXING = "INDEXING"
    COMPARING = "COMPARING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_RUN_STATES


TERMINAL_RUN_STATES = frozenset(
    {
        RunState.COMPLETED,
        RunState.COMPLETED_WITH_WARNINGS,
        RunState.REQUIRES_REVIEW,
        RunState.FAILED,
        RunState.CANCELLED,
    }
)


class TaskType(StrEnum):
    PREPROCESS = "PREPROCESS"
    PARSE_PAGES = "PARSE_PAGES"
    PARSE_SPREADSHEET = "PARSE_SPREADSHEET"
    EXTRACT = "EXTRACT"
    VALIDATE = "VALIDATE"
    INDEX = "INDEX"
    COMPARE = "COMPARE"


class TaskState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExtractionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ReviewStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2, Severity.CRITICAL: 3}


class ValidationOutcome(StrEnum):
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    FAILED = "FAILED"


class ResolutionStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"


class ComparisonType(StrEnum):
    PDF_PDF = "PDF_PDF"
    PDF_SPREADSHEET = "PDF_SPREADSHEET"


class ComparisonStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STALE = "STALE"


class FindingStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MISSING_LEFT = "MISSING_LEFT"
    MISSING_RIGHT = "MISSING_RIGHT"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    DUPLICATE = "DUPLICATE"


class ReviewActionType(StrEnum):
    CORRECTION = "CORRECTION"
    APPROVAL = "APPROVAL"
    REJECTION = "REJECTION"
    ASSIGNMENT = "ASSIGNMENT"


class ReviewTaskStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class StorageCategory(StrEnum):
    ORIGINAL = "ORIGINAL"
    PAGE_LAYOUT = "PAGE_LAYOUT"
    PAGE_TEXT = "PAGE_TEXT"
    OCR_RESULT = "OCR_RESULT"
    EXTRACTION_RAW = "EXTRACTION_RAW"
    TABLE_DATA = "TABLE_DATA"
    EXPORT = "EXPORT"


class StorageObjectStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DELETED = "DELETED"
