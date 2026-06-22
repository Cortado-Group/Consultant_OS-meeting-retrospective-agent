"""Slack webhook notifier — posts to shared Make.com → Slack channel with per-agent header."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


class SlackNotifier:
    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name
        self._url = os.environ.get("SLACK_WEBHOOK_URL", "")

    def notify(self, text: str) -> None:
        """POST a message to Slack. Silently no-ops if SLACK_WEBHOOK_URL is unset."""
        if not self._url:
            return
        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*[{self._agent_name}]*\n{text}",
                    },
                }
            ]
        }
        try:
            requests.post(self._url, json=payload, timeout=5)
        except Exception as exc:
            logger.warning("slack_notifier.failed error=%s", exc)
