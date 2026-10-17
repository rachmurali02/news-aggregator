"""Optional LLM curation through OpenRouter.

Given keyword-ranked candidates and the reader profile, the model picks the
best stories per section, writes a one-line takeaway for each, an intro line,
and a word of the day drawn from today's news. Free (`:free`) OpenRouter models
come and go, so several are tried in order. Any failure falls back to the
keyword ranking, so the digest always goes out.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request

from .models import Story, WordOfTheDay

log = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 180

# All $0 on OpenRouter; tried in order until one answers with valid JSON.
DEFAULT_MODELS = [
    "microsoft/mai-ds-r1:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-26b-a4b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

SYSTEM = (
    "You are the editor of a personal morning newsletter built from opinion columns and "
    "analysis at major newspapers. Choose pieces that best match the reader's interests, "
    "favour substantive arguments over routine updates, and keep a mix of publications. "
    "Takeaways are one or two plain sentences (under 40 words) telling the reader the "
    "column's argument or why the story matters — no hype, no repeating the headline. "
    "The word of the day should be a genuinely useful, somewhat advanced English word that "
    "fits one of today's chosen stories; prefer words the reader is unlikely to use daily. "
    "Reply with a single JSON object and nothing else."
)

RESPONSE_SHAPE = {
    "intro": "One warm sentence previewing today's themes.",
    "sections": [{"key": "<section key>", "stories": [{"id": "<candidate id>", "takeaway": "<1-2 sentences>"}]}],
    "word": {
        "word": "...",
        "pronunciation": "simple respelling, e.g. hi-JEM-uh-nee",
        "part_of_speech": "...",
        "definition": "...",
        "example": "an example sentence tied to today's news",
        "origin": "...",
        "related_story_id": "<candidate id the word relates to>",
    },
}


def enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def models() -> list[str]:
    override = os.environ.get("DIGEST_MODELS", "")
    return [m.strip() for m in override.split(",") if m.strip()] or DEFAULT_MODELS


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
        f"Respond with JSON exactly in this shape:\n{json.dumps(RESPONSE_SHAPE, indent=1)}\n\n"
        f"Candidates:\n{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )


def extract_json(text: str) -> dict | None:
    """Pull the JSON object out of a reply that may include <think> blocks or fences."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list) or not isinstance(data.get("word"), dict):
        return None
    return data


def _complete(model: str, prompt: str) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
        }
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/rachmurali02/news-aggregator",
            "X-Title": "news-aggregator digest",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.load(resp)
    if "error" in data:
        raise RuntimeError(data["error"].get("message", data["error"]))
    return data["choices"][0]["message"].get("content") or ""


def _ask(prompt: str) -> tuple[str, dict] | None:
    for model in models():
        try:
            data = extract_json(_complete(model, prompt))
        except urllib.error.HTTPError as exc:
            log.warning("OpenRouter %s failed (%s): %s", model, exc.code, exc.read()[:300])
            continue
        except Exception as exc:
            log.warning("OpenRouter %s failed: %s", model, exc)
            continue
        if data:
            log.info("Curated with %s", model)
            return model, data
        log.warning("OpenRouter %s returned no usable JSON", model)
    return None


def curate(candidates: dict[str, list[Story]], sections_cfg: dict, profile: str, per_section: int):
    """Return (selected_by_section, intro, word) or None if curation fails."""
    result = _ask(_build_prompt(candidates, sections_cfg, profile, per_section))
    if not result:
        return None
    _, data = result

    by_id = {s.id: s for stories in candidates.values() for s in stories}
    selected: dict[str, list[Story]] = {key: [] for key in sections_cfg}
    for section in data["sections"]:
        if not isinstance(section, dict) or section.get("key") not in selected:
            continue
        for item in (section.get("stories") or [])[:per_section]:
            story = by_id.get(str(item.get("id", ""))) if isinstance(item, dict) else None
            if story and story not in selected[section["key"]]:
                story.takeaway = str(item.get("takeaway", "")).strip()
                selected[section["key"]].append(story)

    w = data["word"]
    if not all(w.get(k) for k in ("word", "definition")):
        return None
    related = by_id.get(str(w.get("related_story_id", "")))
    word = WordOfTheDay(
        word=str(w["word"]),
        pronunciation=str(w.get("pronunciation", "")),
        part_of_speech=str(w.get("part_of_speech", "")),
        definition=str(w["definition"]),
        example=str(w.get("example", "")),
        origin=str(w.get("origin", "")),
        related_url=related.url if related else "",
        related_title=related.title if related else "",
    )
    return selected, str(data.get("intro", "")).strip(), word
