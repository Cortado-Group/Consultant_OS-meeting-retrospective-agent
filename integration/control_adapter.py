"""Control adapter for meeting-retrospective-agent."""
from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime, timezone

from agent_sdk.contract.enums import EventType

import integration.state as state
from integration.event_store import emit
from integration.slack_notifier import SlackNotifier

logger = logging.getLogger(__name__)

_slack = SlackNotifier("meeting-retrospective-agent")

_SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_LOOKBACK_HOURS = int(os.environ.get("RETRO_LOOKBACK_HOURS", "48"))
_MAX_MEETINGS_PER_RUN = int(os.environ.get("RETRO_MAX_PER_RUN", "10"))


def _run_retro_pass() -> dict:
    """Single pass: fetch retrospective meetings without lessons, analyze, write back."""
    from retrospective_analyzer import RetrospectiveAnalyzer, is_retrospective_meeting
    from integration.django_api_client import DjangoApiClient

    client = DjangoApiClient()
    analyzer = RetrospectiveAnalyzer()

    meetings = client.get_recent_meetings(_LOOKBACK_HOURS)
    logger.info("retro_pass.meetings_fetched count=%d", len(meetings))

    created = skipped = processed = 0

    for meeting in meetings:
        if processed >= _MAX_MEETINGS_PER_RUN:
            break

        guid = meeting.get("guid", "")

        if not is_retrospective_meeting(meeting):
            skipped += 1
            continue

        if not meeting.get("has_transcript"):
            skipped += 1
            continue

        if client.has_lessons(guid):
            logger.debug("retro_pass.skip_has_lessons guid=%s", guid)
            skipped += 1
            continue

        detail = client.get_meeting_detail(guid)
        transcript = (detail.get("transcript") or "").strip()
        if not transcript:
            skipped += 1
            continue

        processed += 1
        logger.info("retro_pass.analyzing guid=%s name=%r", guid, meeting.get("name", guid))

        lessons = analyzer.analyze(transcript)
        if not lessons:
            logger.info("retro_pass.no_lessons guid=%s", guid)
            continue

        for lesson in lessons:
            try:
                client.create_lesson(guid, lesson)
                created += 1
            except Exception as exc:
                logger.error("retro_pass.create_failed guid=%s error=%s", guid, exc)

        logger.info("retro_pass.done guid=%s lessons_created=%d", guid, created)

    return {"created": created, "skipped": skipped, "processed": processed}


def start(job_name: str, **kwargs) -> dict:
    correlation_id = kwargs.get("correlation_id")
    emit(EventType.STARTED, job_name, detail="start: clearing pause flag",
         data={"correlation_id": correlation_id} if correlation_id else None)
    with state.lock:
        state.paused = False
    emit(EventType.COMPLETED, job_name, detail="start: pause flag cleared",
         data={"correlation_id": correlation_id} if correlation_id else None)
    return {"job_name": job_name, "action": "start", "ok": True,
            "paused": False, "message": "Pause cleared. Runs will proceed."}


def soft_stop(job_name: str, **kwargs) -> dict:
    correlation_id = kwargs.get("correlation_id")
    emit(EventType.STARTED, job_name, detail="soft_stop: setting pause flag",
         data={"correlation_id": correlation_id} if correlation_id else None)
    with state.lock:
        state.paused = True
    emit(EventType.COMPLETED, job_name, detail="soft_stop: pause flag set",
         data={"correlation_id": correlation_id} if correlation_id else None)
    return {"job_name": job_name, "action": "soft_stop", "ok": True,
            "paused": True, "message": "Paused. Active work drains naturally."}


def hard_stop(job_name: str, **kwargs) -> dict:
    correlation_id = kwargs.get("correlation_id")
    emit(EventType.STARTED, job_name, detail="hard_stop: setting pause flag",
         data={"correlation_id": correlation_id} if correlation_id else None)
    with state.lock:
        state.paused = True
    emit(EventType.COMPLETED, job_name, detail="hard_stop: paused",
         data={"correlation_id": correlation_id} if correlation_id else None)
    return {"job_name": job_name, "action": "hard_stop", "ok": True,
            "paused": True, "revoked": 0, "message": "Hard-stopped."}


