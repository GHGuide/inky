# Inky open bots · design

Date: 2026-09-30 · Status: approved for build ("execute fully, then test fully")
Designs: https://claude.ai/artifact/34g5RGmfJ8V42iXtgEf4cD (page "Open bots (new)", boards 1–38)

## What it is

An open-source, local-first app for always-on bots, in the spirit of Dots (ChatGPT) and Grok bots,
built on Inky's idea: **learn a web job once with a model, then repeat it with no AI**.

- Each bot has a job, a critter look, rules, a memory, a schedule and **its own computer**:
  an isolated browser that is never the user's screen.
- You chat with a bot, watch its computer live, take over, and hand back.
- Bots stop and ask before anything irreversible (send, buy, pay, delete, submit, sign up).
  They never type passwords and never solve robot checks.
- Optional: a bot may drive a visible browser **on your screen**, inside a coral frame,
  and you can text it while it drives. Moving the mouse pauses it; Esc stops it.
- Models: local (Ollama or any OpenAI-compatible server) or cloud with your key
  (OpenRouter, Anthropic, OpenAI, Gemini, Groq, xAI, Mistral). Keys live in the OS keychain.
- Connectors are MCP servers. First-class: **Claude Code** and **Codex**, both directions:
  Inky calls them in automations, and they can call Inky.
- n8n, Apify and Telegram are optional; nothing requires them.

## Architecture

```
inky/                      Python 3.12, stdlib + Playwright only (no new deps)
  __main__.py              python -m inky [--port 8800] [--home ~/.inky]
  store.py                 SQLite: bots, skills, runs, events, messages, needs, settings, computers
  bus.py                   in-process event bus -> SSE
  llm.py                   model router: OpenAI-compatible chat, Anthropic; roles -> provider/model
  keys.py                  keychain (macOS `security -i` via stdin), file fallback 0600 elsewhere
  computer.py              one thread + Playwright browser per bot; element table; actions;
                           overlay (frame, named cursor, step label, pill, chat); screencast;
                           user-input detection; headful "your screen" mode
  skills.py                learn (model loop), record, replay (no AI), repair (name, then AI once),
                           extract + paginate, rule filters, safety gates
  safety.py                irreversible / password / robot-check detection
  bots.py                  bot runtime: chat -> actions, memory, rules, runs, results, scheduler
  mcp.py                   MCP stdio client (JSON-RPC, newline framed) + presets
  mcp_server.py            Inky as an MCP server (stdio) over the local HTTP API
  codex_mcp.py             MCP server wrapping `codex exec --json` (Codex 0.159 has no MCP server)
  transfer.py              export/import bot bundles; remote engines; move a bot
  health.py                Docker, Ollama, models, keys, computers, connectors -> problems
  server.py                HTTP API, SSE /api/events, MJPEG /api/bots/:id/screen.mjpg, static UI
  ui/                      index.html, app.js, app.css: v2 look (Geist, critters, pills, tabs)
tests/                     unittest; fixture site in tests/site/
```

### Key flows

- **Create:** describe a job → model drafts `{name, job, start_url, goal, schedule, rules, look}` →
  user edits and confirms.
- **Learn:** loop: index the page into a numbered element table (role, name, text, attrs) →
  model picks one action `{click|fill|select|press|goto|extract|next_page|done}` → run it with the
  overlay → record a step with a target descriptor. The user can correct it mid-learning in chat.
- **Replay:** run steps with no model. Target lookup order: css path (if role and name still match)
  → role + name → text → attributes. If none match → **repair**: ask the model once;
  accept only when confidence ≥ 0.7 and update the step; otherwise stop with a Problem
  (Show me once / Try a smarter model / Skip).
- **Safety gate:** before any step, check it. Irreversible → Needs you (approve/deny).
  A password field → the bot pauses for the user. A robot check → a Problem. The bot's "never" rules → block.
- **Results:** extracted items → rule filters (`field op value`) → diff with the previous run
  → new matches become a message (plus Telegram if connected).
- **Chat:** the model returns `{reply, actions[]}`. Actions: add_rule, remember, forget, learn,
  run, schedule, pause, resume, stop, speed, delegate (MCP tool call).
- **Your screen:** a headful browser window on the user's desktop with the overlay.
  User mouse or keys outside the bot's own actions → pause. Esc → stop. The in-page chat panel
  (⌥C / Alt+C) is isolated in a shadow root. Bot keyboard actions wait while the chat is focused.
- **MCP:** the client spawns the server, then initialize → tools/list → tools/call.
  Presets: Claude Code `claude mcp serve` (26 tools incl. Agent), Codex `python -m inky.codex_mcp`
  (tools `codex`, `codex_reply`). Inky's server offers list_bots, get_bot, message_bot, run_skill,
  list_needs, bot_results. Approving Needs-you items is not exposed.
- **Move:** export the bundle (bot, skills, memory, results, browser storage state) → POST it to the
  remote engine → start there → check one run → remove it locally.

## Non-goals for this build

Native desktop apps on your screen (only a browser); OS-wide hotkeys (in-app shortcuts only);
the marketplace backend; Docker bot images (bots use isolated Playwright browsers;
a remote engine can run in Docker); a Tauri shell (the UI is a local web app).

## Testing

- Unit tests (`python -m unittest`) run against a local fixture site. It covers search, results,
  pagination, a changed layout for repair, a send form for approval, a login and a robot check.
- End-to-end: drive the running app with computer control (the browser pane for the UI, the
  desktop for the your-screen window). Exercise every page and flow, and log the results in
  `docs/superpowers/test-report-2026-09-30.md`.
