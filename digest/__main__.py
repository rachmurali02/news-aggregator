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

from . import curate, fetch, rank, render, send, words
from .models import Digest

log = logging.getLogger("digest")

DEFAULT_INTRO = "Today's sharpest columns and analysis, picked for you."


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_digest(config: dict, stories, now: datetime | None = None, use_claude: bool | None = None) -> Digest:
    opts = config["digest"]
    sections_cfg = config["sections"]
    per_section = int(opts.get("stories_per_section", 4))
    now = now or datetime.now(ZoneInfo(opts.get("timezone", "UTC")))

    scored = rank.score_stories(
        rank.dedupe(stories),
        sections_cfg,
        opinion_boost=float(opts.get("opinion_boost", 1.5)),
        lookback_hours=int(opts.get("lookback_hours", 36)),
        now=now,
    )
    selected = rank.top_by_section(scored, sections_cfg, per_section)
    intro, word, curated = DEFAULT_INTRO, words.word_for(now.date()), False

    if use_claude is None:
        use_claude = curate.enabled()
    if use_claude:
        # Give Claude a wider pool than we'll show so it has real choices.
        candidates = rank.top_by_section(scored, sections_cfg, per_section * 3)
        result = curate.curate(candidates, sections_cfg, config.get("reader_profile", ""), per_section)
        if result:
            picked, intro, word = result
            # Keep keyword picks for any section Claude left empty.
            selected = {k: picked.get(k) or selected[k] for k in sections_cfg}
            curated = True

    return Digest(
        title=opts.get("title", "Daily Digest"),
        date=now,
        intro=intro,
        sections=[
            {"key": key, "label": cfg["label"], "emoji": cfg.get("emoji", ""), "stories": selected[key]}
            for key, cfg in sections_cfg.items()
        ],
        word=word,
        curated_by_claude=curated,
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

    config = load_config(args.config)
    stories = fetch.fetch_all(config["sources"])
    log.info("Fetched %d stories total", len(stories))
    if not stories:
        log.error("No stories fetched; check network access and feed URLs")
        return 1

    digest = build_digest(config, stories)
    if digest.story_count == 0:
        log.error("No stories matched your sections")
        return 1

    html = render.render_html(digest, settings_url=settings_url())
    text = render.render_text(digest)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "digest.html").write_text(html, encoding="utf-8")
    (out / "digest.txt").write_text(text, encoding="utf-8")
    log.info("Wrote %s (%d stories, Claude=%s)", out / "digest.html", digest.story_count, digest.curated_by_claude)

    if args.dry_run:
        return 0

    to = os.environ.get("DIGEST_TO") or config["digest"].get("recipient")
    if not to:
        log.error("No recipient: set DIGEST_TO or digest.recipient in config.yaml")
        return 1
    subject = f"{digest.title} · {digest.date.strftime('%a %b %-d')} · {digest.word.word if digest.word else ''}".rstrip(" ·")
    send.send_email(subject=subject, html=html, text=text, to=to)
    log.info("Sent digest to %s", to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
