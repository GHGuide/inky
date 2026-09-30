# Inky round 3 · onboarding, motion, real logos, connectors, easy connect, agent library

Date: 2026-09-30 · Status: approved in chat ("Yes, build it all")
Builds on: `2026-09-30-open-bots-design.md` and `2026-09-30-inky-app-and-personality-design.md`. Branch `build`.

The user asked for six things:
1. the onboarding window works properly;
2. much more motion;
3. real brand logos everywhere and no generic, AI-looking images;
4. connecting a Linux server (or any computer) is as easy as possible;
5. every connector works well;
6. when someone posts an agent, everybody can use it.

Their choices: a GitHub-based agent library; all four connect methods (SSH, LAN discovery, one-line install with a pair link, Tailscale); download the official logos; motion that is "calm app, lively critters".

## Constraints

- Engine: no new runtime Python packages. Desktop app: at most one new build-time crate, `tauri-plugin-deep-link`, for `inky://` links.
- UI stays v2: an add-on, never a redesign. The critters remain the only illustrations. There is no stock or AI imagery anywhere.
- Logos: official brand marks, unmodified, only to identify a service. Sources are Simple Icons (CC0) or the brand's own press kit. Each file is stored with its source in `inky/ui/logos/SOURCES.md`.
- Safety is unchanged:
  - approvals are still asked;
  - no passwords are typed: SSH works with keys only (`BatchMode=yes`);
  - no pairing code is ever broadcast;
  - a library agent only opens the sites it lists.
- Everything works offline, except the parts that need the network (library, logos download at build time, installs).

---

## Part 1 · Onboarding that works, with real logos

### Bugs found (reproduced)
- At the app's minimum size (900×600) the Continue button is off-screen on steps 1, 3 and 6, and the wizard can't scroll.
- "Pick a local model", "Paste a key" and "Pair a server" leave the wizard for normal pages, with no way back.
- The wizard asks for terminal commands (`ollama serve`, `git clone …`).
- The app doesn't read the repo's `.env`, so it reports no key and only offers the dead-end button.

### Design
- **Layout:** the wizard scrolls inside its window and keeps a sticky footer (Back / Continue) visible at every size down to 900×600. On a phone the footer sticks to the bottom.
- **Steps stay in the wizard.** Each choice opens inline:
  - **Model:**
    - a provider grid with logos (OpenRouter, Anthropic, OpenAI, Gemini, Groq, xAI, Mistral, custom);
    - a key field and a Test button in place (keys go to the Keychain as today);
    - or **On this computer**: "Start Ollama" (the engine runs `ollama serve` if Ollama is installed, otherwise an Install link), then a model picker with a download progress bar (existing pull API), or LM Studio if it's running.
  - **Computers:** the easy-connect panel from Part 4 (found servers, SSH, pair link or code), inline.
  - **Phone:** the Telegram guided setup from Part 3, inline.
- **Motion:** steps slide and fade in (direction follows Next/Back), the progress pills fill, the critter on Welcome waves.
- **Tests:** a Playwright check walks all 6 steps at 900×600 and 1280×820. Every step's Continue must be visible or reachable by scrolling. Every inline action stays on `#/setup/*` and there are no page errors.

### Logos
- **Location:** `inky/ui/logos/<slug>.svg`, plus `inky/ui/logos/SOURCES.md` (file → source URL → licence or brand page).
- **Slugs:** claude, anthropic, openai, codex (the OpenAI mark), openrouter, googlegemini, groq, xai, mistral, ollama, lmstudio, n8n, apify, telegram, github, docker, linux, tailscale, apple, windows, mcp.
- **Helper:** `logo(slug, size)` returns an `<img>` with alt text. It falls back to a clean lettermark only when a file is missing.
- **Used in:** Connectors, Models, Keys, Setup, Computers (OS and Docker), Library (authors via GitHub).

## Part 2 · Motion: calm app, lively critters

### App motion (`inky/ui/motion.js` plus CSS)
- **Springs and entrances:** Web Animations springs. Cards, list rows and chat messages come in staggered (fade + 8 px rise, 30 ms apart).
- **Page transitions:** they keep the existing View Transitions, with a slide.
- **Press and hover:** buttons press in (scale .97); cards lift on hover.
- **Counters:** stats and badges count up; progress bars ease.
- **Toasts:** they slide in with a spring and leave with a fade.
- **Live pill:** the status pill pulses while a bot works.
- **Reduced motion:** all of this turns off under `prefers-reduced-motion`.

### Critter life v2 (`life.js`)
- **Idle behaviours**, scheduled per critter, never in sync:
  - look around (the pupils glance left and right);
  - a slow sway of tentacles, tail or goo;
  - an occasional yawn (mouth opens, eyes squint);
  - a stretch (scaleY bounce);
  - a blink pair.
- **Reactions:** hover → it looks at you and wiggles; click → a squish and a happy hop; new results → a dance; needs you → a wave plus a small jump every 8 s; learned → a proud puff; asleep → breathing slows and the zzz rise.
- **Parts:** limbs are split per tentacle (octopus), paws (cat) and the base wave (blob), so each can sway on its own phase.
- **Tests:** `node --test` covers the behaviour scheduler (deterministic per seed, never two critters on the same beat, respects reduce-motion) and the reaction mapping.

