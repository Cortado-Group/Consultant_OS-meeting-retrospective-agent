"""SDK event provider adapter for meeting-competitor-agent integration."""

from __future__ import annotations

from datetime import datetime

from agent_sdk.contract.events import EventRecord

from integration.contract import JOB_NAMES
from integration.event_store import get_events as _store_get_events


def get_events(
    job_name: str,
    limit: int = 100,
    since: datetime | None = None,
) -> list[EventRecord]:
    if job_name not in JOB_NAMES:
        raise ValueError(f"unknown job: {job_name!r}")
    return _store_get_events(job_name, limit=limit, since=since)
