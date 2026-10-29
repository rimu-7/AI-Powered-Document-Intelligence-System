from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.jobs.state import InvalidTransition, assert_transition, can_transition, compute_progress
from app.shared.enums import JobType, RunState


def test_document_processing_happy_path() -> None:
    path = [
        RunState.QUEUED,
        RunState.PREPROCESSING,
        RunState.PARSING,
        RunState.EXTRACTING,
        RunState.VALIDATING,
        RunState.INDEXING,
        RunState.COMPLETED,
    ]
    for a, b in zip(path, path[1:], strict=False):
        assert can_transition(JobType.DOCUMENT_PROCESSING, a, b)


@pytest.mark.parametrize(
    ("job", "a", "b"),
    [
        (JobType.DOCUMENT_PROCESSING, RunState.QUEUED, RunState.COMPLETED),
        (JobType.DOCUMENT_PROCESSING, RunState.PARSING, RunState.QUEUED),
        (JobType.DOCUMENT_PROCESSING, RunState.COMPLETED, RunState.FAILED),
        (JobType.REVALIDATION, RunState.QUEUED, RunState.PARSING),
        (JobType.COMPARISON, RunState.QUEUED, RunState.INDEXING),
        (JobType.COMPARISON, RunState.COMPARING, RunState.REQUIRES_REVIEW),
    ],
)
def test_invalid_transitions(job: JobType, a: RunState, b: RunState) -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(job, a, b)


def test_failure_and_cancel_from_any_non_terminal() -> None:
    for state in (RunState.QUEUED, RunState.PARSING, RunState.INDEXING):
        assert can_transition(JobType.DOCUMENT_PROCESSING, state, RunState.FAILED)
        assert can_transition(JobType.DOCUMENT_PROCESSING, state, RunState.CANCELLED)


def test_progress_never_reaches_100_before_terminal_success() -> None:
    for state in (RunState.PARSING, RunState.EXTRACTING, RunState.VALIDATING, RunState.INDEXING):
        assert compute_progress(JobType.DOCUMENT_PROCESSING, state, units_done=10, units_total=10) < 100
    assert compute_progress(JobType.DOCUMENT_PROCESSING, RunState.COMPLETED) == Decimal("100.00")
    assert compute_progress(JobType.DOCUMENT_PROCESSING, RunState.FAILED, previous=Decimal("42")) == Decimal("42")
    half = compute_progress(JobType.DOCUMENT_PROCESSING, RunState.PARSING, units_done=500, units_total=1000)
    assert Decimal("5") < half < Decimal("60")
