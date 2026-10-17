# news-aggregator

A personal morning newsletter. Every day it collects opinion columns and analysis from
**free-to-read** publications, picks the ones that match your interests, and emails you a
styled digest with a word of the day. Every headline links to the original article.

**Sources (no paywalls):** The Guardian, The Independent, The Conversation, Al Jazeera, NPR,
ProPublica, Ars Technica, Quanta Magazine, Rest of World and Calculated Risk. Links to known
paywalled sites (NYT, WSJ, FT, BBC in the US, Vox and others) are dropped through
`blocked_domains` in `config.yaml`, even when a free feed links to them.

**Default sections:** 🌍 Global Affairs · 🔬 Science & Technology · 🏡 Real Estate

![Digest preview](docs/preview.png)

## What's in each email

- **⏱ The 5-minute briefing.** Five one-line summaries at the top, each linking to its article.
- **📈 Developing stories.** Stories that continue coverage from earlier days, with a "Day N"
  badge, a line on what's new, and a timeline linking the earlier pieces.
- **Sections.** Two picks each (`stories_per_section`) for Global Affairs, Science &
  Technology and Real Estate, each with a one-line "The gist".
- **✦ Word of the day.** Taken from the day's articles and chosen to fit the day's main theme,
  with two more words from the same articles. Words don't repeat.
- **🎯 Your edition.** Every story has 👍 *More like this* / 👎 *Less like this* links. Each one
  opens a pre-filled email to yourself. Send it, and the next morning's run reads it over IMAP
  and adjusts how much weight each section, publication and topic gets. The box shows how
  your edition is currently tuned.

## How it works

```
feedback emails (IMAP) ──► learned preferences ─┐
RSS feeds ──► fetch ──► skip already-sent ──► score (keywords, freshness, opinion boost,
                                              your preferences, developing-story boost)
          ──► developing stories + sections ──► (optional) LLM: briefing, gists, updates, words
          ──► HTML email ──► Gmail SMTP ──► remember what was sent (state.enc)
```

- **Memory.** The workflow keeps `state.enc` on the `digest-state` branch. It holds stories
  sent in the last 21 days, learned preferences, processed feedback and used words. It is
  encrypted with the same key as the credentials, because reading habits are personal and
  the repo is public.
- **Developing stories.** Today's headlines are matched against earlier ones by shared
  distinctive words. A match joins that story's thread.
- **AI curation (optional, free).** With `OPENROUTER_API_KEY`, a free OpenRouter model
  (`microsoft/mai-ds-r1:free` first, then other free models) writes the briefing, gists,
  developing-story updates and the word picks. Without it, the email uses keyword ranking.
  The briefing then uses article summaries, and the word comes from a built-in list,
  preferring words that appear in today's articles.
- **Personalisation.** Besides feedback, you can edit `config.yaml` directly: section weights,
  keywords, the free-text `reader_profile`, `reader_name` and sources.

## Credentials

SMTP login, recipient and API keys are stored in **`credentials.enc`**, encrypted with
Fernet (AES + HMAC). The repo only holds the encrypted file. The key lives in one GitHub
secret, `DIGEST_SECRET_KEY`, and without it the file can't be read.

```bash
export DIGEST_SECRET_KEY=...                       # the key (never commit it)
python -m digest.credentials show                  # list stored names
python -m digest.credentials set OPENROUTER_API_KEY=sk-or-...   # add or update a value
python -m digest.credentials genkey                # make a new key (then re-set every value)
```

Any value can also be set as a plain GitHub secret or env var of the same name, which
overrides the encrypted one.

## Setup

1. Add the repository secret **`DIGEST_SECRET_KEY`** under *Settings → Secrets and variables
   → Actions*.
2. The OpenRouter key is already in `credentials.enc`. To replace it, run
   `python -m digest.credentials set OPENROUTER_API_KEY=...` and commit the file.
3. Test it: go to *Actions → Daily digest → Run workflow*. Tick *dry run* to only build the
   email, which you can download from the run's artifacts. Leave it unticked to send it.
4. After that it runs every day at **11:07 UTC** (about 7am New York time). To change the
   time, edit the `cron` line in the workflow. GitHub cron uses UTC.

To use a provider other than Gmail, store `SMTP_HOST` and `SMTP_PORT` as well. Port 465
uses SSL; any other port uses STARTTLS.

## Run locally

```bash
pip install -r requirements.txt
export DIGEST_SECRET_KEY=...
python -m digest --dry-run          # writes out/digest.html; open it in a browser
python -m digest                    # build and send
pip install pytest && python -m pytest
```

## Customising

- **Add a section.** Add a block under `sections:` (with `label`, `emoji`, `weight`,
  `keywords`). Optionally pin feeds to it with `section: <key>`.
- **Favour a topic.** Raise its `weight`, for example `1.5`.
- **More or fewer stories.** Change `digest.stories_per_section` and `digest.developing_stories`.
- **Add a publication.** Append an RSS URL under `sources:`. Mark columns with `opinion: true`.
- **Models.** Set `DIGEST_MODELS` to a comma-separated list of OpenRouter model ids to try
  in order. Free (`:free`) models change often, so check <https://openrouter.ai/models?q=free>.
