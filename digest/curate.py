"""Optional Claude-powered curation.

Given keyword-ranked candidates and the reader profile, Claude picks the best
stories per section, writes a one-line takeaway for each, an intro line, and a
word of the day drawn from today's news. Any failure falls back to the
keyword ranking, so the digest always goes out.
"""
from __future__ import annotations

import json
import logging
import os

from .models import Story, WordOfTheDay

log = logging.getLogger(__name__)

MODEL = os.environ.get("DIGEST_MODEL", "claude-opus-5-5")

SYSTEM = (
    "You are the editor of a personal morning newsletter built from opinion columns and "
    "analysis at major newspapers. Choose pieces that best match the reader's interests, "
    "favour substantive arguments over routine updates, and keep a mix of publications. "
    "Takeaways are one or two plain sentences (under 40 words) telling the reader the "
    "column's argument or why the story matters — no hype, no repeating the headline. "
    "The word of the day should be a genuinely useful, somewhat advanced English word that "
    "fits one of today's chosen stories; prefer words the reader is unlikely to use daily."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "intro": {"type": "string", "description": "One warm sentence previewing today's themes."},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "stories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "takeaway": {"type": "string"},
                            },
                            "required": ["id", "takeaway"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["key", "stories"],
                "additionalProperties": False,
            },
        },
        "word": {
            "type": "object",
            "properties": {
                "word": {"type": "string"},
                "pronunciation": {"type": "string", "description": "Simple respelling, e.g. hi-JEM-uh-nee"},
                "part_of_speech": {"type": "string"},
                "definition": {"type": "string"},
                "example": {"type": "string", "description": "An example sentence tied to today's news."},
                "origin": {"type": "string"},
                "related_story_id": {"type": "string"},
            },
            "required": ["word", "pronunciation", "part_of_speech", "definition", "example", "origin", "related_story_id"],
            "additionalProperties": False,
        },
    },
    "required": ["intro", "sections", "word"],
    "additionalProperties": False,
}


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _build_prompt(candidates: dict[str, list[Story]], sections_cfg: dict, profile: str, per_section: int) -> str:
    payload = {
        key: [
            {
                "id": s.id,
                "source": s.source,
                "opinion": s.opinion,
                "title": s.title,
                "summary": s.summary,
            }
            for s in stories
        ]
        for key, stories in candidates.items()
    }
    labels = {k: v["label"] for k, v in sections_cfg.items()}
    return (
        f"Reader profile:\n{profile.strip()}\n\n"
        f"Sections (key -> label): {json.dumps(labels)}\n\n"
        f"Pick up to {per_section} stories per section from the candidates below, ordered best "
        "first. Use only the given ids and section keys.\n\n"
        f"Candidates:\n{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )


def curate(candidates: dict[str, list[Story]], sections_cfg: dict, profile: str, per_section: int):
    """Return (selected_by_section, intro, word) or None if curation fails."""
    import anthropic

    client = anthropic.Anthropic()
    try:
        # Server-side fallback re-runs the request on another model if the
        # primary declines, so a refusal doesn't silently drop curation.
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": _build_prompt(candidates, sections_cfg, profile, per_section)}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIStatusError as exc:
        log.warning("Claude curation failed (%s): %s", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError as exc:
        log.warning("Claude curation failed (connection): %s", exc)
        return None

    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("Claude curation stopped early: %s", response.stop_reason)
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Claude curation returned invalid JSON")
        return None

    by_id = {s.id: s for stories in candidates.values() for s in stories}
    selected: dict[str, list[Story]] = {key: [] for key in sections_cfg}
    for section in data["sections"]:
        if section["key"] not in selected:
            continue
        for item in section["stories"][:per_section]:
            story = by_id.get(item["id"])
            if story and story not in selected[section["key"]]:
                story.takeaway = item["takeaway"].strip()
                selected[section["key"]].append(story)

    w = data["word"]
    related = by_id.get(w.get("related_story_id", ""))
    word = WordOfTheDay(
        word=w["word"],
        pronunciation=w["pronunciation"],
        part_of_speech=w["part_of_speech"],
        definition=w["definition"],
        example=w["example"],
        origin=w["origin"],
        related_url=related.url if related else "",
        related_title=related.title if related else "",
    )
    return selected, data["intro"].strip(), word