def manual_ping(job_name: str, **kwargs) -> dict:
    correlation_id = kwargs.get("correlation_id")
    emit(EventType.STARTED, job_name, detail="manual_ping: probing",
         data={"correlation_id": correlation_id} if correlation_id else None)
    with state.lock:
        paused = state.paused
    try:
        from integration.django_api_client import DjangoApiClient
        DjangoApiClient()._get("/api/v1/meetings/", occurred_after="2099-01-01")
        probe_msg = "pong — Django API reachable"
    except Exception as err:
        probe_msg = f"pong (Django API unreachable: {err})"
    emit(EventType.COMPLETED, job_name, detail=f"manual_ping: {probe_msg}",
         data={"correlation_id": correlation_id} if correlation_id else None)
    return {"job_name": job_name, "action": "manual_ping", "ok": True,
            "paused": paused, "message": probe_msg}


def run(job_name: str, **kwargs) -> dict:
    """Controller timer target — returns immediately, runs in background."""
    correlation_id = kwargs.get("correlation_id")
    emit(EventType.STARTED, job_name, detail="run: starting retro extraction pass (background)",
         data={"correlation_id": correlation_id} if correlation_id else None)

    def _worker():
        _slack.notify("Run started")
        try:
            result = _run_retro_pass()
            with state.lock:
                state.run_count += 1
                state.last_run_at = datetime.now(timezone.utc)
                count = state.run_count
            msg = (f"run #{count}: processed {result['processed']} meeting(s), "
                   f"created {result['created']} lesson(s), skipped {result['skipped']}")
            logger.info("control.run.completed %s", msg)
            _slack.notify(f"Run complete — processed {result['processed']}, "
                          f"created {result['created']} lesson(s), skipped {result['skipped']}")
            emit(EventType.COMPLETED, job_name, detail=msg,
                 data={"correlation_id": correlation_id} if correlation_id else None)
        except Exception as err:
            logger.error("control.run.failed error=%s", err, exc_info=True)
            _slack.notify(f"Run FAILED: {err}")
            emit(EventType.FAILED, job_name, detail=f"run failed: {err}",
                 data={"correlation_id": correlation_id} if correlation_id else None)

    threading.Thread(target=_worker, daemon=True, name=f"run-{correlation_id or 'noid'}").start()
    return {"job_name": job_name, "action": "run", "ok": True,
            "message": "retrospective extraction started (background)"}


def manual_run(job_name: str, **kwargs) -> dict:
    """Single-pass run, only permitted while paused."""
    correlation_id = kwargs.get("correlation_id")
    with state.lock:
        paused = state.paused

    if not paused:
        emit(EventType.FAILED, job_name, detail="manual_run rejected: job is not paused",
             data={"correlation_id": correlation_id} if correlation_id else None)
        return {"job_name": job_name, "action": "manual_run", "ok": False,
                "paused": False, "message": "manual_run is only allowed while job is paused."}

    emit(EventType.STARTED, job_name, detail="manual_run: starting retro extraction pass",
         data={"correlation_id": correlation_id} if correlation_id else None)
    _slack.notify("Manual run started")
    try:
        result = _run_retro_pass()
        with state.lock:
            state.run_count += 1
            state.last_run_at = datetime.now(timezone.utc)
            count = state.run_count
        msg = (f"manual_run #{count}: processed {result['processed']} meeting(s), "
               f"created {result['created']} lesson(s), skipped {result['skipped']}")
        _slack.notify(f"Manual run complete — processed {result['processed']}, "
                      f"created {result['created']} lesson(s), skipped {result['skipped']}")
        emit(EventType.COMPLETED, job_name, detail=msg,
             data={"correlation_id": correlation_id} if correlation_id else None)
        return {"job_name": job_name, "action": "manual_run", "ok": True,
                "paused": True, "message": msg, **result}
    except Exception as err:
        logger.error("control.manual_run.failed error=%s", err, exc_info=True)
        _slack.notify(f"Manual run FAILED: {err}")
        emit(EventType.FAILED, job_name, detail=f"manual_run failed: {err}",
             data={"correlation_id": correlation_id} if correlation_id else None)
        return {"job_name": job_name, "action": "manual_run", "ok": False,
                "paused": True, "message": str(err)}
