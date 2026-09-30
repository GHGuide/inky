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

## Second pass: the items that were missing

| Item | What was done | Result |
|---|---|---|
| Claude Code → Inky | One `claude -p` run through OpenRouter (Claude Haiku), `--strict-mcp-config` with only Inky's MCP server. It called `list_bots`, then `bot_results` for a bot living on the Linux server (proxied by the Mac engine) | Pass: correct bots and the 3 books with prices |
| Linux | `Dockerfile` (python:3.12-slim + Playwright Chromium). The container on linux/aarch64 was paired from the Mac UI, then Travel Bookwatch was moved there: check run 11 results, then a proxied run (0 AI) and a live 1280×800 screenshot from the container | Pass |
| Windows | CI matrix on GitHub: windows-latest, macos-latest, ubuntu-latest | Pass: 20 tests (19 on Windows and Linux, where the macOS-keychain test skips) |
| Windows fixes found by reading | UTF-8 file reads (overlay.js has ⌥ and …), `.cmd` shims for `claude`/`codex`, `platform.node()` instead of `os.uname()`, memory via ctypes | Done, covered by the Windows CI run |
| Remote sign-in | A browser on another device gets no token in the page. It types the pairing code (wrong code → message; right code → in) | Pass |
| DNS rebinding | Page served to a foreign `Host` has no token (unit test) | Pass |
| Downloads | Share, skill file and n8n export now download with header auth; no token in any link. n8n export uses an n8n Header Auth credential | Pass |
| Menu bar app (macOS) | `native/mac/InkyBar` (Swift, no dependencies): status icon with Needs-you badge, menu per bot (Open, Run now, Pause/Resume/Stop), Needs you, Pause all, Stop my screen, Open Inky | Pass: `--selftest` builds the menu from live data |
| System-wide shortcuts | ⌥Space floating command bar (falls back to ⌃⌥Space if taken), ⌃⌥P pause all, ⌃⌥Esc stop everything on your screen | Registered: yes. Self-test ran the shortcut's action: panel opens as key window with focus in the input, filters "@Flat …", Esc hides it through the page bridge, shortcut reopens and closes it. Snapshot checked |
| Voice | Stand-in recognizer and synthesizer in the page: speech → message → spoken reply; mic paused while it speaks (the bot's own voice is ignored), resumed after; refused mic shows "microphone blocked" | Pass |
| Voice, real microphone | Chrome, mic allowed by you; the Mac spoke through its speakers with `say`. Heard "hello flat checker what did you do on your last run" and answered from the last run out loud. No echo of its own voice. A second spoken turn ("check again every morning") became a schedule change | Pass (fix: an empty speech result no longer sends an empty message) |

## Limits

- **Pressing the global shortcuts with a real keyboard** wasn't automated: it needs control of the whole desktop, which was declined. The self-test runs the same actions the shortcuts trigger, and the OS confirmed the shortcuts are registered.
- **Menu bar on Windows and Linux**: not built (macOS only). The web app and command bar work there.
- **"Your screen" means a visible browser window** the bot drives, not your whole desktop (a non-goal in the spec).
- **Live view and events** still pass the token in the URL (`?t=`), because images and EventSource can't send headers. These URLs are never shown as links.
