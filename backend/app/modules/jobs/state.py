"""Per-job-type state machines.

Each job type has its own allowed transitions; there is no global enum that
lets any state move to any other. Any non-terminal state may move to FAILED or
CANCELLED.
"""

from __future__ import annotations

from decimal import Decimal

from app.shared.enums import TERMINAL_RUN_STATES, JobType, RunState

_SUCCESS = {RunState.COMPLETED, RunState.COMPLETED_WITH_WARNINGS, RunState.REQUIRES_REVIEW}

TRANSITIONS: dict[JobType, dict[RunState, set[RunState]]] = {
    JobType.DOCUMENT_PROCESSING: {
        RunState.QUEUED: {RunState.PREPROCESSING},
        RunState.PREPROCESSING: {RunState.PARSING},
        # Spreadsheets and non-invoice documents skip extraction/validation.
        RunState.PARSING: {RunState.EXTRACTING, RunState.INDEXING},
        RunState.EXTRACTING: {RunState.VALIDATING, RunState.INDEXING},
        RunState.VALIDATING: {RunState.INDEXING},
        RunState.INDEXING: set(_SUCCESS),
    },
    JobType.REVALIDATION: {
        RunState.QUEUED: {RunState.VALIDATING},
        RunState.VALIDATING: {RunState.INDEXING},
        RunState.INDEXING: set(_SUCCESS),
    },
    JobType.REINDEX: {
        RunState.QUEUED: {RunState.INDEXING},
        RunState.INDEXING: set(_SUCCESS),
    },
    JobType.COMPARISON: {
        RunState.QUEUED: {RunState.COMPARING},
        RunState.COMPARING: {RunState.COMPLETED, RunState.COMPLETED_WITH_WARNINGS},
    },
    JobType.RECONCILIATION: {
        RunState.QUEUED: {RunState.COMPARING},
        RunState.COMPARING: {RunState.COMPLETED, RunState.COMPLETED_WITH_WARNINGS},
    },
}


class InvalidTransition(Exception):
    pass


def can_transition(job_type: JobType, current: RunState, target: RunState) -> bool:
    if current in TERMINAL_RUN_STATES:
        return False
    if target in (RunState.FAILED, RunState.CANCELLED):
        return True
    return target in TRANSITIONS[job_type].get(current, set())


def assert_transition(job_type: JobType, current: RunState, target: RunState) -> None:
    if not can_transition(job_type, current, target):
        raise InvalidTransition(f"{job_type}: {current} -> {target} is not allowed")


# Progress bands per stage: (start, end) percent.
_BANDS: dict[JobType, dict[RunState, tuple[int, int]]] = {
    JobType.DOCUMENT_PROCESSING: {
        RunState.QUEUED: (0, 0),
        RunState.PREPROCESSING: (0, 5),
        RunState.PARSING: (5, 60),
        RunState.EXTRACTING: (60, 80),
        RunState.VALIDATING: (80, 88),
        RunState.INDEXING: (88, 99),
    },
    JobType.REVALIDATION: {
        RunState.QUEUED: (0, 0),
        RunState.VALIDATING: (0, 50),
        RunState.INDEXING: (50, 99),
    },
    JobType.REINDEX: {RunState.QUEUED: (0, 0), RunState.INDEXING: (0, 99)},
    JobType.COMPARISON: {RunState.QUEUED: (0, 0), RunState.COMPARING: (0, 99)},
    JobType.RECONCILIATION: {RunState.QUEUED: (0, 0), RunState.COMPARING: (0, 99)},
}


def compute_progress(
    job_type: JobType,
    state: RunState,
    *,
    units_done: int = 0,
    units_total: int = 0,
    previous: Decimal | None = None,
) -> Decimal:
    """Progress from completed work units. Only successful terminal states are 100."""
    if state in _SUCCESS:
        return Decimal("100.00")
    if state in (RunState.FAILED, RunState.CANCELLED):
        return previous if previous is not None else Decimal("0")
    start, end = _BANDS[job_type].get(state, (0, 0))
    fraction = Decimal(units_done) / Decimal(units_total) if units_total > 0 else Decimal(0)
    fraction = min(Decimal(1), max(Decimal(0), fraction))
    value = Decimal(start) + (Decimal(end - start) * fraction)
    return min(Decimal("99.00"), value).quantize(Decimal("0.01"))
