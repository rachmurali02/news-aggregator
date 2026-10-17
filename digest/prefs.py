"""Personalisation learned from reader feedback.

Each story in the email has "More like this" / "Less like this" links. They
open a pre-filled email to the reader's own inbox; the next run reads those
emails over IMAP (same Gmail app password as SMTP), nudges the learned weights
for that story's section, publication and topic words, then archives them.
"""
from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parseaddr
from urllib.parse import quote

from . import threads
from .models import Story

log = logging.getLogger(__name__)

SUBJECT_TAG = "[digest-feedback]"
_SUBJECT_RE = re.compile(r"digest-feedback\]\s*(more|less)\s+([0-9a-f]{8})", re.I)

SECTION_STEP, SECTION_RANGE = 0.15, (0.5, 2.0)
SOURCE_STEP, SOURCE_RANGE = 0.1, (0.6, 1.6)
TERM_RANGE = (-3, 3)


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


def feedback_link(to: str, direction: str, story: Story) -> str:
    subject = f"{SUBJECT_TAG} {direction} {story.id}"
    body = (
        f"Just hit send. Tomorrow's digest will show {direction} stories like:\n"
        f"{story.title}"
    )
    return f"mailto:{to}?subject={quote(subject)}&body={quote(body)}"


def apply(stories: list[Story], prefs: dict) -> None:
    """Scale story scores by learned section, source and topic preferences."""
    sections, sources, term_w = prefs.get("sections", {}), prefs.get("sources", {}), prefs.get("terms", {})
    for s in stories:
        affinity = sum(term_w.get(t, 0) for t in threads.terms(s.title))
        term_factor = 1 + _clamp(0.1 * affinity, (-0.4, 0.5))
        s.score *= sections.get(s.section, 1.0) * sources.get(s.source, 1.0) * term_factor


def learn(prefs: dict, entry: dict, direction: str) -> None:
    sign = 1 if direction == "more" else -1
    sec, src = entry.get("section"), entry.get("source")
    if sec:
        prefs["sections"][sec] = round(_clamp(prefs["sections"].get(sec, 1.0) + sign * SECTION_STEP, SECTION_RANGE), 3)
    if src:
        prefs["sources"][src] = round(_clamp(prefs["sources"].get(src, 1.0) + sign * SOURCE_STEP, SOURCE_RANGE), 3)
    for t in threads.terms(entry.get("title", "")):
        prefs["terms"][t] = int(_clamp(prefs["terms"].get(t, 0) + sign, TERM_RANGE))
    prefs["terms"] = {t: v for t, v in prefs["terms"].items() if v}


def apply_feedback(state: dict, events: list[tuple[str, str, str]], now: datetime) -> int:
    """Apply (message_id, direction, story_id) events; returns how many were used."""
    by_id = {h["id"]: h for h in state["history"]}
    done = set(state["processed_feedback"])
    used = 0
    for msg_id, direction, story_id in events:
        if msg_id in done:
            continue
        done.add(msg_id)
        state["processed_feedback"].append(msg_id)
        entry = by_id.get(story_id)
        if not entry:
            continue
        learn(state["prefs"], entry, direction)
        state["feedback_log"].append(
            {"date": now.date().isoformat(), "direction": direction, "story_id": story_id, "title": entry["title"]}
        )
        used += 1
    return used


def fetch_feedback_emails(allowed_senders: set[str]) -> list[tuple[str, str, str]]:
    """Read feedback emails from the inbox over IMAP and archive them."""
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not user or not password:
        return []
    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    events = []
    try:
        with imaplib.IMAP4_SSL(host, timeout=30) as imap:
            imap.login(user, password)
            imap.select("INBOX")
            _, data = imap.search(None, f'(SUBJECT "{SUBJECT_TAG}")')
            nums = data[0].split() if data and data[0] else []
            for num in nums:
                _, msg_data = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID)])")
                msg = email.message_from_bytes(msg_data[0][1])
                sender = parseaddr(msg.get("From", ""))[1].lower()
                subject = str(make_header(decode_header(msg.get("Subject", ""))))
                match = _SUBJECT_RE.search(subject)
                if match and sender in allowed_senders:
                    events.append((msg.get("Message-ID", f"imap-{num.decode()}"), match[1].lower(), match[2].lower()))
                # In Gmail, deleting from INBOX over IMAP archives the message.
                imap.store(num, "+FLAGS", "\\Deleted")
            if nums:
                imap.expunge()
    except Exception as exc:  # feedback is a nice-to-have; never block the digest
        log.warning("Could not read feedback emails: %s", exc)
    log.info("Found %d feedback emails", len(events))
    return events


def describe(prefs: dict, sections_cfg: dict) -> list[str]:
    """Short notes for the 'Your edition' box."""
    notes = []
    for key, weight in sorted(prefs.get("sections", {}).items(), key=lambda kv: -abs(kv[1] - 1)):
        if key in sections_cfg and abs(weight - 1) >= 0.1:
            label = sections_cfg[key]["label"]
            notes.append(f"{'More' if weight > 1 else 'Less'} {label}")
    for src, weight in sorted(prefs.get("sources", {}).items(), key=lambda kv: -kv[1]):
        if weight >= 1.2:
            notes.append(f"Favouring {src}")
        elif weight <= 0.8:
            notes.append(f"Fewer from {src}")
    liked = [t for t, v in sorted(prefs.get("terms", {}).items(), key=lambda kv: -kv[1]) if v >= 2][:4]
    if liked:
        notes.append("Following: " + ", ".join(liked))
    return notes[:6]
