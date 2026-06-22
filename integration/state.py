"""Shared in-memory state for meeting-competitor-agent integration."""

from __future__ import annotations

import threading
from datetime import datetime

lock = threading.Lock()
paused: bool = False
run_count: int = 0
last_run_at: datetime | None = None
