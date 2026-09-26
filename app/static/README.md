# Inky front-end (app/static)

Plain HTML, CSS and vanilla JS. No framework, no build step. `app/serve.py` serves this folder and the `/api/*` routes.

```bash
.venv/bin/python app/serve.py            # then open http://127.0.0.1:8765/
.venv/bin/python app/static/check_ui.py  # self-check: stub API, every route in headless Chrome, screenshots in /tmp/inky-ui/
```

| File | What it is |
|---|---|
| `index.html` | Shell: fonts (Geist, Geist Mono), `app.css`, `app.js` |
| `app.css` | Design tokens and components copied from the approved `*.dc.html` designs |
| `app.js` | Hash router, one function per screen, all data from `/api/state`, `/api/executions`, `/api/interview`, `/api/command`, `/api/share` |
| `check_ui.py` | The self-check. Three passes: full fixtures, empty state, and 1280x720 with no runs yet. It fails on any console error, uncaught exception, missing element, a card squashed by its column, or content wider than its panel |

Routes: `#home #task #confirm #research #screen #fast #results #workflow #activity #share #market`.

- Every number on screen comes from the API. When data is missing, a screen shows "Runs after the first build". `#market` is the only screen with static sample agents.
- The message box on every task screen posts to `/api/command` and shows the change and the matches before and after. On `#task` it answers the interview instead.
- `#task` runs the real interview: rounds collapse as they finish, and the right panel counts what is clear. When the interview is done, the app moves to `#confirm`. Interview progress is kept in `sessionStorage`.
- `#screen` reads `teach/tecnocasa.program.json` (`steps[].do/label/target.css` and `item.fields`). `#fast` reads `data/race.json` (`compiled` and `llm`).
- The page polls `/api/state` and `/api/executions` every 20 s, so research and runs show up while the build finishes. It never re-renders over text you have typed and not sent.
- Match counts: every screen shows the same number. It is the count from the last command for the current rules, or else the research version with those rules. `derive.py` saves only the first 15 homes. After a command, the ones that fail a new rule are hidden, and the next research run lists the rest.
- Status: `/api/state` has no n8n "active" flag. The header says "Running · every 15 min" only when a scheduled run started in the last 30 minutes. Otherwise it says "Built in n8n · no runs yet" or shows the last run.
- Layout: designed at 1440 wide. Below 1400 px the thread gets narrower, and the n8n picture zooms down to fit.
- The mic button uses Chrome's built-in speech recognition, which sends the audio to Google. Nothing else leaves the page apart from `/api/*` calls and Google Fonts.

What it needs from you: nothing extra. Start `app/serve.py` with the repo's `.env`. The n8n links come from `N8N_BASE_URL`. Use the bare origin (`https://sosus119.app.n8n.cloud`); `serve.py` also strips a pasted path such as `/home/workflows`.
