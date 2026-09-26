# Inky

Tell it once. Inky learns a browser task, compiles it into a typed program, and runs it on its own.

- **Plans, derives rules and repairs** with GLM-5.3 (open weights) via OpenRouter.
- **Scrapes at scale** with Apify Store actors, **runs every 15 minutes** as an n8n workflow that Inky writes itself through the n8n API.
- **Asks you** on Telegram. An approved match becomes a Gmail draft to the agent. Nothing is ever sent for you.
- **Fixes itself**: when a step breaks, n8n's error workflow asks GLM-5.3 to rewrite that one step, saves it and runs again. At most once an hour.

Demo task: where can a Dutch buyer earn the most renting out a flat, where prices are rising and buying is easy? (Porto, Bari, Łódź)

## Build

```bash
cp .env.example .env        # fill in your keys, never paste them anywhere else
uv sync
uv run python build.py      # check -> test scrape (~$0.30) -> full scrape (~$55) -> rules -> n8n
```

Resume after a failed step with `uv run python build.py --from <step>`. Try it without keys or spend: `uv run python build.py --offline`.

| Step | Script | What it does |
|---|---|---|
| check | `check.py` | One free call per key. Never prints a key. |
| test-scrape, scrape | `research.py` | 8 Apify jobs (sale and rent × 3 cities), hard USD cap per job. |
| derive | `derive.py` | Rent and price per m² per neighbourhood, Eurostat price trend, ECB rate; GLM-5.3 proposes rules, the data tests them, three rounds. |
| n8n | `workflow.py` | Creates credentials, the main workflow and the repair workflow, and activates it. |

`inky.js` is the compiled program: the same file normalizes and scores listings locally and inside the n8n Code node. `test_pipeline.py` runs the whole chain on fixtures, including the n8n Code nodes.

## Before the first build

1. Keys in `.env`: OpenRouter, Apify, n8n (base URL + API key), Telegram bot token. Send `/start` to your bot.
2. Apify: set a monthly usage limit of $100.
3. n8n: install the Apify community node (`@apify/n8n-nodes-apify`), add a Gmail OAuth2 credential and put its id in `N8N_GMAIL_CREDENTIAL_ID`.

## What is open

Inky's code, GLM-5.3 (MIT, open weights), Crawlee (Apache-2.0). n8n is fair-code (source-available, self-hostable). The Apify platform and Telegram are hosted services.
