"""Memory between runs, stored encrypted in state.enc.

Holds the stories already sent (for developing-story threads and repeat
avoidance), learned reader preferences, processed feedback emails and words
already used. Encrypted with the same DIGEST_SECRET_KEY as credentials.enc,
because reading behaviour is personal and the repo is public.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import InvalidToken

from .credentials import KEY_ENV, _fernet

log = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "state.enc"
HISTORY_DAYS = 21


def empty() -> dict:
    return {
        "history": [],  # [{id, date, title, url, source, section, thread_id}]
        "prefs": {"sections": {}, "sources": {}, "terms": {}},
        "feedback_log": [],  # [{date, direction, story_id, title}]
        "processed_feedback": [],  # Message-IDs already applied
        "used_words": [],
        "feed_health": {},  # url -> {name, empty_streak, last_empty, last_ok, ...}
    }


def load(path: Path = DEFAULT_PATH) -> dict:
    state = empty()
    if not os.environ.get(KEY_ENV) or not path.exists():
        return state
    try:
        state.update(json.loads(_fernet().decrypt(path.read_bytes())))
    except InvalidToken:
        log.warning("Could not decrypt %s; starting with fresh state", path.name)
    return state


def save(state: dict, now: datetime, path: Path = DEFAULT_PATH) -> bool:
    if not os.environ.get(KEY_ENV):
        log.info("No %s; state not saved", KEY_ENV)
        return False
    cutoff = (now - timedelta(days=HISTORY_DAYS)).date().isoformat()
    state["history"] = [h for h in state["history"] if h["date"] >= cutoff]
    state["feedback_log"] = state["feedback_log"][-200:]
    state["processed_feedback"] = state["processed_feedback"][-500:]
    state["used_words"] = state["used_words"][-365:]
    path.write_bytes(_fernet().encrypt(json.dumps(state, sort_keys=True).encode()))
    return True
