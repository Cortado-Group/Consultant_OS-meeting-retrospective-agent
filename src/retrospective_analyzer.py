"""OpenAI wrapper for retrospective meeting lesson extraction."""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_MIN_WORDS = 80
_MAX_TRANSCRIPT_CHARS = 16_000
_MAX_RETRIES = 2

_VALID_CATEGORIES = {"process", "technology", "people", "communication", "planning", "other"}

_RETRO_KEYWORDS = ("retrospective", "retro", "post mortem", "post-mortem", "postmortem")

_SYSTEM_PROMPT = (
    "You are a retrospective facilitator analyzing a meeting transcript. "
    "Extract concrete, actionable lessons learned.\n\n"
    "For each lesson identify:\n"
    "- title: concise lesson name (max 120 chars)\n"
    "- description: what happened and why it matters (2-4 sentences)\n"
    "- category: one of 'process', 'technology', 'people', 'communication', 'planning', 'other'\n"
    "- recommendation: specific actionable advice for the future (1-2 sentences)\n"
    "- bucket: 'positive' (what went well) or 'improvement' (what needs fixing)\n\n"
    "Extract ONLY substantive lessons — skip vague, generic, or trivial observations.\n\n"
    "Respond ONLY with JSON:\n"
    "{\"lessons\": [{\"title\": \"...\", \"description\": \"...\", "
    "\"category\": \"process\", \"recommendation\": \"...\", \"bucket\": \"improvement\"}]}\n\n"
    "Return {\"lessons\": []} if no clear lessons are identifiable."
)


def _strip_vtt(text: str) -> str:
    """Remove WebVTT timestamps and headers, leaving only spoken text."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or re.match(r"^\d+$", line):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", line):
            continue
        lines.append(line)
    return " ".join(lines)


def is_retrospective_meeting(meeting: dict) -> bool:
    """Return True if the meeting's type name contains a retro keyword."""
    type_name = (meeting.get("meeting_type_name") or "").lower()
    return any(kw in type_name for kw in _RETRO_KEYWORDS)


class RetrospectiveAnalyzer:
    """Analyze a retrospective transcript and return lessons learned."""

    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def analyze(self, transcript: str) -> list[dict]:
        """Return list of lesson dicts. Empty list on failure or too-brief transcript."""
        clean = _strip_vtt(transcript)
        if len(clean.split()) < _MIN_WORDS:
            logger.info("retro_analyzer.too_brief words=%d", len(clean.split()))
            return []

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": clean[:_MAX_TRANSCRIPT_CHARS]},
                    ],
                    temperature=0.3,
                    max_tokens=3000,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or "{}"
                parsed = json.loads(raw)
                lessons = parsed.get("lessons", [])
                validated = []
                for item in lessons:
                    if not isinstance(item, dict):
                        continue
                    title = (item.get("title") or "").strip()
                    if not title:
                        continue
                    category = item.get("category", "other")
                    if category not in _VALID_CATEGORIES:
                        category = "other"
                    validated.append({
                        "title": title[:120],
                        "description": (item.get("description") or "").strip(),
                        "category": category,
                        "recommendation": (item.get("recommendation") or "").strip(),
                        "bucket": item.get("bucket", "improvement"),
                    })
                return validated
            except Exception as exc:
                logger.error(
                    "retro_analyzer.failed attempt=%d error=%s", attempt, exc, exc_info=True
                )
                if attempt == _MAX_RETRIES:
                    return []

        return []
