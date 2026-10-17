# news-aggregator

A personal morning newsletter. Every day it collects opinion columns and analysis from
**free-to-read** publications, picks the ones that match your interests, and emails you a
styled digest with a word of the day. Every headline links to the original article.

**Sources (no paywalls):** The Guardian, The Independent, The Conversation, Al Jazeera, Vox,
BBC News, NPR, Ars Technica, Quanta Magazine, CNBC and HousingWire.

**Default sections:** 🌍 Global Affairs · 🔬 Science & Technology · 🏡 Real Estate

![Digest preview](docs/preview.png)

## How it works

```
RSS feeds ──► fetch ──► dedupe + keyword scoring ──► (optional) LLM picks & annotates ──► HTML email ──► Gmail SMTP
                         per-section weights,              using your reader profile
                         opinion boost, freshness
```

- **Personalisation.** Edit `config.yaml`: section weights, keywords, the free-text
  `reader_profile`, and the sources list. Stories from mixed feeds such as *Opinion* are
  put into a section by keyword. Stories that fit no section are dropped.
- **AI curation (optional, free).** If `OPENROUTER_API_KEY` is set, a free OpenRouter model
  picks the best pieces for your profile and writes a one-line "The gist" takeaway for each.
  It also picks a word of the day that appears in one of today's stories, with a link to that
  story. Free models are tried in order (`microsoft/mai-ds-r1:free` first). If none
  answers, or there's no key, the digest uses keyword ranking and a built-in rotating word list.
- **Delivery.** A GitHub Actions workflow (`.github/workflows/daily-digest.yml`) runs
  every morning and sends the email over SMTP.

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
2. *(Optional)* Get a free key at <https://openrouter.ai/keys> and add it as the secret
   `OPENROUTER_API_KEY`, or store it in `credentials.enc` as shown above.
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
- **More or fewer stories.** Change `digest.stories_per_section`.
- **Add a publication.** Append an RSS URL under `sources:`. Mark columns with `opinion: true`.
- **Models.** Set `DIGEST_MODELS` to a comma-separated list of OpenRouter model ids to try
  in order. Free (`:free`) models change often, so check <https://openrouter.ai/models?q=free>.
