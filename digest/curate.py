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
    "analysis at free-to-read newspapers. Choose pieces that best match the reader's interests "
    "and what their feedback says they enjoy, favour substantive arguments over routine "
    "updates, and keep a mix of publications. Takeaways are one or two plain sentences "
    "(under 40 words) telling the reader the column's argument or why the story matters: no "
    "hype, no repeating the headline. The 5-minute briefing is five crisp sentences, one per "
    "story, that together tell the reader what matters today. For developing stories, say in "
    "one sentence what is new compared with the earlier instalments. For words, pick "
    "somewhat advanced English words that actually appear in today's candidate titles or "
    "summaries; the word of the day should be the one that best captures the day's dominant "
    "theme. Never pick a word the reader has already had. Reply with a single JSON object "
    "and nothing else."
)

WORD_SHAPE = {
    "word": "...",
    "pronunciation": "simple respelling, e.g. hi-JEM-uh-nee",
    "part_of_speech": "...",
    "definition": "...",
    "example": "an example sentence tied to today's news",
    "origin": "...",
    "related_story_id": "<candidate id where the word appears>",
}

RESPONSE_SHAPE = {
    "intro": "One warm sentence previewing today's themes.",
    "briefing": [{"story_id": "<candidate or developing id>", "text": "<one sentence>"}],
    "developing": [{"story_id": "<developing id>", "update": "<what is new, one sentence>"}],
    "sections": [{"key": "<section key>", "stories": [{"id": "<candidate id>", "takeaway": "<1-2 sentences>"}]}],
    "word": {**WORD_SHAPE, "theme": "<one line: why this word captures today's news>"},
    "word_bank": [WORD_SHAPE],
}


def enabled() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def models() -> list[str]:
    override = os.environ.get("DIGEST_MODELS", "")
    return [m.strip() for m in override.split(",") if m.strip()] or DEFAULT_MODELS


def _story_json(s: Story) -> dict:
    return {"id": s.id, "source": s.source, "opinion": s.opinion, "title": s.title, "summary": s.summary}


def _build_prompt(
    candidates: dict[str, list[Story]],
    developing: list[Story],
    sections_cfg: dict,
    profile: str,
    per_section: int,
    used_words: list[str],
    tuning: list[str],
) -> str:
    payload = {key: [_story_json(s) for s in stories] for key, stories in candidates.items()}
    threads_json = [
        {**_story_json(s), "earlier": [f"{t['date']}: {t['title']}" for t in s.thread]} for s in developing
    ]
    labels = {k: v["label"] for k, v in sections_cfg.items()}
    return (
        f"Reader profile:\n{profile.strip()}\n\n"
        f"Learned from the reader's feedback: {'; '.join(tuning) or 'nothing yet'}\n\n"
        f"Words the reader has already had (do not reuse): {', '.join(used_words[-60:]) or 'none'}\n\n"
        f"Sections (key -> label): {json.dumps(labels)}\n\n"
        f"Pick up to {per_section} stories per section from the candidates, ordered best first. "
        "Write an update line for every developing story. The briefing covers the five most "
        "important stories across developing and chosen stories. Add two more words to word_bank. "
        "Use only the given ids and section keys.\n\n"
        f"Respond with JSON exactly in this shape:\n{json.dumps(RESPONSE_SHAPE, indent=1)}\n\n"
        f"Developing stories (continuing earlier coverage):\n{json.dumps(threads_json, ensure_ascii=False, indent=1)}\n\n"
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


def _word(w: dict, by_id: dict[str, Story]) -> WordOfTheDay | None:
    if not isinstance(w, dict) or not w.get("word") or not w.get("definition"):
        return None
    related = by_id.get(str(w.get("related_story_id", "")))
    return WordOfTheDay(
        word=str(w["word"]).strip(),
        pronunciation=str(w.get("pronunciation", "")),
        part_of_speech=str(w.get("part_of_speech", "")),
        definition=str(w["definition"]),
        example=str(w.get("example", "")),
        origin=str(w.get("origin", "")),
        related_url=related.url if related else "",
        related_title=related.title if related else "",
        theme=str(w.get("theme", "")),
    )


def curate(
    candidates: dict[str, list[Story]],
    developing: list[Story],
    sections_cfg: dict,
    profile: str,
    per_section: int,
    used_words: list[str] = (),
    tuning: list[str] = (),
) -> dict | None:
    """Return {sections, intro, briefing, word, word_bank} or None if curation fails.

    Takeaways and developing-story updates are written onto the Story objects.
    """
    prompt = _build_prompt(candidates, developing, sections_cfg, profile, per_section, list(used_words), list(tuning))
    result = _ask(prompt)
    if not result:
        return None
    _, data = result

    by_id = {s.id: s for stories in candidates.values() for s in stories}
    by_id.update({s.id: s for s in developing})
    selected: dict[str, list[Story]] = {key: [] for key in sections_cfg}
    for section in data["sections"]:
        if not isinstance(section, dict) or section.get("key") not in selected:
            continue
        for item in (section.get("stories") or [])[:per_section]:
            story = by_id.get(str(item.get("id", ""))) if isinstance(item, dict) else None
            if story and story not in developing and story not in selected[section["key"]]:
                story.takeaway = str(item.get("takeaway", "")).strip()
                selected[section["key"]].append(story)

    for item in data.get("developing") or []:
        story = by_id.get(str(item.get("story_id", ""))) if isinstance(item, dict) else None
        if story in developing:
            story.update = str(item.get("update", "")).strip()

    briefing = []
    for item in data.get("briefing") or []:
        story = by_id.get(str(item.get("story_id", ""))) if isinstance(item, dict) else None
        if story and item.get("text"):
            briefing.append({"text": str(item["text"]).strip(), "story": story})

    word = _word(data["word"], by_id)
    if not word or word.word.lower() in {w.lower() for w in used_words}:
        word = None
    bank = [w for w in (_word(x, by_id) for x in (data.get("word_bank") or [])[:3]) if w]
    return {
        "sections": selected,
        "intro": str(data.get("intro", "")).strip(),
        "briefing": briefing[:5],
        "word": word,
        "word_bank": [w for w in bank if not word or w.word.lower() != word.word.lower()][:2],
    }
