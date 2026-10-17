"""Download and parse RSS/Atom feeds into Story objects."""
from __future__ import annotations

import html
import logging
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser

from .models import Story

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; news-aggregator-digest/1.0)"
TIMEOUT = 20

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str, limit: int = 320) -> str:
    text = html.unescape(_TAG_RE.sub(" ", raw or ""))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + "…"
    return text


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def parse_feed(content: bytes, source: dict) -> list[Story]:
    parsed = feedparser.parse(content)
    stories = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title", ""), limit=200)
        url = entry.get("link", "")
        if not title or not url:
            continue
        stories.append(
            Story(
                title=title,
                url=url,
                source=source["name"],
                summary=clean_text(entry.get("summary", "") or entry.get("description", "")),
                published=_published(entry),
                author=clean_text(entry.get("author", ""), limit=80),
                opinion=bool(source.get("opinion", False)),
                feed_section=source.get("section", "auto"),
            )
        )
    return stories


def fetch_source(source: dict) -> list[Story]:
    req = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            content = resp.read()
    except Exception as exc:  # one bad feed must not sink the digest
        log.warning("Failed to fetch %s (%s): %s", source["name"], source["url"], exc)
        return []
    stories = parse_feed(content, source)
    log.info("Fetched %d stories from %s", len(stories), source["url"])
    return stories


def fetch_all(sources: list[dict]) -> list[Story]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(fetch_source, sources)
    return [story for batch in results for story in batch]
