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


def test_build_and_render_without_llm():
    cfg = config()
    digest = app.build_digest(cfg, load_stories(), now=NOW, use_llm=False)
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


def test_extract_json_handles_reasoning_and_fences():
    from digest import curate
    reply = '<think>let me {think}</think>\n```json\n{"intro": "hi", "sections": [], "word": {"word": "x"}}\n```'
    assert curate.extract_json(reply)["intro"] == "hi"
    assert curate.extract_json("no json here") is None
    assert curate.extract_json('{"intro": "missing sections"}') is None


def test_llm_curation_falls_through_models(monkeypatch):
    import json
    from digest import curate

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
    tried = []

    def fake_complete(model, prompt):
        tried.append(model)
        if len(tried) == 1:
            raise RuntimeError("model unavailable")
        return "<think>pondering</think>" + json.dumps(payload)

    monkeypatch.setenv("DIGEST_MODELS", "first:free,second:free")
    monkeypatch.setattr(curate, "_complete", fake_complete)
    digest = app.build_digest(config(), stories, now=NOW, use_llm=True)

    assert tried == ["first:free", "second:free"]
    assert digest.curated_by_ai
    assert digest.intro == "Trade wars and housing math."
    by_key = {s["key"]: s["stories"] for s in digest.sections}
    assert [s.takeaway for s in by_key["global_affairs"]] == ["Tariffs aren't working."]
    assert len(by_key["real_estate"]) == 1
    assert by_key["science_tech"]  # model left it empty -> keyword picks kept
    assert digest.word.related_url == china.url
    assert "See it in today" in render.render_html(digest)


def test_llm_total_failure_falls_back_to_keywords(monkeypatch):
    from digest import curate
    monkeypatch.setattr(curate, "_complete", lambda m, p: "sorry")
    digest = app.build_digest(config(), load_stories(), now=NOW, use_llm=True)
    assert not digest.curated_by_ai and digest.story_count == 4


def test_credentials_roundtrip(tmp_path, monkeypatch):
    import os
    from cryptography.fernet import Fernet
    from digest import credentials

    key = Fernet.generate_key().decode()
    path = tmp_path / "creds.enc"
    credentials.write({"SMTP_USER": "a@b.com", "SMTP_PASSWORD": "pw"}, path, key)
    assert b"a@b.com" not in path.read_bytes()

    monkeypatch.setenv("DIGEST_SECRET_KEY", key)
    monkeypatch.setenv("SMTP_USER", "override@b.com")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert credentials.load_into_env(path) == ["SMTP_PASSWORD"]
    assert os.environ["SMTP_PASSWORD"] == "pw"
    assert os.environ["SMTP_USER"] == "override@b.com"


def _history(*entries):
    return [{"id": f"h{i}", "date": d, "title": t, "url": f"https://old.example/{i}", "source": "Old Paper",
             "section": sec, "thread_id": tid or f"h{i}"} for i, (d, t, sec, tid) in enumerate(entries)]


def test_developing_story_is_threaded_and_pulled_out_of_sections():
    from digest import state
    memory = state.empty()
    memory["history"] = _history(
        ("2026-10-15", "China tariffs strategy faces backlash in Europe", "global_affairs", None),
        ("2026-10-16", "Europe weighs response to China tariffs strategy", "global_affairs", "h0"),
        ("2026-10-16", "Unrelated piece on gardening", "science_tech", None),
    )
    china_feed = fetch.parse_feed(b"""<rss><channel><item><title>China tariffs strategy: what Europe does next</title>
        <link>https://example.com/china-next</link><description>Tariffs and trade diplomacy.</description>
        <pubDate>Sat, 17 Oct 2026 09:00:00 GMT</pubDate></item></channel></rss>""",
                                  {"name": "The Guardian", "section": "global_affairs", "opinion": True})
    digest = app.build_digest(config(), load_stories() + china_feed, now=NOW, use_llm=False, memory=memory)

    assert [s.url for s in digest.developing] == ["https://example.com/china-next"]
    dev = digest.developing[0]
    assert dev.thread_id == "h0"
    assert [t["date"] for t in dev.thread] == ["2026-10-15", "2026-10-16"]
    assert dev not in [s for sec in digest.sections for s in sec["stories"]]
    html = render.render_html(digest)
    assert "Developing stories" in html and "Day 3" in html and "Oct 15" in html


def test_already_sent_urls_are_skipped():
    from digest import state
    memory = state.empty()
    memory["history"] = [{"id": "x", "date": "2026-10-16", "title": "AI Will Not Save Us From Ourselves",
                          "url": "https://example.com/ai-save", "source": "S", "section": "science_tech"}]
    digest = app.build_digest(config(), load_stories(), now=NOW, use_llm=False, memory=memory)
    assert "https://example.com/ai-save" not in [s.url for s in digest.all_stories]


def test_feedback_shifts_preferences_and_ranking():
    from digest import prefs, state
    memory = state.empty()
    memory["history"] = _history(("2026-10-16", "Mortgage rates and housing supply", "real_estate", None))
    memory["history"][0]["source"] = "Property Desk"
    used = prefs.apply_feedback(memory, [("<m1>", "more", "h0"), ("<m1>", "more", "h0"), ("<m2>", "less", "nope")], NOW)
    assert used == 1  # duplicate message and unknown story ignored
    p = memory["prefs"]
    assert p["sections"]["real_estate"] > 1 and p["sources"]["Property Desk"] > 1 and p["terms"]["mortgage"] == 1
    assert "More Real Estate" in prefs.describe(p, config()["sections"])

    stories = load_stories()
    baseline = {s.url: s.score for s in rank.score_stories(rank.dedupe(load_stories()), config()["sections"], now=NOW)}
    scored = rank.score_stories(rank.dedupe(stories), config()["sections"], now=NOW)
    prefs.apply(scored, p)
    mortgage = next(s for s in scored if "Mortgage" in s.title)
    assert mortgage.score > baseline[mortgage.url]


