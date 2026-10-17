"""Feed health: log what each feed returned and flag feeds that stay empty.

A feed counts as empty on a day when it fails to load or has no stories from
within the lookback window (a dead feed often still serves old items). After
`flag_after_days` empty days in a row it is flagged in the run log, the GitHub
Actions summary and the email footer, so it can be replaced in config.yaml.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from .fetch import FeedResult

log = logging.getLogger(__name__)


@dataclass
class FeedStatus:
    name: str
    url: str
    total: int
    fresh: int
    error: str
    empty_streak: int
    last_ok: str

    @property
    def empty(self) -> bool:
        return self.fresh == 0


def update(
    health: dict, results: list[FeedResult], now: datetime, lookback_hours: int, flag_after_days: int = 3
) -> tuple[list[FeedStatus], list[FeedStatus]]:
    """Record today's results in `health` (keyed by URL); return (all, flagged)."""
    today = now.date().isoformat()
    cutoff = now - timedelta(hours=lookback_hours)
    statuses = []
    for r in results:
        url = r.source["url"]
        fresh = sum(1 for s in r.stories if not s.published or s.published >= cutoff)
        entry = health.setdefault(url, {"empty_streak": 0, "last_empty": "", "last_ok": ""})
        if fresh:
            entry["empty_streak"], entry["last_ok"] = 0, today
        elif entry["last_empty"] != today:  # count each day once, even with re-runs
            entry["empty_streak"] += 1
            entry["last_empty"] = today
        entry.update(name=r.source["name"], last_total=len(r.stories), last_fresh=fresh, last_error=r.error)
        statuses.append(
            FeedStatus(r.source["name"], url, len(r.stories), fresh, r.error, entry["empty_streak"], entry["last_ok"])
        )
    # Forget feeds that were removed from config.yaml.
    for url in set(health) - {r.source["url"] for r in results}:
        del health[url]
    flagged = [s for s in statuses if s.empty_streak >= flag_after_days]
    return statuses, flagged


def _problem(s: FeedStatus) -> str:
    if s.error:
        return f"failed: {s.error}"
    if s.total:
        return f"{s.total} items, none recent"
    return "no items"


def log_report(statuses: list[FeedStatus], flagged: list[FeedStatus]) -> None:
    log.info("Feed health (%d feeds):", len(statuses))
    for s in sorted(statuses, key=lambda s: (s.fresh, s.name)):
        mark = "OK  " if not s.empty else "EMPTY"
        detail = "" if not s.empty else f" ({_problem(s)}; empty {s.empty_streak} day(s) running)"
        log.info("  %s %3d fresh / %3d total  %s  %s%s", mark, s.fresh, s.total, s.name, s.url, detail)
    for s in flagged:
        # GitHub Actions turns this into a warning annotation on the run.
        print(f"::warning title=Feed empty {s.empty_streak} days::{s.name} ({s.url}) {_problem(s)}. Replace it in config.yaml.")


def write_summary(statuses: list[FeedStatus], flagged: list[FeedStatus]) -> None:
    """Add a feed table to the GitHub Actions run summary page."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = ["## Feed health", ""]
    if flagged:
        lines += [f"⚠️ **{len(flagged)} feed(s) empty for several days. Consider replacing them in `config.yaml`.**", ""]
    lines += ["| Status | Feed | Fresh | Total | Empty streak | Last OK | Note |", "|---|---|---:|---:|---:|---|---|"]
    for s in sorted(statuses, key=lambda s: (-s.empty_streak, s.fresh, s.name)):
        status = "🚩" if s in flagged else ("⚠️" if s.empty else "✅")
        note = _problem(s) if s.empty else ""
        lines.append(
            f"| {status} | [{s.name}]({s.url}) | {s.fresh} | {s.total} | {s.empty_streak} | {s.last_ok or 'never'} | {note} |"
        )
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
