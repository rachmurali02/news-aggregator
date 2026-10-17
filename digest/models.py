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
    # Filled by the Claude curator when enabled.
    takeaway: str = ""

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


@dataclass
class Digest:
    title: str
    date: datetime
    intro: str
    sections: list[dict] = field(default_factory=list)  # {key, label, emoji, stories}
    word: WordOfTheDay | None = None
    curated_by_claude: bool = False

    @property
    def story_count(self) -> int:
        return sum(len(s["stories"]) for s in self.sections)

    @property
    def source_count(self) -> int:
        return len({st.source for s in self.sections for st in s["stories"]})