## Part 3 · Connectors that work

Every connector card has the same parts:
- a logo;
- a status (not installed / installed, signed out / connected);
- a **Test** button that does a real check and shows the result;
- a clear message with a fix button for each failure;
- an automatic reconnect on start.

| Connector | What works |
|---|---|
| Claude Code | Detects the install and the login (`claude auth status`). Connect (MCP) shows its tools. Test lists the tools. **Add Inky to Claude Code** (one click, only when you click): `claude mcp add inky …` |
| Codex | Detects the install and the login (`codex login status`). Connect (wrapper MCP). Test runs a read-only prompt. **Add Inky to Codex**: appends `[mcp_servers.inky]` to `~/.codex/config.toml` after showing the change |
| Telegram | Paste the bot token (Keychain), send /start to your bot, and Inky polls `getUpdates` and fills your chat id. Test sends "Inky is connected" to you. Needs-you and new results arrive there |
| n8n | URL + API key. Test lists your workflows. **Send to n8n** creates the skill's workflow through the n8n API. A bot action/automation `n8n.trigger` calls a workflow's webhook with the new results |
| Apify | API token. Test reads your account. A bot action/automation `apify.run` starts an Actor with input and brings back its dataset items as results |
| Any MCP server | Name + command (+ env). Test lists its tools. It also gets a quick picker for common servers (GitHub, filesystem, fetch) |

Built-in connectors (Telegram, n8n, Apify) are **internal tool providers** with the same shape as MCP servers. The same catalog, `delegate`, automations and approval gate apply to all of them. Handing work to any connector still asks first unless you said "always".

## Part 4 · Connect a Linux server (or any computer)

- **`install.sh`** at the repo root (Linux, and macOS for a spare Mac):
  - With Docker, it builds and runs Inky as a container with a volume and `--restart unless-stopped`.
  - Otherwise it creates a Python venv and a systemd (or launchd) service, then runs `playwright install --with-deps chromium`.
  - It prints `inky://pair?url=http://<ip>:8800&code=<code>`, plus a terminal QR code if `qrencode` is there.
  - `--json` prints `{"url","code"}` for the SSH path.
- **Pair link:** `inky://pair?...` opens the app (deep-link plugin) and pairs after one confirm. The Computers page also accepts a pasted link.
- **SSH setup:** in the app, "Set up a server over SSH" takes `user@host`. The engine runs `ssh -o BatchMode=yes -o ConnectTimeout=10 user@host 'curl -fsSL <install-url> | sh -s -- --json'`, streams progress, reads the JSON and pairs. The failures it explains:
  - no key;
  - host unreachable;
  - no curl;
  - not Linux or macOS.
- **LAN discovery:** an engine started with `--host 0.0.0.0` sends a UDP beacon every 5 s to port 48800 with `{"inky":1,"name","url","version"}` (no code, no token). The local engine listens and lists "Found on your network" in onboarding and Computers. Pairing still needs the code shown on that server (its log, or the install output).
- **Tailscale:** if `tailscale status --json` works, peers that answer `/api/ping` on :8800 are listed as "On your tailnet". Their Tailscale address is used, so they stay reachable away from home.
- **Tests:**
  - beacon encode/decode;
  - the listener dedups and expires entries after 30 s;
  - the pair-link parser;
  - an SSH command builder (no shell injection: the host is validated as `[user@]host[:port]`);
  - `install.sh --json` in the Linux Docker test image.

## Part 5 · Agent library (GitHub)

- **Where it lives:**
  - `library/agents/<slug>.inky`: shared bundles, which never carry sign-ins, memory, results or chat;
  - `library/agents/<slug>.json`: the listing (title, summary, sites, tags, author, critter look, version);
  - `library/index.json`: built by CI.
  - The app reads the index from `https://raw.githubusercontent.com/GHGuide/inky/main/library/index.json`, overridable with `INKY_LIBRARY_URL`.
- **CI (`library.yml`), on pull requests touching `library/`:**
  - validate the schema;
  - reject cookies, memory, results, messages and anything that looks like a secret;
  - list every domain the skills visit and flag irreversible steps;
  - comment a summary;
  - on main, rebuild `index.json`.
- **Posting from the app** (Share → Post to the library):
  - local checks first (the same rules as CI);
  - then, if `gh` is signed in: fork, branch and pull request, automatically;
  - otherwise GitHub's "new file" page opens with the file filled in, and you click "Propose".
  - **Share link now:** with `gh`, a public Gist plus an `inky://install?url=…` link anyone can open.
- **Library tab:**
  - cards with the critter, summary, "visits: site.com", "may: submit a form (asks you)", the author and a Reviewed badge;
  - search and tags;
  - **Get** shows a permission preview, then imports (with the hatch).
- **Safety:** an imported library agent records its allowed domains. During replay a `goto` or link to another domain stops with "This agent only works on …". Every safety gate still applies.
- **Limits:**
  - No install counts or ratings (they need a server).
  - The public library appears only when `build` is merged to main.
- **Tests:**
  - index build;
  - the checker (secrets, domains, irreversible steps);
  - the domain guard in replay;
  - install from an index entry (local fixture).

## Out of scope
- A hosted backend, accounts, ratings.
- Publishing a Docker image (it would need a GHCR workflow; ask first).
- Signing and notarizing the app.
