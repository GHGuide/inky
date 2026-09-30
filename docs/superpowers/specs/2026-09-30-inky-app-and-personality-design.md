# Inky app and personality · design

Date: 2026-09-30 · Status: approved in chat, spec for review
Builds on: `2026-09-30-open-bots-design.md` (engine, UI, MCP, move). Branch `build`.

Two goals from the user: **make Inky a real app, not a localhost page**, and **give the bots
personality so they feel alive**. Chosen in chat:

- The app shell is **Tauri 2**, for Mac, Windows and Linux.
- The app is **self-contained**: the engine is bundled, and Chromium downloads on first launch.
- **8 personality layers:** living critters, sound and motion, character and voice, proactive and
  aware, growth and relationship, team life, native presence, rituals.
- **Not chosen:** in-character copy. System text and error text stay as they are.

The work is built in four parts. Each part has its own plan and ends with a working app.

## Constraints (all parts)

- Engine rules stay the same: Python 3.12, stdlib + Playwright + httpx (the existing deps).
  **Build-time only:** PyInstaller for the engine binary; `@tauri-apps/cli` and the Tauri crates for
  the shell. No new runtime Python packages.
- The UI stays the v2 look (Geist, critters, pills, tabs). New things are **add-ons to v2 screens**,
  never a redesign (user preference).
- **Safety is untouchable.** A persona never rewrites approval, safety or problem wording. It never
  skips an ask-first step. It never makes a bot type passwords or solve robot checks. Bot-to-bot
  hand-offs go through the same approval gate.
- **Quiet and considerate.** Proactive notes are at most **one unprompted note per bot per day**,
  never in quiet hours. Sounds follow mute, quiet hours and the OS Do Not Disturb (where it can be
  detected). Motion follows `prefers-reduced-motion`.
- **Cheap.** Personality features are templates first. The model polishes at most once per bot per
  day (diary, morning paper), and only when a chat model is set.
- **Disk.** A Tauri build needs about 6 GB free. The machine has about 3 GB. Free space before Part 1.

---

## Part 1 · The app (Tauri) and native presence

### Shape

```
desktop/                      Tauri 2 project
  package.json                devDependency @tauri-apps/cli (build only)
  src-tauri/
    Cargo.toml                tauri 2 + plugins: shell (sidecar), notification, global-shortcut, autostart
    tauri.conf.json           windows: main, bar, buddy; externalBin: binaries/inky-engine
    capabilities/*.json       IPC allowed only for the local engine origin
    src/main.rs               start/attach engine, windows, tray, shortcuts, notifications, badge
    binaries/                 inky-engine-<target-triple> (built by scripts/build-engine.py)
  scripts/build-engine.py     PyInstaller: inky → one binary incl. the Playwright driver
```

### Engine lifecycle

1. On launch, the app reads `~/.inky/engine.json`, which holds `{url, pid, version}`. The engine
   writes this file on start and removes it on exit. If the file exists and `/api/ping` answers,
   the app **attaches** to that engine: the CLI or a previous instance may already be running, and
   two engines must never share one database.
2. Otherwise the app starts the sidecar with `--port 0 --no-open --home ~/.inky`. The engine binds a
   free port and prints `Inky is running at <url>`, and the app reads the URL from stdout.
   `--port 0` and `engine.json` are new engine features.
3. The main window loads the engine URL. It has no address bar and no browser chrome. Because the
   request comes from loopback with a `127.0.0.1` Host, the page gets the token exactly as today.
4. On quit, the app stops the sidecar with SIGTERM (Windows: terminate), but only if it started it.
5. **First launch:** if Chromium is missing from `PLAYWRIGHT_BROWSERS_PATH=~/.inky/browsers`, the UI
   shows "Getting your bots a browser…" with progress. The new endpoint `POST /api/setup/browser`
   runs the Playwright driver's `install chromium` and streams progress over SSE (`browser` events).

### Windows (Tauri)

- **main**: the app, 1280×820, minimum 900×600, remembers its size and position.
- **bar**: transparent, borderless, always on top, hidden until ⌥Space. It loads `?bar=1#/bar`,
  the existing bar mode. The `native()` bridge in `app.js` calls Tauri IPC (`invoke("bar", …)`)
  when Tauri is present, and the old WebKit handler otherwise.
- **buddy**: a small transparent, always-on-top, click-through window at the screen edge. It is
  shown only when a bot needs you and the Buddy setting is on. The critter peeks in; clicking it
  opens the need in main.

### Native presence

- **Tray:** a critter icon, whose frames animate while any bot works (the Rust side swaps icons).
  The menu offers each bot (Open, Run now, Pause/Resume/Stop), Needs you (n), Command bar,
  Pause all, Stop my screen, Open Inky and Quit. The status comes from polling `GET /api/state`
  every 4 s with the token from `~/.inky/api_token`.
