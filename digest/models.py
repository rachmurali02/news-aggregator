from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Story:
    title: str
    url: str
    source: str
    summary: str = ""
    published: datetime | None = None
    author: str = ""
    opinion: bool = False
    # Section the feed is pinned to, or "auto" to classify by keywords.
    feed_section: str = "auto"
    section: str | None = None
    score: float = 0.0
    # Filled by the LLM curator when enabled.
    takeaway: str = ""
    # Earlier digest entries this story continues ({date, title, url, source}),
    # oldest first, and the id shared by every story in that thread.
    thread: list[dict] = field(default_factory=list)
    thread_id: str = ""
    # What changed since the last instalment (LLM, when enabled).
    update: str = ""

    @property
    def id(self) -> str:
        return hashlib.sha1(self.url.encode()).hexdigest()[:8]


@dataclass
class WordOfTheDay:
    word: str
    pronunciation: str
    part_of_speech: str
    definition: str
    example: str
    origin: str = ""
    # Optional link to a story in today's digest where the word fits.
    related_url: str = ""
    related_title: str = ""
    # One line on why this word fits today's news.
    theme: str = ""


@dataclass
class Digest:
    title: str
    date: datetime
    intro: str
    sections: list[dict] = field(default_factory=list)  # {key, label, emoji, stories}
    # 5-minute briefing: [{"text": str, "story": Story}]
    briefing: list[dict] = field(default_factory=list)
    developing: list[Story] = field(default_factory=list)
    word: WordOfTheDay | None = None
    word_bank: list[WordOfTheDay] = field(default_factory=list)
    # Human-readable notes on how the edition is tuned to the reader.
    tuning: list[str] = field(default_factory=list)
    reader_name: str = ""
    # Address that "more/less like this" feedback emails go to.
    feedback_to: str = ""
    # Feeds empty for several days running: [{"name", "url", "days"}]
    flagged_feeds: list[dict] = field(default_factory=list)
    curated_by_ai: bool = False

    @property
    def all_stories(self) -> list[Story]:
        return self.developing + [st for s in self.sections for st in s["stories"]]

    @property
    def story_count(self) -> int:
        return len(self.all_stories)

    @property
    def source_count(self) -> int:
        return len({st.source for st in self.all_stories})
