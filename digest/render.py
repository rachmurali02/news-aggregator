"""Render a Digest to HTML and plain text."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import prefs
from .models import Digest

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def short_date(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%b %-d")


_env.filters["short_date"] = short_date
_env.globals["feedback_link"] = prefs.feedback_link


def render_html(digest: Digest, settings_url: str = "") -> str:
    return _env.get_template("digest.html.j2").render(digest=digest, settings_url=settings_url)


def render_text(digest: Digest) -> str:
    lines = [digest.title.upper(), digest.date.strftime("%A, %B %-d, %Y"), "", digest.intro, ""]
    if digest.briefing:
        lines += ["THE 5-MINUTE BRIEFING", "-" * 40]
        lines += [f"{i}. {item['text']} ({item['story'].url})" for i, item in enumerate(digest.briefing, 1)]
        lines.append("")
    if digest.developing:
        lines += ["DEVELOPING STORIES", "-" * 40]
        for s in digest.developing:
            lines.append(f"* {s.title} — {s.source} [Day {len(s.thread) + 1}]")
            if s.update or s.takeaway:
                lines.append(f"  What's new: {s.update or s.takeaway}")
            for past in s.thread:
                lines.append(f"  {short_date(past['date'])}: {past['title']}")
            lines += [f"  {s.url}", ""]
    for section in digest.sections:
        if not section["stories"]:
            continue
        lines += [f"{section['emoji']} {section['label'].upper()}", "-" * 40]
        for s in section["stories"]:
            tag = " [Opinion]" if s.opinion else ""
            lines.append(f"* {s.title} — {s.source}{tag}")
            if s.takeaway or s.summary:
                lines.append(f"  {s.takeaway or s.summary}")
            lines.append(f"  {s.url}")
            lines.append("")
    if digest.word:
        w = digest.word
        lines += ["WORD OF THE DAY", "-" * 40]
        if w.theme:
            lines.append(w.theme)
        lines += [
            f"{w.word} ({w.part_of_speech}) /{w.pronunciation}/",
            w.definition,
            f'"{w.example}"',
        ]
        if w.origin:
            lines.append(f"Origin: {w.origin}")
        if w.related_url:
            lines.append(f"In today's news: {w.related_url}")
        for extra in digest.word_bank:
            lines.append(f"Also: {extra.word} — {extra.definition}")
    return "\n".join(lines) + "\n"