- **Badge:** the Needs-you count on the dock/taskbar (`set_badge_count` on macOS and Linux, an
  overlay icon on Windows).
- **Shortcuts** (global-shortcut plugin):
  - ⌥Space shows or hides the bar, falling back to ⌃⌥Space if the first is taken;
  - ⌃⌥P pauses all bots;
  - ⌃⌥Esc stops every bot on your screen.
- **Notifications** (notification plugin): new Needs-you items and new results, with the bot's name
  and critter. Clicking one opens the right page. *Approve/Deny buttons inside a desktop
  notification are not possible* (Tauri supports actions on mobile only), so the notification
  opens the decision instead.
- **Launch at login:** a setting that uses the autostart plugin.
- **Files:** opening an `.inky.json` or `.skill.json` file imports it (a file association).
- **InkyBar (Swift) is deleted** once the tray, shortcuts and bar work in the Tauri app.

### Builds

- `npm run build` in `desktop/` builds the engine binary, then `tauri build`.
- **CI:** a matrix on macOS, Windows and Ubuntu builds the app and uploads the `.dmg`, `.msi` and
  `.AppImage` as artifacts. Builds are unsigned, so macOS needs right-click → Open the first time.
- **Tests:**
  - engine: `--port 0` and `engine.json` (unittest);
  - Rust: `cargo test` for the engine-discovery function;
  - by hand with computer control: launch the app, first-run browser download, tray, bar,
    notification, badge.

---

## Part 2 · Living critters, sound and motion (UI)

### Critter rig

`critter.js` keeps its drawings but gains named parts:
- groups `.body`, `.eyes`, `.pupil`, `.limbs` and `.extra`;
- mood overlays `.zzz`, `.sweat`, `.sparkle`, `.star` and `.spiral`, each hidden by default.

`critter(kind, color, acc, size, mood)` sets `data-mood`. CSS draws the moods; a tiny `life.js` adds:
- **breathing:** a slow scale on `.body`;
- **blinking:** random, every 3–7 s per critter, never in sync;
- **eyes that follow the cursor:** pupils move at most 2 px toward the pointer, for critters bigger
  than 40 px on screen.

### Moods (pure function, `moodOf(bot, recent)`)

| State | Mood | Look |
|---|---|---|
| status working | focused | narrowed eyes, limbs tapping |
| status learning | curious | eyes wide, head tilt |
| open decision | waving | a limb waves |
| open problem | worried | sweat drop, brows |
| quiet hours now | asleep | eyes closed, zzz |
| new results in the last 2 min | happy | bounce + sparkles |
| skill learned in the last 5 min | proud | star, chest out |
| repaired a step in the last 2 min | dizzy | spiral eyes, one wobble |
| otherwise | calm | breathing, blinking |

**Engine change:** every `store.event()` is also published on the bus as `event`
(`{bot, kind, text}`), so moods and sounds react live. The kinds are `learned`, `replay`, `fixed`,
`problem`, `denied`, `delegate` and `moved`. New results publish as `results` with `{bot, new}`.

### Sound

`sound.js` synthesizes sounds with Web Audio; there are no files. Each bot has a "voice": a pitch
and timbre derived from its kind and color, so every bot sounds a little different.

| Event | Sound |
|---|---|
| new result | plip |
| needs you | two soft knocks |
| run done | chime |
| learned | rising three notes |

Settings add **Sounds on/off** (default on). Sounds are silent in quiet hours. Reduce-motion
affects only animation, not sound.

### Motion

- **Typing bubble:** three dots next to the critter while a chat reply is pending.
- **Confetti:** a small canvas burst of about 40 particles on milestones (Part 3).
- **Page transitions:** CSS View Transitions where the webview supports them.
- **Reduced motion:** all of the above turn off with `prefers-reduced-motion`.

### Tests

`node --test` (built in, no packages) runs `ui/life.test.mjs`. It covers `moodOf` for every row of
the table, the blink scheduler (it never syncs two critters), and the mapping from bot to sound
voice (stable per bot).

---

## Part 3 · Mind: character and voice, proactive and aware, growth

### Persona (stored on the bot)

```json
"persona": {"chatty": 0.6, "playful": 0.7, "emoji": true,
            "catchphrase": "Inked and on it!", "quirk": "makes gentle ink puns",
            "bio": "I hunt flats in Bari so you don't have to."}
```

- **Drafted by the model** together with the bot (`DRAFT_SYSTEM` gains a `persona` field), with
  defaults per critter kind:
  - octopus: multitasking, ink puns;
  - cat: a little aloof, naps between runs;
  - blob: bubbly, squishy optimism.
