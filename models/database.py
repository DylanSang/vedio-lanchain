from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config import settings
from models.schemas import WorkflowState

Base = declarative_base()

_DB_PATH = settings.output_dir / "workflow.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class WorkflowRecord(Base):
    __tablename__ = "workflows"

    workflow_id = Column(String(64), primary_key=True)
    topic = Column(String(256), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    state_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


Base.metadata.create_all(engine)


def save_workflow(state: WorkflowState) -> None:
    with SessionLocal() as session:  # type: Session
        record = session.get(WorkflowRecord, state.workflow_id)
        if record is None:
            record = WorkflowRecord(
                workflow_id=state.workflow_id,
                topic=state.topic,
                status=state.status.value,
                state_json=state.model_dump_json(),
                created_at=state.created_at,
                updated_at=datetime.now(),
            )
            session.add(record)
        else:
            record.status = state.status.value
            record.state_json = state.model_dump_json()
            record.updated_at = datetime.now()
        session.commit()


def load_workflow(workflow_id: str) -> WorkflowState | None:
    with SessionLocal() as session:  # type: Session
        record = session.get(WorkflowRecord, workflow_id)
        if record is None:
            return None
        return WorkflowState.model_validate_json(record.state_json)


def list_workflows(limit: int = 20) -> list[WorkflowState]:
    with SessionLocal() as session:  # type: Session
        records = (
            session.query(WorkflowRecord)
            .order_by(WorkflowRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return [WorkflowState.model_validate_json(r.state_json) for r in records]
