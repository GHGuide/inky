# Inky open bots: test report, 2026-09-30

Branch `build`. Every feature was driven through the real UI with computer control (Claude's built-in browser: clicks, typing, keys, file inputs), on a real engine (`python -m inky`, port 8800), a second engine acting as "your server" (port 8801), a local listings test site (port 8766) and one real public site (books.toscrape.com).
Unit tests: `.venv/bin/python -m unittest discover -s tests -t .`, **20 tests, OK**.

Models used: OpenRouter `z-ai/glm-5.3` (key in the macOS Keychain), local Ollama `qwen3:1.7b`, and a local OpenAI-compatible stub for the "custom server" path.

## Results

| Area | What was done in the UI | Result |
|---|---|---|
| Setup wizard | All steps: engine, models, keys, your-screen permission, first bot | Pass |
| New bot: draft | Typed a job, then "Draft the bot"; checked name, site, goal, rules, schedule | Pass (fix: "every morning" now drafts as daily) |
| Learn once | Watched it learn the test site (7 steps, 9 AI calls) and books.toscrape.com (1 step, 3 AI calls) | Pass |
| Correct it while learning | "Use the Prezzo max field…" mid-learn | Pass |
| Replay with no AI | Many runs: 0 AI calls, results identical | Pass |
| Real site accuracy | Travel category: 11 books, 6 under £40, cross-checked against the live page | Pass, 6/6 correct |
| Rules and filters | "Skip ground floor" in chat, numeric `!=`, missing field warning | Pass |
| Results tab | New badges, open ↗ links (absolute URLs) | Pass (fix: image URLs now absolute too) |
| Chat actions | Add rule, remember, run, schedule, speed | Pass (fix: a schedule change no longer wipes summary and quiet hours) |
| Live computer view | MJPEG stream, step labels, target box | Pass |
| Take over / hand back | Clicked and typed in the live view, then Hand back resumed the run | Pass |
| Command bar | ⌘K, run and navigate | Pass |
| Pause all (⌥P) | Pressed while a bot worked; status paused; Resume continued | Pass |
| Ask before irreversible | Approve (1 send), Deny (0 sends), from both Needs page and bot page | Pass, send log checked each time |
| Always for this step | Second run submitted without asking | Pass |
| Revoke "always" | New "ask again" on the skill step; next run asked again | Pass (new) |
| Repair | Moved button repaired at 85% confidence | Pass |
| Failed fix | 40% confidence stopped instead of guessing; "Show me once" recorded the fix | Pass |
| Robot check | Stopped and asked, never tried to solve | Pass |
| Sign-in gate | Stopped at the password field; the password was never typed | Pass |
| Your screen mode | Visible window with the coral frame, named cursor and pill; Alt+C chat, Esc stop, mouse pauses | Pass (screenshot and test_overlay) |
| Make it yours | Cat, Grape, Glasses, bot-colored frame, critter cursor, then Save | Pass: the live frame pixels read (127,114,228) = Grape, not coral |
| Call tab | Typed "What did you do on your last run?"; the reply was grounded in the last run | Pass (fix: greeting no longer says "I'm type message" when idle) |
| Voice | Mic is blocked in the test browser | Not tested |
| Activity | Runs, AI calls, "if it asked every step", cost, event log | Pass (fix: action skills no longer log "0 results") |
| Settings | Toggles persist, data folder | Pass (removed the crash-report toggle, which did nothing and contradicted "no Inky server"; shows the real data folder) |
| Models | Role save and test (OpenRouter 1.13 s), local model, custom server, disk-fit warnings | Pass |
| Keys | Add and remove in the Keychain (key pasted by the user, never typed by me) | Pass |
| Connectors: Claude Code | `claude mcp serve`, 25 tools; Read tool; automation after every run → `Write` a file | Pass (fix: retries `Write` after `Read` when Claude Code hasn't read the file yet) |
| Connectors: Codex | `python -m inky.codex_mcp` wrapper around `codex exec`; delegated a question and got an answer | Pass |
| Automations approval | Asks with the exact tool call; "Always for this automation" skipped later prompts; remove works | Pass |
| Inky as an MCP server | Codex → Inky `list_bots`; MCPClient test for list/results/message; no approve tool exposed | Pass |
| Computers: pair | Typed the address, name and 6-letter code of server B | Pass |
| Computers: move | Paused, packed, sent, check run on the server (14 results), done | Pass |
| Moved bot | Bot page, chat, Run now, scheduler every minute and 17:41 summary, all on server B through A's proxy | Pass (fix: A's scheduler no longer also runs a moved bot) |
| Share / import bot | Share file then Import a bot file created a copy | Pass (security fix: a shared file no longer includes sign-in cookies or chat history; only Move carries them) |
| Skill file / n8n | Download, import into another bot; n8n export = schedule + HTTP node, token read from `$env` | Pass |
| Bad files | Non-JSON and wrong JSON for bot and skill import | Pass (fix: shows a toast instead of failing silently) |
| Delete bot | Deleted a bot while it was waiting on an approval | Pass (fix: waits for the run to stop so no orphan rows; shutdown no longer crashes) |
| Bots home | Cards, live thumbnails (1280×800), status labels | Pass (fix: moved bot reads "on another computer") |
| Mobile (375 px) | 16 pages, menu drawer | Pass (fix: 6 pages scrolled sideways; rows and buttons now wrap) |
| Navigation | Leaving a page while it loads | Pass (fix: a slow render could overwrite the next page) |

## Limits, not tested or not built

- **Claude Code calling Inky**: `claude -p` fails with "OAuth session expired" on this Mac. The protocol path passes in `test_engine`; Codex → Inky works live. Run `claude` once to sign in again.
- **Voice input** on the Call tab: microphone blocked in the test browser. Typed input works.
- **Windows and Linux**: only macOS was available.
- **Native menu bar and global hotkeys**: not built. The command bar and ⌥P work inside the app. Esc, ⌥C and mouse-to-pause work in the bot's window.
- **"Your screen" means a visible browser window** the bot drives, not your whole desktop.
- **Download links carry the local API token in the URL** (`?t=`), like the live view and events stream. Fine on localhost; on a server install, don't paste those links anywhere.
- **n8n `$env` access** is blocked by default in some n8n versions (`N8N_BLOCK_ENV_ACCESS_IN_NODE`); paste the token into the node instead if so.
