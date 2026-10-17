"""Keyword-based personalisation: classify, score, de-duplicate, select."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .models import Story


def _keyword_patterns(sections: dict) -> dict[str, list[re.Pattern]]:
    return {
        key: [re.compile(rf"\b{re.escape(k.lower())}\b") for k in cfg.get("keywords", [])]
        for key, cfg in sections.items()
    }


def keyword_hits(text: str, patterns: list[re.Pattern]) -> int:
    text = text.lower()
    return sum(1 for p in patterns if p.search(text))


def _normalise_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def dedupe(stories: list[Story]) -> list[Story]:
    seen_urls, seen_titles, out = set(), set(), []
    for s in stories:
        url = s.url.split("?")[0].rstrip("/")
        title = _normalise_title(s.title)
        if url in seen_urls or title in seen_titles:
            continue
        seen_urls.add(url)
        seen_titles.add(title)
        out.append(s)
    return out


def score_stories(
    stories: list[Story],
    sections: dict,
    *,
    opinion_boost: float = 1.5,
    lookback_hours: int = 36,
    now: datetime | None = None,
) -> list[Story]:
    """Assign each story a section and a score; drop stories that fit nowhere."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    patterns = _keyword_patterns(sections)
    kept = []
    for s in stories:
        if s.published and s.published < cutoff:
            continue
        text = f"{s.title} {s.summary}"
        hits = {key: keyword_hits(text, pats) for key, pats in patterns.items()}

        if s.feed_section != "auto" and s.feed_section in sections:
            s.section = s.feed_section
            base = 1.0  # pinned feeds are on-topic by construction
        else:
            best = max(hits, key=hits.get) if hits else None
            if not best or hits[best] == 0:
                continue
            s.section = best
            base = 0.0

        relevance = base + hits.get(s.section, 0)
        weight = sections[s.section].get("weight", 1.0)
        if s.published:
            age_h = max((now - s.published).total_seconds() / 3600, 0)
            freshness = 1.0 / (1.0 + age_h / 24)  # halves after a day
        else:
            freshness = 0.5
        s.score = relevance * weight * freshness * (opinion_boost if s.opinion else 1.0)
        kept.append(s)
    return kept


def top_by_section(stories: list[Story], sections: dict, per_section: int) -> dict[str, list[Story]]:
    """Best stories per section, preferring a mix of publications."""
    out: dict[str, list[Story]] = {}
    for key in sections:
        ranked = sorted((s for s in stories if s.section == key), key=lambda s: s.score, reverse=True)
        picked, per_source = [], {}
        for s in ranked:
            if per_source.get(s.source, 0) >= 2 and len(ranked) > per_section * 2:
                continue
            picked.append(s)
            per_source[s.source] = per_source.get(s.source, 0) + 1
            if len(picked) == per_section:
                break
        out[key] = picked
    return out
