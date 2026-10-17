"""Render a Digest to HTML and plain text."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import Digest

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(digest: Digest, settings_url: str = "") -> str:
    return _env.get_template("digest.html.j2").render(digest=digest, settings_url=settings_url)


def render_text(digest: Digest) -> str:
    lines = [digest.title.upper(), digest.date.strftime("%A, %B %-d, %Y"), "", digest.intro, ""]
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
        lines += [
            "WORD OF THE DAY",
            "-" * 40,
            f"{w.word} ({w.part_of_speech}) /{w.pronunciation}/",
            w.definition,
            f'"{w.example}"',
        ]
        if w.origin:
            lines.append(f"Origin: {w.origin}")
        if w.related_url:
            lines.append(f"In today's news: {w.related_url}")
    return "\n".join(lines) + "\n"
