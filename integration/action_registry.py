"""Action registry for meeting-competitor-agent integration."""
from __future__ import annotations
import logging
from agent_sdk.contract.actions import ActionRequest, ActionResult
from integration import control_adapter
from integration.contract import ACTION_NAMES, JOB_NAMES
logger = logging.getLogger(__name__)
_ACTION_REJECTED = "agent.action.rejected"
def _require_job_name(request):
    if request.job_name:
        return request.job_name, None
    return None, "job_name is required"
def _to_action_result(action_name, result):
    accepted = bool(result.get("ok"))
    message = str(result.get("message") or f"{action_name} {'accepted' if accepted else 'rejected'}")
    data = {"action": action_name}
    for key in ("job_name", "paused", "revoked"):
        value = result.get(key)
        if value is not None:
            data[key] = value
    return ActionResult(accepted=accepted, message=message, data=data)
def _make_handler(action_name):
    def _handler(request):
        job_name, error = _require_job_name(request)
        if error is not None:
            return ActionResult(accepted=False, message=error)
        if job_name not in JOB_NAMES:
            return ActionResult(accepted=False, message=f"unknown job_name: {job_name}")
        fn = getattr(control_adapter, action_name, None)
        if fn is None:
            return ActionResult(accepted=False, message=f"unsupported action: {action_name}")
        kwargs = dict(request.payload)
        kwargs.setdefault("actor", "sdk")
        kwargs.setdefault("correlation_id", request.correlation_id)
        try:
            result = fn(job_name, **kwargs)
        except Exception as exc:
            return ActionResult(accepted=False, message=str(exc))
        return _to_action_result(action_name, result)
    return _handler
def _build_action_registry():
    missing = [n for n in ACTION_NAMES if not callable(getattr(control_adapter, n, None))]
    if missing:
        raise ValueError(f"control_adapter missing callable action(s): {', '.join(missing)}")
    return {name: _make_handler(name) for name in ACTION_NAMES}
actions = _build_action_registry()
