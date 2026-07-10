"""Centralized environment configuration. Nothing here does I/O beyond reading
env vars — read once at import time so the rest of the app treats these as
plain constants.
"""

import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

MAX_TICKET_CHARS = int(os.environ.get("MAX_TICKET_CHARS", "2000"))

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
).split(",")
