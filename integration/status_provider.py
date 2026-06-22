"""Status provider for meeting-competitor-agent integration."""

from __future__ import annotations

from agent_sdk.contract.enums import Availability, Health, OperatingState
from agent_sdk.contract.status import AgentStatus

from integration.contract import AGENT_ID, JOB_NAMES
import integration.state as state


def get_all_statuses() -> list[AgentStatus]:
    with state.lock:
        paused = state.paused
        run_count = state.run_count
        last_run_at = state.last_run_at

    op_state = OperatingState.STOPPED if paused else OperatingState.IDLE
    msg = f"{'paused' if paused else 'idle'} — {run_count} run(s) completed"

    detail: dict = {"run_count": run_count}
    if last_run_at:
        detail["last_run_at"] = last_run_at.isoformat()

    return [
        AgentStatus(
            agent_id=AGENT_ID,
            job_name=job_name,
            availability=Availability.ONLINE,
            operating_state=op_state,
            health=Health.HEALTHY,
            message=msg,
            detail=detail,
        )
        for job_name in JOB_NAMES
    ]
