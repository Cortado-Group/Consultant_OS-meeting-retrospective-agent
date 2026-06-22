"""SDK-backed integration server for meeting-retrospective-agent."""
from __future__ import annotations
import logging
import os
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO)
from agent_sdk.contract.enums import EventType
from agent_sdk.integration.server import create_integration_app
from integration.action_registry import actions
from integration.contract import manifest
from integration.event_provider import get_events
from integration.event_store import emit
from integration.status_provider import get_all_statuses

flask_app = create_integration_app(
    manifest, get_all_statuses, actions,
    event_provider=get_events,
    auth_token=os.environ.get("RETRO_AGENT_TOKEN") or None,
)
emit(EventType.ONLINE, "retrospective_extraction", detail="meeting-retrospective-agent integration server started")

if __name__ == "__main__":
    host = os.environ.get("INTEGRATION_HOST", "127.0.0.1")
    port = int(os.environ.get("INTEGRATION_PORT", "8101"))
    logging.getLogger(__name__).info("Starting meeting-retrospective-agent on %s:%d", host, port)
    flask_app.run(host=host, port=port, debug=False)
