# Inky app server

One stdlib file, `serve.py`. It serves the front-end in `app/static/` and a small JSON API on http://127.0.0.1:8765.

```bash
.venv/bin/python app/serve.py          # from the repo root; optional port: app/serve.py 8799
.venv/bin/python app/test_serve.py     # self-check: every endpoint, with data and without; GLM and n8n faked, no network
```

| Endpoint | What it returns |
|---|---|
| `GET /api/state` | `{research, rules, plan, n8n: {base, main_url, repair_url}, race, program}`; `null` where a file is missing |
| `GET /api/executions` | `[{id, status, startedAt, stoppedAt, mode, workflow: "main"\|"repair"}]`, newest first, cached 20 s; `[]` if n8n is not set up |
| `POST /api/interview {messages}` | `{done:false, round, understood:[{k,v}], questions:[{id,text,why}]}` or `{done:true, plan, summary, results_format}`. At most 5 rounds. |
| `POST /api/command {text, dry_run?}` | `{change, rule, removed, applied, matches_before, matches_after}`, plus `n8n_error` if the push failed or was skipped. Writes `rules.backup.json` (one version back) first, then pushes the rules to the main n8n workflow, and republishes it if it was active. `dry_run: true` changes nothing. |
| `POST /api/share {to, text?}` | `{name, description, link, gets, keeps}`. The budget is never sent to GLM, and a description with the amount is rejected. Nothing is sent to anyone. |

Errors come back as `{error}`, with status 400 for a bad request and 502 when GLM or n8n fails. POSTs need `Content-Type: application/json`, and the server answers 403 to any host other than 127.0.0.1 or localhost and to POSTs from another website. Every GLM call goes through `derive.glm`, is checked, and is retried once if the answer is invalid. Each call's cost is logged to stderr.

## What it needs

- `.env` in the repo root: `OPENROUTER_API_KEY` for interview, command and share. `N8N_BASE_URL` and `N8N_API_KEY` for the executions list and for pushing rules. Put only the origin in `.env` (`https://sosus119.app.n8n.cloud`): `workflow.py` needs it that way. The server also accepts a pasted browser URL such as `https://sosus119.app.n8n.cloud/home/workflows` and keeps only the origin, but `workflow.py` does not.
- Data from `derive.py` in `data/`, or in `$INKY_DATA` if that is set. Until it exists, `/api/state` returns `null` for research and rules, and `/api/command` answers "No rules yet" without calling GLM.
- `data/n8n.json` from `workflow.py`, always read from `data/`, as `workflow.py` writes it there. Without it there are no n8n links, no executions and no push. If `INKY_DATA` points at another folder, the links and executions still show, but a rule edit is not pushed (`n8n_error: "not pushed: ..."`), so a test or demo copy never overwrites the live workflow.
- `node` on the PATH. The before and after match counts use `inky.js`.
