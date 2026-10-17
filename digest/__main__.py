"""Build and send the daily digest.

    python -m digest              # build and email
    python -m digest --dry-run    # build only, write out/digest.html
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import credentials, curate, fetch, health, prefs, rank, render, send, state, threads, words
from .models import Digest, Story

log = logging.getLogger("digest")

DEFAULT_INTRO = "Today's sharpest columns and analysis, picked for you."


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fallback_briefing(stories: list[Story], n: int = 5) -> list[dict]:
    top = sorted(stories, key=lambda s: s.score, reverse=True)[:n]
    return [{"text": s.takeaway or s.update or s.summary or s.title, "story": s} for s in top]


def build_digest(
    config: dict,
    stories: list[Story],
    now: datetime | None = None,
    use_llm: bool | None = None,
    memory: dict | None = None,
) -> Digest:
    opts = config["digest"]
    sections_cfg = config["sections"]
    per_section = int(opts.get("stories_per_section", 2))
    max_developing = int(opts.get("developing_stories", 3))
    now = now or datetime.now(ZoneInfo(opts.get("timezone", "UTC")))
    memory = memory if memory is not None else state.empty()
    history = memory["history"]

    already_sent = threads.sent_urls(history)
    blocked = config.get("blocked_domains", [])
    fresh = [s for s in stories if s.url not in already_sent and not rank.is_blocked(s.url, blocked)]
    scored = rank.score_stories(
        rank.dedupe(fresh),
        sections_cfg,
        opinion_boost=float(opts.get("opinion_boost", 1.5)),
        lookback_hours=int(opts.get("lookback_hours", 36)),
        now=now,
    )
    prefs.apply(scored, memory["prefs"])
    threads.attach(scored, history, now.date().isoformat())
    for s in scored:
        if s.thread:
            s.score *= float(opts.get("developing_boost", 1.3))

    # Best continuation per thread goes to "Developing stories"; the rest compete in sections.
    developing, seen_threads = [], set()
    for s in sorted((s for s in scored if s.thread), key=lambda s: s.score, reverse=True):
        if s.thread_id not in seen_threads and len(developing) < max_developing:
            developing.append(s)
            seen_threads.add(s.thread_id)
    pool = [s for s in scored if s not in developing]
    selected = rank.top_by_section(pool, sections_cfg, per_section)

    used_words = memory["used_words"]
    tuning = prefs.describe(memory["prefs"], sections_cfg)
    picked_so_far = developing + [s for v in selected.values() for s in v]
    word = words.from_stories(picked_so_far, set(used_words)) or words.word_for(now.date(), set(used_words))
    intro, briefing, word_bank, curated = DEFAULT_INTRO, [], [], False

    if use_llm is None:
        use_llm = curate.enabled()
    if use_llm:
        # Give the model a wider pool than we'll show so it has real choices.
        candidates = rank.top_by_section(pool, sections_cfg, per_section * 4)
        result = curate.curate(
            candidates, developing, sections_cfg, config.get("reader_profile", ""), per_section, used_words, tuning
        )
        if result:
            # Keep keyword picks for any section the model left empty.
            selected = {k: result["sections"].get(k) or selected[k] for k in sections_cfg}
            intro = result["intro"] or DEFAULT_INTRO
            briefing = result["briefing"]
            word = result["word"] or word
            word_bank = result["word_bank"]
            curated = True

    shown = developing + [s for v in selected.values() for s in v]
    if len(briefing) < 3:
        briefing = _fallback_briefing(shown)

    return Digest(
        title=opts.get("title", "Daily Digest"),
        date=now,
        intro=intro,
        sections=[
            {"key": key, "label": cfg["label"], "emoji": cfg.get("emoji", ""), "stories": selected[key]}
            for key, cfg in sections_cfg.items()
        ],
        briefing=briefing,
        developing=developing,
        word=word,
        word_bank=word_bank,
        tuning=tuning,
        reader_name=opts.get("reader_name", ""),
        curated_by_ai=curated,
    )


def settings_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    return f"{server}/{repo}/edit/main/config.yaml" if repo else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Write HTML to out/ instead of emailing")
    parser.add_argument("--out", default="out")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    loaded = credentials.load_into_env()
    if loaded:
        log.info("Loaded encrypted credentials: %s", ", ".join(loaded))
    config = load_config(args.config)
    tz = ZoneInfo(config["digest"].get("timezone", "UTC"))
    now = datetime.now(tz)
    memory = state.load()

    to = os.environ.get("DIGEST_TO") or config["digest"].get("recipient")
    if not args.dry_run:  # reading feedback archives it, so only do it when state is saved
        reader = {a.lower() for a in (to, os.environ.get("SMTP_USER")) if a}
        applied = prefs.apply_feedback(memory, prefs.fetch_feedback_emails(reader), now)
        if applied:
            log.info("Applied %d pieces of feedback", applied)

    results = fetch.fetch_all(config["sources"])
    stories = [s for r in results for s in r.stories]
    log.info("Fetched %d stories total", len(stories))
    statuses, flagged = health.update(
        memory["feed_health"],
        results,
        now,
        lookback_hours=int(config["digest"].get("lookback_hours", 36)),
        flag_after_days=int(config["digest"].get("flag_empty_feeds_after_days", 3)),
    )
    health.log_report(statuses, flagged)
    health.write_summary(statuses, flagged)
    if not stories:
        log.error("No stories fetched; check network access and feed URLs")
        if not args.dry_run:
            state.save(memory, now)  # keep the empty-feed streaks
        return 1

    digest = build_digest(config, stories, now=now, memory=memory)
    if digest.story_count == 0:
        log.error("No stories matched your sections")
        if not args.dry_run:
            state.save(memory, now)
        return 1
    # Feedback emails go to the mailbox the next run reads over IMAP.
    digest.feedback_to = os.environ.get("SMTP_USER", "")
    digest.flagged_feeds = [{"name": f.name, "url": f.url, "days": f.empty_streak} for f in flagged]

    html = render.render_html(digest, settings_url=settings_url())
    text = render.render_text(digest)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "digest.html").write_text(html, encoding="utf-8")
    (out / "digest.txt").write_text(text, encoding="utf-8")
    log.info(
        "Wrote %s (%d stories, %d developing, AI-curated=%s)",
        out / "digest.html", digest.story_count, len(digest.developing), digest.curated_by_ai,
    )

    if args.dry_run:
        return 0

    if not to:
        log.error("No recipient: set DIGEST_TO or digest.recipient in config.yaml")
        return 1
    subject = f"{digest.title} · {digest.date.strftime('%a %b %-d')} · {digest.word.word if digest.word else ''}".rstrip(" ·")
    send.send_email(subject=subject, html=html, text=text, to=to)
    log.info("Sent digest to %s", to)

    # Remember what was sent only once it has actually gone out.
    threads.record(memory["history"], digest.all_stories, now)
    if digest.word:
        memory["used_words"].append(digest.word.word.lower())
    if state.save(memory, now):
        log.info("Saved state")
    return 0


if __name__ == "__main__":
    sys.exit(main())
