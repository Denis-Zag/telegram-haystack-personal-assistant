"""Персональный Telegram-ассистент на Haystack."""

from __future__ import annotations

import os

# Учебный проект не отправляет анонимную телеметрию Haystack.
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "false")
