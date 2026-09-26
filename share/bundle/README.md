# Inky: Inky · Buy-to-let abroad

Inky reads 5 property sites every 15 minutes, scores every new home with fixed rules (no AI in the loop),
asks you on Telegram and, when you tap "Save as draft", writes a Gmail draft to the agent. It never sends anything.

| File | What it is |
|---|---|
| `plan.json` | What the person who shared this asked for: budget, cities, the kind of home. |
| `rules.json` | The 7 rules Inky derived from real listings for that plan. |
| `inky-main.json` | The n8n workflow: Apify -> score -> Telegram -> Gmail draft, a daily digest, "Send me the best now". |
| `inky-repair.json` | The repair workflow: when a step breaks, GLM-5.3 rewrites that step's input, at most once an hour. |
| `bundle.json` | Title, one-line description, author and date, for the marketplace. |

## Set it up with the API (2 minutes)

You need an n8n with the public API on, and in a `.env` file:
`N8N_BASE_URL`, `N8N_API_KEY`, `APIFY_TOKEN`, `TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`,
`TELEGRAM_CHAT_ID` (or send /start to your bot first), and optionally `N8N_GMAIL_CREDENTIAL_ID`
(an existing Gmail OAuth2 credential in your n8n; without it drafts stay paused).

```bash
python share/import.py --dry-run     # checks this bundle and your .env, changes nothing
python share/import.py               # creates the credentials and both workflows, not published
python share/import.py --activate    # the same, and publishes them: it starts running every 15 minutes
python share/import.py --no-credentials  # only needs N8N_BASE_URL and N8N_API_KEY: pick your own credentials in n8n
```

To check the import first, `python share/import.py --test` makes a throwaway copy: both workflows are created
inactive, named "... (import test)", with no credentials and Telegram, Gmail, the schedules and re-runs switched off.
It checks them in n8n, deletes them and confirms each is gone (GET -> 404). Nothing runs, nothing is sent.

## Or import by hand

In n8n: Workflows -> Import from file -> `inky-repair.json`, then `inky-main.json`. Open each red node and pick your
own credential (Apify: header auth `Authorization: Bearer <token>`; Telegram; n8n API; OpenRouter: header auth).
Replace `INKY_TELEGRAM_CHAT_ID` with your chat id, set the repair's "Run it again" to the main workflow, set the main
workflow's error workflow (Settings) to the repair one, and give the "Send me the best now" webhook a secret path.

Costs: about $0.23 of Apify per run at 60 listings per site (at most 120 runs a day), and a few cents of
OpenRouter only when a repair runs.
