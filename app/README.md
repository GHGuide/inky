# Inky app server

One stdlib file, `serve.py`. It serves the front-end in `app/static/` and a small JSON API on http://127.0.0.1:8765.

```bash
.venv/bin/python app/serve.py          # from the repo root; optional port: app/serve.py 8799
.venv/bin/python app/serve.py --demo   # no keys: the committed snapshot in data-demo/, never calls n8n, Apify or GLM
.venv/bin/python app/test_serve.py     # self-check: every endpoint, with data, without, and in demo mode; nothing leaves the machine
.venv/bin/python app/make_demo.py      # regenerate data-demo/ from data/ and the live runs (read only); --record re-records the GLM replies
INKY_SAFE=1 .venv/bin/python app/serve.py 8799   # for tests: builds go to staging, best-now only to a local webhook
```

| Endpoint | What it returns |
|---|---|
| `GET /api/state` | `{research, rules, plan, n8n: {base, main_url, repair_url}, race, program}`; `null` where a file is missing |
| `GET /api/executions` | `[{id, status, startedAt, stoppedAt, mode, workflow: "main"\|"repair"}]`, newest first, cached 20 s; `[]` if n8n is not set up |
| `POST /api/interview {messages}` | `{done:false, round, understood:[{k,v}], questions:[{id,text,why}]}` or `{done:true, plan, summary, results_format}`. At most 5 rounds. |
| `POST /api/command {text, dry_run?}` | `{change, rule, removed, applied, matches_before, matches_after}`, plus `n8n_error` if the push failed or was skipped. Writes `rules.backup.json` (one version back) first, then pushes the rules to the main n8n workflow, and republishes it if it was active. `dry_run: true` changes nothing. |
| `POST /api/share {to, text?}` | `{name, description, link, gets, keeps}`. The budget is never sent to GLM, and a description with the amount is rejected. Nothing is sent to anyone. |
| `GET /api/run_detail` | `{main, ok, repair}`: items, ms and error per step of the latest run and latest good run; `repair` adds `step, change, error, before, after` (the broken step's actor input before and after the fix, parsed), `failed` and `again`. Cached 60 s. |
| `GET /api/summary?since=<iso>` | Default the last 24 h. `{since, runs, ok, failed, waiting, repairs, fixes:[{id,startedAt,step,change}], listings_checked, new_listings, matches, apify_usd, apify_usd_runs, apify_usd_per_run, ai_calls: 0, glm_usd_research, n8n_stats, per_run:[{id,startedAt,status,mode,listings,new,matches,secs,sources:{step:items},apify_usd}], errors}`. A run is an execution where a source step ran (not the digest or a best-now send). Each execution is fetched once and kept in `data/run-cache.json`; the whole answer is cached 60 s. `apify_usd` is all Apify spend since `since`, `apify_usd_runs` the part started by these runs. `new_listings` counts raw items, so a few more than `n8n_stats.fresh` (the workflow's own counters). |
| `GET /api/end` | `{listings_read, runs, listings_checked, new_listings, matches, research_matches, fixes, apify_usd_total, apify_usd_per_run, glm_usd_research, ai_calls_per_run: 0, repo}`, all since the start; listings and matches from the workflow's own counters when n8n answers, so they match the digest. |
| `POST /api/plan {plan}` | `{ok, plan}`. The keys must be exactly plan.json's; cities from porto, bari, lodz; the `never` limits are always kept. The previous plan goes to `<data>/plan.backup.json`. |
| `POST /api/best_now {n?}` | `{sent, matches}`: the top n (default 3, max 10) matches of the current rules go to the n8n webhook `workflow.best_now_url()`, which asks on Telegram. 503 until the webhook is deployed; with `INKY_SAFE=1` only a local webhook is used. |
| `GET /api/bundles` | `{bundles:[{id, title, description, author, cities, rules, sources, created_at, example}]}`: `share/bundle/` as id `example`, then every bundle under `<data>/shared/`, newest first. For the Marketplace. Add one with `share/export.py --out data/shared/<name> --author X`. |
| `POST /api/research/run {plan?, offline?}` | Server-Sent Events (`data: <json>` per event): `{type:"step", text, sub?}`, `{type:"version", v, matches, zones, rules, removed}` per GLM round, then `{type:"done", research, rules}` or `{type:"error", text}`. A given plan is checked and saved first. Uses the cached `raw/` listings, no scraping. One run at a time (409). `offline: true` uses fixed rules, no GLM. |
| `POST /api/build/run {staging?}` | Server-Sent Events of `workflow.deploy()`: steps, then `{type:"done", main_url, repair_url, staging, mode, active, gmail}`. Live by default; `INKY_SAFE=1` forces staging; a server on another data folder than `data/` refuses a live build (503). One at a time (409); 503 while `workflow.deploy` is missing. |

Errors come back as `{error}`, with status 400 for a bad request, 409 when a run is already going, 503 when something is not set up yet, and 502 when GLM or n8n fails. The two streams answer with plain JSON and one of these statuses when they cannot start, so check `response.ok` before reading the stream; once streaming, a failure arrives as an `error` event. POSTs need `Content-Type: application/json`, and the server answers 403 to any host other than 127.0.0.1 or localhost and to POSTs from another website. Every GLM call goes through `derive.glm`, is checked, and is retried once if the answer is invalid. Each call's cost is logged to stderr.

## What it needs

- `.env` in the repo root: `OPENROUTER_API_KEY` for interview, command and share. `N8N_BASE_URL` and `N8N_API_KEY` for the executions list and for pushing rules. Put only the origin in `.env` (`https://YOUR-N8N.app.n8n.cloud`): `workflow.py` needs it that way. The server also accepts a pasted browser URL such as `https://YOUR-N8N.app.n8n.cloud/home/workflows` and keeps only the origin, but `workflow.py` does not.
- Data from `derive.py` in `data/`, or in `$INKY_DATA` if that is set. Until it exists, `/api/state` returns `null` for research and rules, and `/api/command` answers "No rules yet" without calling GLM.
- `data/n8n.json` from `workflow.py`, always read from `data/`, as `workflow.py` writes it there. Without it there are no n8n links, no executions and no push. If `INKY_DATA` points at another folder, the links and executions still show, but a rule edit is not pushed (`n8n_error: "not pushed: ..."`), so a test or demo copy never overwrites the live workflow.
- `node` on the PATH. The before and after match counts use `inky.js`.
