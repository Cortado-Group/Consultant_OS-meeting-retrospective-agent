"""HTTP client for the django_project REST API — meeting retrospective agent operations."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)
_TIMEOUT = 20


class DjangoApiClient:
    def __init__(self) -> None:
        base = os.environ.get("DJANGO_API_BASE_URL", "").rstrip("/")
        token = os.environ.get("DJANGO_API_TOKEN", "")
        basic_user = os.environ.get("DJANGO_API_BASIC_USER", "webhook")
        basic_secret = os.environ.get("DJANGO_API_BASIC_SECRET", "")
        if not base:
            raise RuntimeError("DJANGO_API_BASE_URL is not set")
        if not token:
            raise RuntimeError("DJANGO_API_TOKEN is not set")
        self._base = base
        self._headers = {"X-API-Token": token, "Content-Type": "application/json"}
        self._auth = (basic_user, basic_secret) if basic_secret else None

    def _get(self, path: str, **params) -> dict:
        resp = requests.get(
            f"{self._base}{path}", headers=self._headers,
            params=params, auth=self._auth, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: dict) -> dict:
        resp = requests.post(
            f"{self._base}{path}", json=payload,
            headers=self._headers, auth=self._auth, timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def get_recent_meetings(self, lookback_hours: int = 48) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
        url = f"{self._base}/api/v1/meetings/?occurred_after={since}"
        meetings: list[dict] = []
        while url:
            resp = requests.get(url, headers=self._headers, auth=self._auth, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            meetings.extend(data.get("results", []))
            url = data.get("next")
        return meetings

    def get_meeting_detail(self, guid: str) -> dict:
        return self._get(f"/api/v1/meetings/{guid}/")

    def has_lessons(self, guid: str) -> bool:
        data = self._get(f"/api/v1/lessons/", meeting=guid)
        return len(data.get("results", [])) > 0

    def create_lesson(self, meeting_guid: str, lesson: dict) -> dict:
        payload = {
            "title": lesson["title"],
            "description": lesson.get("description", ""),
            "category": lesson.get("category", "other"),
            "recommendation": lesson.get("recommendation", ""),
            "status": "draft",
            "meeting": meeting_guid,
            "tags": [],
        }
        return self._post("/api/v1/lessons/", payload)
