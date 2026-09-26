# Inky

Tell it once. Inky learns a browser task, compiles it into a typed program, and runs it on its own.

- **Plans and repairs** with GLM-5.3 (open weights) via OpenRouter.
- **Decides each click** with [Laya](https://github.com/NandhaKishorM/laya), a small local typed-decision model. No LLM in the browser loop.
- **Scrapes at scale** with Apify actors, **runs on a schedule** as an n8n workflow, **asks you** on Telegram before anything risky.

Demo task: where can a Dutch buyer earn the most renting out a flat, where prices are rising and buying is easy?

## Setup

```bash
cp .env.example .env   # fill in your keys
uv sync
```