def test_feedback_links_in_email():
    digest = app.build_digest(config(), load_stories(), now=NOW, use_llm=False)
    digest.feedback_to = "me@example.com"
    html = render.render_html(digest)
    assert "mailto:me@example.com?subject=%5Bdigest-feedback%5D%20more%20" in html
    assert "Less like this" in html


def test_word_comes_from_todays_articles_and_skips_used():
    from digest.models import Story
    s = Story(title="Housing reform is no panacea", url="https://e.com/p", source="Vox", summary="")
    w = words.from_stories([s])
    assert w.word == "panacea" and w.related_url == "https://e.com/p"
    assert words.from_stories([s], used={"panacea"}) is None
    assert words.word_for(NOW.date(), used={words.word_for(NOW.date()).word}).word != words.word_for(NOW.date()).word


def test_briefing_fallback_has_five_or_fewer_items():
    digest = app.build_digest(config(), load_stories(), now=NOW, use_llm=False)
    assert 1 <= len(digest.briefing) <= 5
    assert "5-minute briefing" in render.render_html(digest)


def test_state_roundtrip_encrypted(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from digest import state
    monkeypatch.setenv("DIGEST_SECRET_KEY", Fernet.generate_key().decode())
    path = tmp_path / "state.enc"
    memory = state.empty()
    memory["history"] = _history(("2026-10-16", "Recent", "x", None), ("2026-01-01", "Ancient", "x", None))
    memory["used_words"] = ["panacea"]
    assert state.save(memory, NOW, path)
    assert b"Recent" not in path.read_bytes()
    loaded = state.load(path)
    assert [h["title"] for h in loaded["history"]] == ["Recent"]  # old entries pruned
    assert loaded["used_words"] == ["panacea"]


def test_llm_briefing_developing_and_word_bank(monkeypatch):
    import json
    from digest import curate, state
    memory = state.empty()
    memory["history"] = _history(("2026-10-16", "West's China strategy questioned", "global_affairs", None))
    stories = load_stories()
    china = next(s for s in stories if "China" in s.title)
    ai = next(s for s in stories if s.title.startswith("AI"))
    payload = {
        "intro": "Hi.",
        "briefing": [{"story_id": china.id, "text": "China line."}, {"story_id": ai.id, "text": "AI line."},
                     {"story_id": "bogus", "text": "dropped"}, {"story_id": ai.id, "text": "Third."}],
        "developing": [{"story_id": china.id, "update": "Europe now joins in."}],
        "sections": [{"key": "science_tech", "stories": [{"id": ai.id, "takeaway": "Hype."}]}],
        "word": {"word": "hype", "definition": "Exaggerated publicity.", "theme": "AI week",
                 "related_story_id": ai.id},
        "word_bank": [{"word": "zoning", "definition": "Land-use rules."}, {"word": "hype", "definition": "dup"}],
    }
    monkeypatch.setattr(curate, "_complete", lambda m, p: json.dumps(payload))
    digest = app.build_digest(config(), stories, now=NOW, use_llm=True, memory=memory)

    assert digest.developing == [china] and china.update == "Europe now joins in."
    assert [b["text"] for b in digest.briefing] == ["China line.", "AI line.", "Third."]
    assert digest.word.word == "hype" and digest.word.theme == "AI week"
    assert [w.word for w in digest.word_bank] == ["zoning"]


def test_feedback_emails_read_and_archived(monkeypatch):
    from digest import prefs

    mails = {
        b"1": b"Subject: [digest-feedback] more abcd1234\r\nFrom: Me <me@example.com>\r\nMessage-ID: <a@x>\r\n\r\n",
        b"2": b"Subject: [digest-feedback] less abcd1234\r\nFrom: stranger@evil.com\r\nMessage-ID: <b@x>\r\n\r\n",
    }
    deleted = []

    class FakeIMAP:
        def __init__(self, host, timeout=None): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, u, p): pass
        def select(self, box): pass
        def search(self, charset, query): return "OK", [b"1 2"]
        def fetch(self, num, what): return "OK", [(b"hdr", mails[num])]
        def store(self, num, op, flag): deleted.append(num)
        def expunge(self): pass

    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setattr(prefs.imaplib, "IMAP4_SSL", FakeIMAP)
    events = prefs.fetch_feedback_emails({"me@example.com"})
    assert events == [("<a@x>", "more", "abcd1234")]  # stranger ignored
    assert deleted == [b"1", b"2"]


def test_paywalled_domains_are_dropped():
    from digest.models import Story
    assert rank.is_blocked("https://www.vox.com/podcasts/506325/x", ["vox.com"])
    assert not rank.is_blocked("https://notvox.com/a", ["vox.com"])
    cfg = config()
    paywalled = Story(title="AI chips and the semiconductor war", url="https://www.vox.com/tech/ai-chips",
                      source="Some Aggregator", feed_section="science_tech")
    digest = app.build_digest(cfg, load_stories() + [paywalled], now=NOW, use_llm=False)
    assert all("vox.com" not in s.url for s in digest.all_stories)
    sources = {s["name"] for s in cfg["sources"]}
    assert not sources & {"Vox", "BBC News", "CNBC", "HousingWire"}
    assert not any(rank.is_blocked(s["url"], cfg["blocked_domains"]) for s in cfg["sources"])
