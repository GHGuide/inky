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

## Third pass: the desktop app and personality

Plan: `docs/superpowers/plans/2026-09-30-inky-app-and-personality.md`. Unit tests: 38 Python, 5 Node (`node --test inky/ui/*.test.mjs`), 2 Rust (`cargo test`).

| Feature | How it was checked | Result |
|---|---|---|
| Moods | Gallery of all 9 moods × 3 critters, plus live runs: calm → focused while working → waving while it waits for your yes → calm after Deny | Pass (fix: a run waiting on you now waves instead of looking busy) |
| Blinking, breathing, eyes that follow you | In the page: blinks on a per-critter schedule that never syncs (unit test), pupils follow the pointer | Pass |
| Sounds | Each event mapped (plip, knock, chime, rise); Sounds off and quiet hours silence them | Pass (fix: "Sounds off" was ignored) |
| Typing bubble, confetti, page transitions | Live chat; confetti on level-up | Pass |
| Persona | Edited in Make it yours (sliders, catchphrase, bio). The real model then used your name, the cat's naps and its catchphrase | Pass (fixes: it re-ran old actions it was only recounting; settings you change are now noted in its chat) |
| Drafted persona | New bot on books.toscrape.com: the model wrote "Bon voyage, bargain hunter!" | Pass |
| While you were away | Card after 3 h away: runs, new results, waiting items, each critter in its mood | Pass |
| Near-miss suggestion | Limit set to £36: "2 results were just outside your under £36 rule", with the chip "Raise it to £40" | Pass |
| Chip | One tap: rule updated, chip marked done, next run found 3 new (the two near-misses and one more) | Pass |
| Levels | Real runs up to 10: confetti, toast, "I unlocked the scarf", the scarf wearable, the others locked with their run counts | Pass (fix: the level message came before the run's own message) |
| Diary, stats, About you | Diary tab stats and level bar; memory add and edit | Pass (diary entries are written at quiet-hours start, covered by a unit test) |
| Team life | Real model: Travel Hunter told Flat Checker about 3 books; Flat Checker answered in character and asked you. No approval was needed or created | Pass |
| Team room, office view | Feed shows the exchange; office at desktop and 375 px, evening sky | Pass |
| Hatch, tour, goodbye | Hatch shows the intro in its own words; 4-step tour saved; goodbye "packed its goo" then deleted | Pass |
| App: its own window | Tauri window, no browser, no address bar, no localhost visible | Pass |
| App: first launch | Fresh folder: the app started its own engine and downloaded Chromium into its folder | Pass |
| App: attach | With a CLI engine already on the same folder, the app used it and started none, and the CLI engine survived the app quitting | Pass |
| App: quit | Quitting stops the engine it started and removes engine.json | Pass (fix: PyInstaller's loader left the real engine running; the engine now stops when its stdin closes) |
| App: bundled engine | Travel Hunter ran inside the app: 11 results, 0 AI | Pass |
| App: open .inky file | macOS "open with Inky": bot imported, says hello | Pass (fix: shared files no longer carry what the bot knows about you or its results) |
| App: native link | Page → app commands (tray state, bar, buddy, notify) | Pass (fix: app commands must be declared and allowed for the local engine page) |
| Shortcuts | ⌃⌥Space opened the floating bar, typing filtered it, "Open Needs you" opened the main window; ⌃⌥P paused | Pass (fix: ⌥Space is taken by another app on this Mac even though registering it works, so ⌃⌥Space always opens the bar too) |
| Dock badge | Red "1" on the Inky icon while a bot waited, cleared after Deny | Pass |
| Desktop buddy | Flat Checker peeked in at the bottom right while it waited; clicking it opened Needs you; it hid after Deny | Pass (fix: buddy mode reused the bar's hidden container) |
| Notification | The app sent "Flat Checker needs you" (no error) while its window was hidden | Sent; the banner wasn't seen on screen (macOS may need permission for the unsigned build) |
| Tray menu | The tray item exists (checked through accessibility), but this Mac's full, notched menu bar hides it | Not opened; macOS behavior. Everything in it is also in the window, the bar and shortcuts |
| Launch at login | Reads its state from the app | Not switched on: it installs a login item on your Mac, so that's yours to turn on |
| Release app, fresh install | The release `.app` on an empty data folder: started its engine, downloaded the bots' browser by itself (557 MB installed), quit cleanly | Pass |
| CI | Unit tests (Python + UI) and the app build (engine binary check, `cargo test`, `tauri build`) on macOS, Windows and Linux | Pass on all three (fixes: a Windows-only test assumption; engine.json is now written atomically, a race CI caught) |

## Fourth pass: onboarding, motion, real logos, connectors, easy connect, agent library

Plan: [plans/2026-09-30-inky-round3.md](plans/2026-09-30-inky-round3.md). Unit and browser tests: **70 Python tests and 6 UI tests, OK**. Checks were run against the new release build's own engine (a separate copy with its own data folder), dev engines, a real sshd container, a clean `python:3.12-slim` container and real public sandbox sites. Computer control of the test copy of the app was declined, so its screens were checked with a headless browser on the same engine the app window shows.

| Area | What was done | Result |
|---|---|---|
| Onboarding | All 6 steps at the app's smallest window (900×600) and at 1280×820 | Continue stays on screen on every step (it was off screen on step 3 at y 602) |
| Onboarding choices | Provider tiles, key form, pairing and Telegram all open inside the wizard | Pass: nothing leaves `#/setup` |
| Model after a key | Inky lists the provider's models, picks one, tests it, and uses it (checked against realistic lists for 6 providers) | Pass: claude-sonnet-4-5, gpt-5-mini, gemini-2.5-flash, gpt-oss-120b, grok-4-fast, mistral-medium |
| Local model | **Start Ollama** on this Mac, then "Use this" | Ollama answered in 0.6 s; qwen3:1.7b replied "OK." in 2.2 s |
| Real logos | 20 brand marks (Simple Icons CC0 plus the brands' own files), each with its source in `ui/logos/SOURCES.md` | Pass; no letter tiles or generic glyphs left |
| Motion | Pages slide in, content staggers in, numbers count up, buttons give when pressed, toasts spring | Checked in a browser, no errors; everything is off under reduced motion |
| Critters | Separate tentacles sway, cat tail, look around, yawn, stretch; they wiggle on hover, squish on click and dance on new results | Gallery checked by eye; the scheduler tests pass |
| App finds your tools | The test copy was started by LaunchServices (the bare Dock PATH) | Claude Code and Codex were both found (the engine's PATH has your login shell's folders) |
| Claude Code, Codex | Connect and Test from Connectors | 26 and 2 tools; the status shows Claude Code "signed out" with its fix |
| Telegram | Paste the token → send /start → Inky finds your chat and says hello (fake Telegram API, in the real browser) | Pass |
| n8n, Apify | Setup, test, send a skill, trigger and run_actor against fake APIs; a wrong n8n address shows "Couldn’t reach n8n at …" | Pass. No real n8n or Apify account was used |
| install.sh | In a clean `python:3.12-slim` container: install, start, print address and code | Pass: the engine it started answered on the network |
| Set up over SSH | Real ssh into a throwaway sshd container with a throwaway key: connect, install, service, pair | Paired in 4.4 s. An unreachable host shows "Couldn’t reach … over SSH" with a fix |
| Found on your network | Two real engines, the second on 0.0.0.0: UDP beacon, listed in Computers, paired with its code from the page | Pass from the dev engine. The release app heard nothing: macOS keeps apps off the local network until you allow it. The build now asks with a clear reason (Info.plist), and Computers says where to allow it |
| Tailscale | `tailscale status --json` on this Mac | Read fine: 1 peer online, no Inky on it |
| Pair links | `handleLink("inky://pair?…")` in the page: one confirm, then paired | Pass. The OS-level `open inky://…` wasn't tried, because your own Inky was running and macOS could have handed it the link |
| Library | Two starters made by running them for real with no AI: Book Bargains (60 books over 3 pages, 14 under £20) and Quote of the Day (20 quotes), checked and indexed | Pass. The Library tab lists them; Get shows the permission preview; the installed agent ran in 3.4 s with 0 AI calls |
| Domain guard | A library agent's step leading to another site | Stops with "This agent only works on …" (test); a same-site subdomain is allowed |
| Posting | Share → Post to the library shows the exact public file and the checker's result | Checked up to the final button. Not pressed: it would open a real pull request on your GitHub |

## Limits

- **The desktop app is unsigned**: macOS asks you to right-click → Open the first time; Windows SmartScreen asks too.
- **Approve/Deny inside a desktop notification** isn't possible with Tauri; the notification brings you to the decision.
- **Windows and Linux builds** come from CI; their tray, buddy and shortcuts were not tried by hand.
- **"Your screen" means a visible browser window** the bot drives, not your whole desktop (a non-goal in the spec).
- **Live view and events** still pass the token in the URL (`?t=`), because images and EventSource can't send headers. These URLs are never shown as links.
- **The public library, the one-line install and "Set up over SSH" use the `main` branch** (`library/index.json`, `install.sh`). Until `build` is merged into `main`, the Library tab shows the two starters that ship with the app, and the install line and SSH setup won't find `install.sh`.
- **No install counts or ratings** in the library: they would need a server.
- **Found on your network needs macOS's Local Network permission** for the app, which macOS asks for the first time you open Computers.
