from datetime import datetime, timezone
from pathlib import Path

import yaml

from digest import __main__ as app
from digest import fetch, rank, render, words

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def load_stories():
    opinion = fetch.parse_feed((FIXTURES / "opinion.xml").read_bytes(),
                               {"name": "The Daily Opinion", "section": "auto", "opinion": True})
    estate = fetch.parse_feed((FIXTURES / "realestate.xml").read_bytes(),
                              {"name": "Property Desk", "section": "real_estate"})
    return opinion + estate


def config():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def test_parse_feed_strips_html():
    stories = load_stories()
    china = next(s for s in stories if "China" in s.title)
    assert "<p>" not in china.summary
    assert china.author == "Jane Columnist"
    assert china.opinion


def test_auto_feed_is_classified_and_off_topic_dropped():
    cfg = config()
    scored = rank.score_stories(rank.dedupe(load_stories()), cfg["sections"], now=NOW)
    sections = {s.title: s.section for s in scored}
    assert sections["The West's China Strategy Is Running Out of Road"] == "global_affairs"
    assert sections["AI Will Not Save Us From Ourselves"] == "science_tech"
    assert sections["Build More Homes. It Really Is That Simple."] == "real_estate"
    assert "My Favourite Recipes for Autumn" not in sections  # matches no section
    assert "An Old Piece About Ukraine" not in sections  # outside lookback window


def test_dedupe_by_title():
    deduped = rank.dedupe(load_stories())
    assert sum(1 for s in deduped if s.title.startswith("Build More Homes")) == 1


def test_build_and_render_without_claude():
    cfg = config()
    digest = app.build_digest(cfg, load_stories(), now=NOW, use_claude=False)
    assert digest.story_count == 4
    assert digest.word == words.word_for(NOW.date())

    html = render.render_html(digest, settings_url="https://github.com/x/y/edit/main/config.yaml")
    assert "https://example.com/china-strategy" in html
    assert "Read on The Daily Opinion" in html
    assert digest.word.word in html
    assert 'href="#real_estate"' in html

    text = render.render_text(digest)
    assert "WORD OF THE DAY" in text and "https://example.com/build-homes" in text


def test_word_rotation_covers_list():
    from datetime import date, timedelta
    start = date(2026, 1, 1)
    seen = {words.word_for(start + timedelta(days=i)).word for i in range(len(words.WORDS))}
    assert len(seen) == len(words.WORDS)


def test_claude_curation_with_fake_client(monkeypatch):
    import json
    import anthropic
    from types import SimpleNamespace

    stories = load_stories()
    china = next(s for s in stories if "China" in s.title)
    homes = next(s for s in stories if s.title.startswith("Build More Homes"))
    payload = {
        "intro": "Trade wars and housing math.",
        "sections": [
            {"key": "global_affairs", "stories": [{"id": china.id, "takeaway": "Tariffs aren't working."}]},
            {"key": "real_estate", "stories": [{"id": homes.id, "takeaway": "Supply is the fix."},
                                               {"id": "bogus", "takeaway": "ignored"}]},
            {"key": "not_a_section", "stories": []},
        ],
        "word": {"word": "intransigent", "pronunciation": "in-TRAN-suh-junt", "part_of_speech": "adjective",
                 "definition": "Unwilling to change.", "example": "Beijing stayed intransigent.",
                 "origin": "Spanish.", "related_story_id": china.id},
    }
    captured = {}

    class FakeStream:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get_final_message(self):
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=json.dumps(payload))])

    class FakeClient:
        def __init__(self, *a, **k):
            self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))
        def stream(self, **kwargs):
            captured.update(kwargs)
            return FakeStream()

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    digest = app.build_digest(config(), stories, now=NOW, use_claude=True)

    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert digest.curated_by_claude
    assert digest.intro == "Trade wars and housing math."
    by_key = {s["key"]: s["stories"] for s in digest.sections}
    assert [s.takeaway for s in by_key["global_affairs"]] == ["Tariffs aren't working."]
    assert len(by_key["real_estate"]) == 1
    assert by_key["science_tech"]  # Claude left it empty -> keyword picks kept
    assert digest.word.related_url == china.url
    assert "See it in today" in render.render_html(digest)
