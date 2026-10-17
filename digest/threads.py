"""Developing stories: link today's stories to ones sent on earlier days."""
from __future__ import annotations

import re
from datetime import datetime

from .models import Story

STOPWORDS = {
    "about", "after", "again", "against", "amid", "says", "said", "will", "would", "could",
    "should", "their", "there", "these", "those", "this", "that", "with", "from", "into",
    "over", "under", "what", "when", "where", "which", "while", "who", "why", "how", "your",
    "have", "has", "had", "been", "being", "more", "most", "than", "then", "they", "them",
    "it's", "isn't", "just", "like", "make", "made", "new", "news", "first", "last", "year",
    "years", "week", "today", "still", "back", "only", "also", "very", "really", "here",
    "live", "latest", "update", "updates", "opinion", "analysis", "view", "guardian", "need",
    "does", "doesn't", "can't", "won't", "were", "many", "much", "some", "every", "people",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")


def terms(text: str) -> set[str]:
    """Distinctive words of a headline: lowercase, 4+ letters, no stopwords."""
    out = set()
    for w in _WORD_RE.findall(text):
        w = w.lower().strip("'-")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) >= 4 and w not in STOPWORDS:
            out.add(w)
    return out


def similar(a: set[str], b: set[str]) -> bool:
    shared = a & b
    return len(shared) >= 2 and len(shared) / max(min(len(a), len(b)), 1) >= 0.4


def attach(stories: list[Story], history: list[dict], today: str) -> None:
    """Mark stories that continue a thread from earlier days' digests."""
    past = [(h, terms(h["title"])) for h in history if h["date"] < today]
    for s in stories:
        mine = terms(s.title)
        matches = [h for h, t in past if h["url"] != s.url and similar(mine, t)]
        if not matches:
            continue
        # Follow the most recent match's thread so the timeline stays coherent.
        latest = max(matches, key=lambda h: h["date"])
        thread_id = latest.get("thread_id") or latest["id"]
        chain = [h for h, _ in past if (h.get("thread_id") or h["id"]) == thread_id]
        chain.sort(key=lambda h: h["date"])
        s.thread_id = thread_id
        s.thread = [{k: h[k] for k in ("date", "title", "url", "source")} for h in chain[-3:]]


def sent_urls(history: list[dict]) -> set[str]:
    return {h["url"] for h in history}


def record(history: list[dict], stories: list[Story], now: datetime) -> None:
    day = now.date().isoformat()
    for s in stories:
        history.append(
            {
                "id": s.id,
                "date": day,
                "title": s.title,
                "url": s.url,
                "source": s.source,
                "section": s.section,
                "thread_id": s.thread_id or s.id,
            }
        )