- **Editable** in Make it yours, under a new Personality section with two sliders, the emoji
  toggle, the catchphrase, the quirk and the bio.
- **The chat prompt** gains:
  - the persona;
  - your name (Settings: "What should bots call you?");
  - the local time of day;
  - the last 3 days of the bot's notable events, so it can say "like on Tuesday";
  - "if you got something wrong, say so plainly and say what you'll do differently".
- **The safety note** is in the prompt too, and approval text is never generated by the model.

### Insights (`inky/insights.py`, pure Python, no AI)

- **Recap since a time:** runs, results, new results, needs and fixes, per bot.
  `GET /api/recap?since=` feeds a "While you were away" card on the home screen when the app was
  away for more than 2 h.
- **Trends:** the week-over-week change of a numeric field's median (price, size), when there are at
  least 10 results in each week.
- **Near-misses:** items that failed exactly one numeric filter by 5% or less. These become a
  **suggestion** ("4 flats just over budget: raise to 155k?").
- **Morning paper:** at the bot's `summary_at` time (default 08:00), or the first time the app opens
  after quiet hours. It combines the recap, the trend and one suggestion, in the persona's voice
  (a template, with one optional model polish per day).

**Suggestion chips** are messages carrying `actions: [{"label": "Raise to 155k", "apply": {…}}]`, where
`apply` is exactly one of `{"filters": [...]}`, `{"schedule": {...}}` or `{"look": {...}}`. A tap
calls `POST /api/bots/:id/apply`, which accepts only those three keys, all of them **reversible
settings changes**. Anything irreversible is never a chip.

**Rate limit:** `insights` posts at most one unprompted message per bot per day. It never posts in
quiet hours, and it never posts while the bot has an open need.

### Growth

- **Stats:**
  - days on the job;
  - streak (consecutive days with a successful run);
  - runs;
  - AI calls saved (steps × runs − AI calls);
  - hours saved (runs × steps × 20 s, shown as an estimate).
- **Levels** by runs: 10, 50, 100 and 500. Each unlocks an accessory: scarf, party hat, star badge,
  crown. These are new drawings in `critter.js`. Reaching a level fires the proud mood, confetti
  and a one-line message.
- **Diary:** one entry per bot per day, in the persona's voice, from the day's events. It is a
  template, with one optional model polish per day, and it appears on a new **Diary** tab on the
  bot page.
- **About you:** the bot's memory list becomes its own tab ("Things I know about you"), with edit
  and forget.

### Tests

unittest covers insights (trends, near-misses, recap windows, rate limit and quiet hours), growth
stats and levels, and the persona prompt (including that safety text is present and approval
wording is unchanged).

---

## Part 4 · World: team life and rituals

### Team life

- **The chat prompt lists the other bots** (name, job, one-line status).
- **New action** `{"type":"ask_bot","bot":"<name>","text":"…"}`: it posts into the other bot's chat
  as "Bari Flats: …" and runs that bot's chat turn.
  - **Loop guard:** at most 3 hops per bot pair per hour, and a bot never asks itself.
  - **Safety:** any irreversible step that follows goes through the normal Needs-you gate.
- **Team room:** a `#/team` page with a merged feed of bot-to-bot messages, hand-offs, milestones
  and each bot's morning paper.
- **Office view:** a toggle on the bots home, Cards or Office. In Office, each critter sits at a
  desk with a mini live screen and its current mood. The room dims in quiet hours, and the
  critters sleep. It is an add-on above the existing cards, which stay.

### Rituals

- **Hatch:** creating a bot plays an ink splash, then the critter pops out and introduces itself in
  one line from its persona.
- **Good morning / good night:** the good-morning note is the morning paper. The good-night note is
  one line at quiet-hours start with today's count, posted only if the bot ran today.
- **First-run tour:** after setup, four coach marks: your bot, its computer, Needs you, and the
  ⌥Space bar. It can be skipped and never shows again.
- **Goodbye:** deleting a bot plays a short farewell ("Flat Checker packed its tentacles") before
  the existing confirm-and-delete. The delete behaviour itself is unchanged.

### Tests

unittest covers ask_bot (the message goes to the other bot, the loop guard, no self-ask, and an
irreversible follow-up still asks), the good-night rule, and the Team feed endpoint. By hand with
computer control: the hatch, the tour, the office view and the goodbye.

---

## Out of scope

- In-character error and empty-state copy (not chosen).
- Approve/Deny inside desktop notifications (not possible with Tauri on desktop).
- App-store signing and notarization (needs the user's developer accounts).
- A mobile app (the phone uses the web app and pairing code, as today).
