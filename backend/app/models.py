"""Import every ORM model so SQLAlchemy metadata (and Alembic) sees them all."""

from app.core.database import Base
from app.modules.auditing.models import AuditEvent
from app.modules.comparison.models import ComparisonDocument, ComparisonFinding, DocumentComparison
from app.modules.documents.models import (
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentTable,
    IdempotencyRecord,
    SpreadsheetRow,
    StorageObject,
)
from app.modules.extraction.models import ExtractionRun, InvoiceLineItem, InvoiceRecord
from app.modules.identity.models import Organization, RefreshSession, User
from app.modules.jobs.models import OutboxEvent, ProcessingRun, ProcessingTask
from app.modules.reviews.models import ReviewAction, ReviewTask
from app.modules.validation.models import ValidationIssue

__all__ = [
    "AuditEvent",
    "Base",
    "ComparisonDocument",
    "ComparisonFinding",
    "Document",
    "DocumentChunk",
    "DocumentComparison",
    "DocumentPage",
    "DocumentTable",
    "ExtractionRun",
    "IdempotencyRecord",
    "InvoiceLineItem",
    "InvoiceRecord",
    "Organization",
    "OutboxEvent",
    "ProcessingRun",
    "ProcessingTask",
    "RefreshSession",
    "ReviewAction",
    "ReviewTask",
    "SpreadsheetRow",
    "StorageObject",
    "User",
    "ValidationIssue",
]
