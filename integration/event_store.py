"""In-memory event store for meeting-competitor-agent integration."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone

from agent_sdk.contract.enums import EventType
from agent_sdk.contract.events import EventRecord

_lock = threading.Lock()
_events: deque[EventRecord] = deque(maxlen=500)


def emit(
    event_type: EventType | str,
    job_name: str,
    *,
    detail: str = "",
    data: dict | None = None,
    run_id: str | None = None,
) -> None:
    if isinstance(event_type, str):
        event_type = EventType(event_type)
    record = EventRecord(
        event_type=event_type,
        job_name=job_name,
        timestamp=datetime.now(timezone.utc),
        detail=detail,
        run_id=run_id,
        data=data or {},
    )
    with _lock:
        _events.appendleft(record)


def get_events(
    job_name: str,
    limit: int = 100,
    since: datetime | None = None,
) -> list[EventRecord]:
    with _lock:
        records = list(_events)
    if since:
        records = [r for r in records if r.timestamp > since]
    records.reverse()
    return records[:limit]
