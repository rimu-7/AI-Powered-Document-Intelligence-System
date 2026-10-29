"""Re-embed documents whose search chunks were built with another embedding model.

  python -m scripts.reindex            # only documents with stale or missing embeddings
  python -m scripts.reindex --all      # every document
Creates one REINDEX job per document (through the transactional outbox).
"""

from __future__ import annotations

import argparse
import uuid

from sqlalchemy import exists, select

from app.core.config import get_settings
from app.core.database import sync_session
from app.modules.documents.models import Document, DocumentChunk
from app.modules.jobs.models import ProcessingRun
from app.modules.jobs.outbox import new_task_with_event
from app.shared.enums import TERMINAL_RUN_STATES, DocumentStatus, JobType, RunState, TaskType

READY = (DocumentStatus.COMPLETED, DocumentStatus.COMPLETED_WITH_WARNINGS, DocumentStatus.REQUIRES_REVIEW)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    model = get_settings().embedding_model
    with sync_session() as session:
        stmt = select(Document).where(Document.deleted_at.is_(None), Document.status.in_(READY))
        if not args.all:
            stmt = stmt.where(~exists().where(DocumentChunk.document_id == Document.id, DocumentChunk.embedding_model == model))
        busy = select(ProcessingRun.document_id).where(
            ProcessingRun.state.not_in(list(TERMINAL_RUN_STATES)), ProcessingRun.document_id.is_not(None)
        )
        docs = session.execute(stmt.where(Document.id.not_in(busy))).scalars().all()
        for doc in docs:
            run = ProcessingRun(
                id=uuid.uuid4(),
                organization_id=doc.organization_id,
                document_id=doc.id,
                job_type=JobType.REINDEX,
                state=RunState.QUEUED,
                payload_json={"reason": f"embedding model {model}"},
                stage_history_json=[],
            )
            session.add(run)
            session.flush()
            session.add_all(new_task_with_event(run, TaskType.INDEX))
        session.commit()
    print(f"queued {len(docs)} reindex job(s) for embedding model {model}")


if __name__ == "__main__":
    main()
