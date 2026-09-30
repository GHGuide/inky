# Inky app and personality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Inky into a Tauri desktop app for Mac, Windows and Linux, and give its bots personality: living critters, sound, persona, insights, growth, team life, native presence and rituals.

**Architecture:** Personality lives in three places:
- the engine: `insights.py` and `growth.py`, both pure Python, plus persona in the chat prompt, new actions and scheduler hooks;
- the web UI: `life.js` (moods, blinking, eyes), `sound.js` (Web Audio), and new views and tabs added to v2;
- a Tauri 2 shell in `desktop/` that runs a PyInstaller build of the engine as a sidecar and adds the tray, badge, shortcuts, bar, buddy and notifications.

**Tech Stack:** Python 3.12 stdlib + Playwright + httpx; vanilla JS UI; `node --test` for UI logic; Tauri 2 (Rust) + plugins shell/notification/global-shortcut/autostart; PyInstaller (build only).

**Spec:** `docs/superpowers/specs/2026-09-30-inky-app-and-personality-design.md`

**Build order (disk: 2.6 GB free):** Part 2 → Part 3 → Part 4 → Part 1. Part 1 needs ~6 GB free for the Rust target dir.

## Global Constraints

- No new runtime Python packages; build-time only: PyInstaller, `@tauri-apps/cli`, Tauri crates.
- The UI stays v2 (Geist, critters, pills, tabs); new things are add-ons, never a redesign.
- A persona never rewrites approval, safety or problem wording, and never skips an ask-first step. Bot-to-bot hand-offs go through the same gate.
- At most one unprompted note per bot per day, never in quiet hours, and never while the bot has an open need.
- The model polishes at most once per bot per day (diary, morning paper), and only when a chat model is set.
- Sounds are silent in quiet hours and when off in Settings. `prefers-reduced-motion` turns off animation only.
- Run the tests with: `.venv/bin/python -m unittest discover -s tests -t .` and `node --test inky/ui/`.

---

## Part 2 · Living critters, sound and motion

### Task 1: Engine publishes live events

**Files:**
- Modify: `inky/store.py` (the `event` method), `inky/bots.py` (`Engine.__init__`, `_replay`)
- Test: `tests/test_engine.py` (new test in `EngineTest`)

**Interfaces:**
- Produces: bus messages `{"kind": "event", "bot": id, "ev": "<event kind>", "text": str}` for every `store.event`, and `{"kind": "results", "bot": id, "new": int}` after each replay.

- [ ] **Step 1: Write the failing test**

```python
    def test_0_events_are_published_live(self):
        E = self.E
        q = E.bus.subscribe()
        E.store.event(self.bot_id, "learned", "Learned something")
        msgs = []
        while not q.empty():
            msgs.append(q.get_nowait())
        E.bus.unsubscribe(q)
        self.assertIn({"kind": "event", "bot": self.bot_id, "ev": "learned", "text": "Learned something"}, msgs)
```

- [ ] **Step 2: Run it and check that it fails:** `.venv/bin/python -m unittest tests.test_engine.EngineTest.test_0_events_are_published_live`. Expected: AssertionError (nothing published).
- [ ] **Step 3: Implement.** In `Store.__init__` set `self.on_event = None`, and in `Store.event`:

```python
    def event(self, bot_id, kind, text, **meta):
        i = self.insert("events", dict(kind=kind, text=text, **meta), bot_id=bot_id, status=kind)
        if self.on_event:
            self.on_event(bot_id, kind, text)
        return i
```

In `Engine.__init__`, after `self.bus = Bus()`, add
`self.store.on_event = lambda bid, kind, text: self.bus.publish("event", bot=bid, ev=kind, text=text)`.
In `_replay`, after the `new` list is built, add `self.bus.publish("results", bot=bid, new=len(new))`.
- [ ] **Step 4: Run the whole suite:** expect 21 tests OK.
- [ ] **Step 5: Commit:** "Engine publishes store events and new results live".

### Task 2: Critter rig, moods and life.js

**Files:**
- Modify: `inky/ui/critter.js` (named parts, mood overlays, the `mood` argument)
- Create: `inky/ui/life.js` (moodOf, blink scheduler, eye tracking, the RECENT tracker)
- Create: `inky/ui/life.test.mjs`
- Modify: `inky/ui/app.css` (mood and breathing animations), `inky/ui/index.html` (load life.js), `inky/ui/app.js` (feed SSE into RECENT, `botCritter` passes the mood)

**Interfaces:**
- Produces:
  - `critter(kind, color, acc, size, mood = "calm")` returns an SVG string with `data-mood` and the parts `.body .eyes .pupil .limbs .extra .zzz .sweat .sparkle .star .spiral`.
  - `moodOf(bot, recent, now = Date.now())` returns one of `focused|curious|waving|worried|asleep|happy|proud|dizzy|calm`.
  - `recent[botId] = {results: ms, learned: ms, fixed: ms}`.
  - `inQuiet(schedule, date)` returns a bool.
  - `blinkDelay(seed, n)` returns ms in 3000..7000.
  - `LIFE.start()` starts blinking and the cursor-following eyes for every `.critter` on the page.

- [ ] **Step 1: Write the failing test** `inky/ui/life.test.mjs`:

```js
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const { moodOf, inQuiet, blinkDelay } = createRequire(import.meta.url)("./life.js");
const now = new Date(2026, 8, 30, 12, 0).getTime();
const bot = (o) => ({ id: 1, status: "idle", needs: 0, schedule: { quiet_from: "23:00", quiet_to: "07:00" }, ...o });
test("state moods", () => {
  assert.equal(moodOf(bot({ status: "working" }), {}, now), "focused");
  assert.equal(moodOf(bot({ status: "learning" }), {}, now), "curious");
  assert.equal(moodOf(bot({ status: "needs_you", need_kind: "decision" }), {}, now), "waving");
  assert.equal(moodOf(bot({ status: "needs_you", need_kind: "problem" }), {}, now), "worried");
  assert.equal(moodOf(bot({}), {}, now), "calm");
});
test("recent events", () => {
  assert.equal(moodOf(bot({}), { 1: { results: now - 60e3 } }, now), "happy");
  assert.equal(moodOf(bot({}), { 1: { results: now - 180e3 } }, now), "calm");
  assert.equal(moodOf(bot({}), { 1: { learned: now - 240e3 } }, now), "proud");
  assert.equal(moodOf(bot({}), { 1: { fixed: now - 60e3 } }, now), "dizzy");
});
test("quiet hours: asleep unless it needs you", () => {
  const late = new Date(2026, 8, 30, 23, 30).getTime();
  assert.equal(moodOf(bot({}), {}, late), "asleep");
  assert.equal(moodOf(bot({ status: "needs_you", need_kind: "decision" }), {}, late), "waving");
  assert.equal(inQuiet({ quiet_from: "23:00", quiet_to: "07:00" }, new Date(2026, 8, 30, 6, 59)), true);
  assert.equal(inQuiet({ quiet_from: "23:00", quiet_to: "07:00" }, new Date(2026, 8, 30, 7, 0)), false);
  assert.equal(inQuiet({}, new Date(2026, 8, 30, 3, 0)), false);
});
test("blinks never sync", () => {
  const a = [0, 1, 2, 3].map((n) => blinkDelay(1, n)), b = [0, 1, 2, 3].map((n) => blinkDelay(2, n));
  a.concat(b).forEach((d) => assert.ok(d >= 3000 && d <= 7000));
  assert.notDeepEqual(a, b);
});
```

- [ ] **Step 2: Run** `node --test inky/ui/`. Expected: it fails because `./life.js` can't be found.
- [ ] **Step 3: Implement `life.js`.** It is a UMD-style file: in the browser it sets `window.LIFE` and globals; in Node it sets `module.exports`.
  - `moodOf` takes priorities in this order: `needs_you` (decision → waving, otherwise worried), working → focused, learning → curious, quiet hours → asleep, then recent `fixed` < 2 min → dizzy, `results` < 2 min → happy, `learned` < 5 min → proud, otherwise calm.
  - The bot view needs a `need_kind` field: `bots.py bot_view` adds `"need_kind": needs[0]["kind"] if needs else None`, and `decision` for kind `decision`.
  - `blinkDelay(seed, n)` = `3000 + ((seed * 9301 + n * 49297) % 233280) / 233280 * 4000`.
  - `LIFE.start()` does two things. A single `setTimeout` loop per critter element (keyed by `data-seed`) adds the class `blink` for 140 ms. A `pointermove` listener, throttled to one animation frame, translates each `.pupil` group of critters wider than 40 px by at most 2 px toward the pointer.
- [ ] **Step 4: Change `critter.js`.** Wrap each kind's eye shapes in `<g class="eyes"><g class="pupil">…</g></g>`, the body in `<g class="body">`, and legs/arms/tentacles in `<g class="limbs">`. Append the overlays: `<g class="zzz"><text …>z</text><text …>z</text></g>`, `<path class="sweat" …/>`, `<g class="sparkle">` (3 four-point stars), `<path class="star" …/>`, and `<g class="spiral">` (two spirals over the eyes). Add a `mood` parameter that writes `data-mood="${mood}" data-seed="${seed}"` on the `<svg>`. The seed comes from a hash of color+kind+size.
- [ ] **Step 5: Add the CSS in `app.css`.**

```css
.critter .zzz,.critter .sweat,.critter .sparkle,.critter .star,.critter .spiral{opacity:0;transition:opacity .3s}
.critter .body{transform-origin:60px 110px;animation:breathe 3.6s ease-in-out infinite}
.critter.blink .eyes{transform:scaleY(.1);transform-origin:60px 54px}
.critter .eyes{transition:transform .08s}
.critter[data-mood=focused] .eyes{transform:scaleY(.6);transform-origin:60px 54px}
.critter[data-mood=focused] .limbs{animation:tap .5s ease-in-out infinite}
.critter[data-mood=curious]{animation:tilt 2.4s ease-in-out infinite}
.critter[data-mood=waving] .limbs{animation:wave 1s ease-in-out infinite;transform-origin:60px 80px}
.critter[data-mood=worried] .sweat{opacity:1;animation:drip 1.6s ease-in infinite}
.critter[data-mood=asleep] .eyes{transform:scaleY(.08);transform-origin:60px 54px}.critter[data-mood=asleep] .zzz{opacity:1;animation:float 3s ease-in-out infinite}
.critter[data-mood=happy]{animation:hop .6s ease-out 3}.critter[data-mood=happy] .sparkle{opacity:1;animation:twinkle 1s ease-in-out infinite}
.critter[data-mood=proud] .star{opacity:1}.critter[data-mood=proud] .body{animation:puff 2s ease-in-out infinite}
.critter[data-mood=dizzy] .pupil{opacity:0}.critter[data-mood=dizzy] .spiral{opacity:1;animation:spin 1.2s linear infinite;transform-origin:60px 54px}
@keyframes breathe{50%{transform:scaleY(1.025) scaleX(.99)}}
@keyframes tap{50%{transform:translateY(2px)}}
@keyframes tilt{50%{transform:rotate(-6deg)}}
@keyframes wave{0%,100%{transform:rotate(0)}50%{transform:rotate(-12deg)}}
@keyframes drip{0%{transform:translateY(0);opacity:1}100%{transform:translateY(8px);opacity:0}}
@keyframes float{50%{transform:translateY(-4px)}}
@keyframes hop{30%{transform:translateY(-10%)}60%{transform:translateY(0)}}
@keyframes twinkle{50%{opacity:.3}}
@keyframes puff{50%{transform:scale(1.04)}}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.critter,.critter *{animation:none!important;transition:none!important}}
```

- [ ] **Step 6: Wire it up.**
  - `app.js`: `const RECENT = {}`. In the SSE `onmessage`: `results` with `new > 0` sets `RECENT[m.bot].results = Date.now()`, an `event` with `ev === "learned"` sets `.learned`, and `ev === "fixed"` sets `.fixed`.
  - `critter.js`: `botCritter` becomes `(b, size) => critter(k, c, a, size, window.moodOf ? moodOf(b, RECENT) : "calm")`.
  - `index.html`: load `life.js` before `app.js`.
  - Call `LIFE.start()` once on load.
  - A 30 s interval calls `renderNav()` and `S.view.refresh` only if a mood changed, so decayed moods return to calm.
- [ ] **Step 7:** Run `node --test inky/ui/` (all pass) and the Python suite. Check by eye in the browser pane: Flat Checker idle is calm and blinking, Robot Test (problem) is worried, and a bot during Run now is focused.
- [ ] **Step 8: Commit:** "Living critters: breathing, blinking, eyes that follow you, moods from state".

### Task 3: Sound

**Files:**
- Create: `inky/ui/sound.js`
- Modify: `inky/ui/life.test.mjs` (voice tests), `inky/ui/app.js` (play on events), `inky/ui/views.js` (Settings toggle), `inky/ui/index.html`

**Interfaces:**
- Produces: `voiceOf(bot)` returns `{base: Hz, wave: "sine"|"triangle"}`, stable per bot. `SOUND.play(name, bot)` for `name ∈ plip|knock|chime|rise`. `SOUND.allowed(bot)` returns false when the setting `sounds === false` or the bot is in quiet hours.

- [ ] **Step 1: Add the tests** to `life.test.mjs`:

```js
const { voiceOf } = createRequire(import.meta.url)("./sound.js");
test("each bot has a stable voice", () => {
  const a = { id: 1, look: { kind: "octopus", color: "#E9A23B" } }, b = { id: 2, look: { kind: "cat", color: "#7C6CF2" } };
  assert.deepEqual(voiceOf(a), voiceOf({ ...a }));
  assert.notEqual(voiceOf(a).base, voiceOf(b).base);
  assert.ok(voiceOf(a).base >= 330 && voiceOf(a).base <= 880);
});
```

- [ ] **Step 2: Run it and check that it fails** (module not found).
- [ ] **Step 3: Implement `sound.js`.**
  - `voiceOf` maps the kind to a wave (octopus sine, cat triangle, blob sine) and hashes the color to a base between 330 and 880 Hz.
  - `SOUND.play` creates a lazily shared `AudioContext` and schedules a short envelope per sound:
    - plip: one 90 ms note at base×2;
    - knock: two 60 ms low notes at base/2, 140 ms apart;
    - chime: base then base×1.5, 180 ms each;
    - rise: base, ×1.25, ×1.5.
  - Gain is 0.08.
- [ ] **Step 4: Hook it up in `app.js`.**
  - SSE `results` with new > 0 → `plip`.
  - `needs` → `knock`, only when the needs count went up.
  - `event` with `ev === "replay"` and text matching `/results, .* new$|^Done in/` → `chime`.
  - `event` with `ev === "learned"` → `rise`.
  - Every play is guarded by `SOUND.allowed(bot)`.
- [ ] **Step 5: Settings.** Add a toggle "Sounds" under Notifications. The key `sounds` defaults to true in `settings_view`.
- [ ] **Step 6: Run the tests, then commit:** "Each bot has its own little sounds".

### Task 4: Motion (typing bubble, confetti, transitions)

**Files:** Modify `inky/ui/views.js` (the bot page `send`, `drawMsgs`), `inky/ui/app.js` (`confetti()`, view transitions in `route`), `inky/ui/app.css`

**Interfaces:** Produces the global `confetti(x = innerWidth / 2, y = innerHeight / 3)`, a no-op under reduced motion.

- [ ] **Step 1: Typing bubble.** In `VIEWS.bot`, while a chat post is pending, set `this.typing = true` and have `drawMsgs` append `<div class="m">${botCritter(b,26)}<div class="body typing"><i></i><i></i><i></i></div></div>`. Clear it when the reply arrives. CSS: `.typing i{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--faint);margin:0 2px;animation:dots 1.2s infinite}.typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}@keyframes dots{30%{transform:translateY(-4px);opacity:1}0%,60%,100%{opacity:.4}}`.
- [ ] **Step 2: Confetti.** A canvas overlay with 40 particles, 1.4 s, removed afterwards. It uses the coral, honey, sea and grape colors.
- [ ] **Step 3: View transitions.** In `route()`, if `document.startViewTransition` exists and motion isn't reduced, wrap the `replaceWith` + `show` in it.
- [ ] **Step 4: Check by eye:** send a chat and the dots appear; `confetti()` from the console bursts once. Commit: "Motion: typing bubble, confetti, page transitions".

---

## Part 3 · Mind

### Task 5: Persona and a warmer chat

**Files:**
- Create: `inky/persona.py`
- Modify: `inky/bots.py` (the `DRAFT_SYSTEM` persona field, `create_bot`, `update_bot` allowing `persona`, `chat` using `persona.prompt_lines`), `inky/server.py` (`settings_view` adds `user_name`)
- Modify: `inky/ui/views.js` (a Personality section in Make it yours; Settings "What should bots call you?")
- Test: `tests/test_persona.py`

**Interfaces:**
- Produces:
  - `persona.DEFAULTS[kind]` is a dict.
  - `persona.normalize(p, kind)` returns a full persona.
  - `persona.prompt_lines(bot, user_name, now: datetime, events: list[dict])` returns a str appended to `CHAT_SYSTEM`.
  - `persona.SAFETY` is a str.

- [ ] **Step 1: Write the failing test** `tests/test_persona.py`:

```python
import unittest
from datetime import datetime
from inky import persona


class PersonaTest(unittest.TestCase):
    def test_defaults_by_kind(self):
        p = persona.normalize({}, "octopus")
        self.assertIn("ink", p["quirk"])
        self.assertTrue(0 <= p["chatty"] <= 1 and 0 <= p["playful"] <= 1)
        self.assertEqual(persona.normalize({"chatty": 5}, "cat")["chatty"], 1.0)

    def test_prompt_has_name_time_memory_and_safety(self):
        bot = {"name": "Bari Flats", "look": {"kind": "octopus"}, "persona": {"catchphrase": "Inked and on it!"}}
        ev = [{"ts": datetime(2026, 9, 29, 10).timestamp(), "text": "14 results, 12 pass your rules, 2 new"}]
        s = persona.prompt_lines(bot, "Leo", datetime(2026, 9, 30, 8, 15), ev)
        self.assertIn("Leo", s)
        self.assertIn("morning", s)
        self.assertIn("Tue", s)
        self.assertIn("Inked and on it!", s)
        self.assertIn(persona.SAFETY, s)

    def test_no_name_no_problem(self):
        s = persona.prompt_lines({"name": "X", "look": {"kind": "blob"}}, "", datetime(2026, 9, 30, 22), [])
        self.assertNotIn("call the user", s)
        self.assertIn("night", s)
```

- [ ] **Step 2: Run it and check that it fails** (no module `inky.persona`).
- [ ] **Step 3: Implement `persona.py`.**

```python
"""A bot's character: traits, a catchphrase and a quirk. Never touches safety wording."""
from datetime import datetime

DEFAULTS = {
    "octopus": {"chatty": 0.6, "playful": 0.7, "emoji": True, "catchphrase": "Inked and on it!",
                "quirk": "juggles many things at once and makes the odd gentle ink pun", "bio": ""},
    "cat": {"chatty": 0.35, "playful": 0.5, "emoji": False, "catchphrase": "Consider it handled.",
            "quirk": "a little aloof, likes naps between runs, secretly proud of good work", "bio": ""},
    "blob": {"chatty": 0.7, "playful": 0.8, "emoji": True, "catchphrase": "Squish squish, on it!",
             "quirk": "bubbly and endlessly optimistic, bounces back from every problem", "bio": ""},
}
SAFETY = ("Your personality never changes your rules: you still ask before anything irreversible, "
          "never type passwords, never solve robot checks, and you never pretend something happened.")


def normalize(p, kind):
    base = dict(DEFAULTS.get(kind) or DEFAULTS["octopus"])
    base.update({k: v for k, v in (p or {}).items() if v is not None})
    for k in ("chatty", "playful"):
        base[k] = min(1.0, max(0.0, float(base[k])))
    base["emoji"] = bool(base["emoji"])
    return base


def part_of_day(h):
    return "morning" if 5 <= h < 12 else "afternoon" if h < 17 else "evening" if h < 22 else "night"


def prompt_lines(bot, user_name, now, events):
    p = normalize(bot.get("persona"), (bot.get("look") or {}).get("kind", "octopus"))
    talk = "chatty and warm" if p["chatty"] > 0.6 else "brief" if p["chatty"] < 0.4 else "friendly and to the point"
    mood = "playful" if p["playful"] > 0.6 else "calm and serious" if p["playful"] < 0.4 else "light"
    lines = [f"YOUR CHARACTER: {talk}, {mood}. Quirk: {p['quirk']}. Catchphrase (use rarely): \"{p['catchphrase']}\"."
             + (f" About you: {p['bio']}." if p.get("bio") else "") + (" Emoji are fine, at most one." if p["emoji"] else " No emoji.")]
    if user_name:
        lines.append(f"You call the user {user_name}.")
    lines.append(f"It is {part_of_day(now.hour)} ({now.strftime('%a %H:%M')}).")
    if events:
        lines.append("RECENTLY: " + "; ".join(f"{datetime.fromtimestamp(e['ts']).strftime('%a')}: {e['text']}" for e in events[-6:]))
    lines.append("If you got something wrong, say so plainly and say what you'll do differently.")
    lines.append(SAFETY)
    return "\n".join(lines)
```

- [ ] **Step 4: Wire it into `bots.py`.**
  - `DRAFT_SYSTEM` gains `"persona": {"chatty": 0-1, "playful": 0-1, "emoji": true|false, "catchphrase": "<short>", "quirk": "<one line>", "bio": "<one line in first person>"}`.
  - `create_bot` stores `persona.normalize(d.get("persona"), look["kind"])`.
  - `update_bot` allows `persona` and merges it the same way as `look`.
  - In `chat`, `sys += "\n" + persona.prompt_lines(b, S.user_name, datetime.now(), notable)`, where `notable` is the bot's events from the last 3 days with kinds in `("replay","learned","fixed","problem","level")`, and `S.user_name` comes from `store.setting("app", {}).get("user_name", "")`.
  - `bot_view` includes `persona`.
- [ ] **Step 5: UI.**
  - **Make it yours** gains a "Personality" column: a Chatty ↔ Quiet slider (`chatty`, 0..1 step .1), a Playful ↔ Serious slider (`playful`), an Emoji chip toggle, and Catchphrase, Quirk and "In its own words" (bio) inputs. They go into `this.draft.persona` and are saved with the existing Save button (`patch({name, look, persona})`).
  - **Settings** gains the field "What should bots call you?" (`user_name`) under About.
- [ ] **Step 6: Run the tests** (all pass). Then a live check in chat with the real model: set the name "Leo" and ask Flat Checker "good morning". The reply should use the name and the time of day, and the approval cards stay unchanged. Commit: "Persona: each bot has a character, knows your name and the time, owns mistakes".

### Task 6: Insights (recap, trends, near-misses, morning paper) and suggestion chips

**Files:**
- Create: `inky/insights.py`, `tests/test_insights.py`
- Modify:
  - `inky/bots.py`: `tick` calls `morning_paper` instead of `summary`, `_replay` calls `maybe_suggest`, `apply_chip`;
  - `inky/server.py`: `GET /api/recap`, `POST /api/bots/:id/apply`;
  - `inky/ui/views.js`: recap card on the bots home, chips in `drawMsgs`;
  - `inky/ui/app.js`: `lastSeen` tracking.

**Interfaces:**
- Produces:
  - `insights.recap(store, since: float, bot_id=None)` returns `[{bot, name, runs, results, new, needs, fixed}]`.
  - `insights.trend(results, field, now)` returns `{"field", "from", "to", "pct"}` or None.
  - `insights.near_misses(results, filters, margin=0.05)` returns `{"filter": f, "items": [...], "suggest": value}` or None.
  - `insights.may_post(store, bot, now)` returns a bool.
  - `insights.morning_paper(store, bot, now)` returns `{"text", "chips"}`.
  - Chips are shaped like `{"label": str, "apply": {"filters": [...]}}`.
  - `Engine.apply_chip(bid, apply: dict)` accepts only the keys `filters|schedule|look`.

- [ ] **Step 1: Write the failing tests** `tests/test_insights.py`:

```python
import time
import unittest
from datetime import datetime
from inky import insights
from inky.store import Store


def R(price, ts, **kw):
    return {"price": f"€ {price:,}".replace(",", "."), "ts": ts, **kw}


class InsightsTest(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.bid = self.s.insert("bots", {"name": "Bari Flats", "schedule": {"quiet_from": "23:00", "quiet_to": "07:00"}}, status="idle")
        self.now = datetime(2026, 9, 30, 9, 0).timestamp()

    def test_trend_needs_ten_each_week(self):
        wk = 7 * 86400
        old = [R(100000 + i * 1000, self.now - wk - 3600 * i) for i in range(10)]
        new = [R(94000 + i * 1000, self.now - 3600 * i) for i in range(10)]
        t = insights.trend(old + new, "price", self.now)
        self.assertEqual(t["field"], "price")
        self.assertLess(t["pct"], -5)
        self.assertIsNone(insights.trend(new, "price", self.now))

    def test_near_miss_suggests_a_rounded_new_limit(self):
        f = [{"field": "price", "op": "<=", "value": 150000, "text": "under 150k"}]
        items = [R(152000, self.now), R(155000, self.now), R(190000, self.now), R(120000, self.now)]
        nm = insights.near_misses(items, f)
        self.assertEqual(len(nm["items"]), 2)
        self.assertEqual(nm["suggest"], 155000)

    def test_rate_limit_quiet_hours_and_open_needs(self):
        b = self.s.get("bots", self.bid)
        self.assertTrue(insights.may_post(self.s, b, self.now))
        self.s.message(self.bid, "bot", "note", unprompted=True)
        self.assertFalse(insights.may_post(self.s, b, self.now + 60))
        self.assertFalse(insights.may_post(self.s, b, datetime(2026, 10, 1, 23, 30).timestamp()))
        self.s.insert("needs", {"kind": "decision"}, bot_id=self.bid, status="open")
        self.assertFalse(insights.may_post(self.s, b, datetime(2026, 10, 2, 10).timestamp()))

    def test_recap_counts_since(self):
        self.s.insert("runs", {"kind": "replay", "items": 14, "new": 2}, bot_id=self.bid, status="ok")
        r = insights.recap(self.s, time.time() - 60)
        self.assertEqual((r[0]["runs"], r[0]["results"], r[0]["new"]), (1, 14, 2))

    def test_morning_paper_has_text_and_a_chip(self):
        b = self.s.get("bots", self.bid)
        b["filters"] = [{"field": "price", "op": "<=", "value": 150000, "text": "under 150k"}]
        for p in (152000, 154000):
            self.s.upsert_key("results", self.bid, f"k{p}", R(p, self.now, title="flat", passed=False))
        paper = insights.morning_paper(self.s, b, self.now)
        self.assertIn("Good morning", paper["text"])
        self.assertEqual(paper["chips"][0]["apply"]["filters"][0]["value"], 155000)
```

- [ ] **Step 2: Run it and check that it fails** (module not found).
- [ ] **Step 3: Implement `insights.py`**, pure Python with `from inky.skills import parse_num, keep` and `from inky.bots import quiet`. To avoid a circular import, move `quiet` into `insights.py` and import it into `bots.py`.
  - `trend` takes the median of `parse_num(r[field])` for results with `ts` in [now−7d, now] versus [now−14d, now−7d], and needs ≥10 in each.
  - `near_misses` handles each numeric filter with op `<=`/`<` (and `>=`/`>` mirrored). An item misses when its value is in (limit, limit×(1+margin)] and it passes all the other filters. The suggestion is the max missing value, rounded up to a "nice" step (the step is 5000 if the limit ≥ 50000, 500 if ≥ 5000, else 5).
  - `may_post` is: not quiet now, no open needs, and no message with `unprompted=True` in the last 20 h.
  - `morning_paper` is a template: "Good morning! Since yesterday: {runs} runs, {new} new." plus the trend sentence if one exists, plus a near-miss sentence with a chip `{"label": f"Raise to {fmt(v)}", "apply": {"filters": [...updated]}}`.
  - Results need `passed=False` saved for items filtered out. In `_replay`, also upsert the failing items with `passed: False, new: False` so near-misses have data. The UI results table shows only `passed != False`.
- [ ] **Step 4: Engine hooks.**
  - In `tick`, when `summary_at == hm`, replace `self.summary(bid)` with `self.post_paper(bid)`. `post_paper` builds the paper, stores the message with `chips=paper["chips"], unprompted=True, paper=True`, and notifies.
  - At the end of `_replay`, if there are no new items, `near_misses` is not None, and `may_post` is true, post one suggestion message with chips and `unprompted=True`.
  - `apply_chip(bid, apply)`: `assert set(apply) <= {"filters", "schedule", "look"} and len(apply) == 1`. It updates via `update_bot` and returns the bot view. Filter changes also rewrite the matching `rules` text.
- [ ] **Step 5: Server.**
  - `GET /api/recap?since=<ts>` returns `{"recap": insights.recap(E.store, float(since))}`.
  - `POST /api/bots/(\d+)/apply` with body `{"apply": {...}}` returns `{"bot": E.apply_chip(...)}`, and 400 for other keys.
- [ ] **Step 6: UI.**
  - `app.js` keeps `localStorage.inkyLastSeen`, updated on `visibilitychange` to hidden and on `pagehide`.
  - On load, if away for more than 2 h, fetch the recap and show a card above "Your bots": "While you were away" with one line per bot that has `runs > 0` or `needs > 0`, each with its critter in its current mood, and a Dismiss button.
  - `drawMsgs` renders `m.chips` as `.btn s` buttons. A click POSTs apply, and then the chip turns into "● done".
- [ ] **Step 7: Run the tests, plus a live check:** set Bari Flats' filter to 60000, run it, and see the near-miss suggestion chip; tap it and the filter updates. Commit: "Insights: recap, trends, near-miss suggestions with one-tap chips, morning paper".

### Task 7: Growth (stats, levels, accessories, diary, About you)

**Files:**
- Create: `inky/growth.py`, `tests/test_growth.py`
- Modify:
  - `inky/bots.py`: `_finish` checks for a level-up, and `tick` writes the diary at `quiet_from`;
  - `inky/server.py`: `GET /api/bots/:id` adds `growth` and `diary`;
  - `inky/ui/critter.js`: accessories `scarf`, `party`, `star`, `crown`;
  - `inky/ui/views.js`: Diary and About you tabs, locked accessories in Make it yours, stats on Diary;
  - `inky/ui/app.js`: confetti on a `level` event.

**Interfaces:**
- Produces:
  - `growth.LEVELS = [(10, "scarf"), (50, "party"), (100, "star"), (500, "crown")]`.
  - `growth.stats(bot, runs: list, skills: list, now)` returns `{days, streak, runs, ai_saved, hours_saved, level, unlocked: [acc], next: {at, acc} | None}`.
  - `growth.level_up(before_runs, after_runs)` returns an acc name or None.
  - `growth.diary_entry(bot, events_today: list, runs_today: list)` returns a str.
  - The engine stores the diary in the table `diary` (bot_id, key = YYYY-MM-DD, data {text}).

- [ ] **Step 1: Write the failing tests** `tests/test_growth.py`:

```python
import unittest
from datetime import datetime, timedelta
from inky import growth


def run(day, ok=True, ai=0, steps=4):
    return {"ts": day.timestamp(), "status": "ok" if ok else "problem", "kind": "replay", "ai_calls": ai, "steps": steps}


class GrowthTest(unittest.TestCase):
    now = datetime(2026, 9, 30, 20)

    def test_streak_counts_consecutive_days_with_a_good_run(self):
        runs = [run(self.now - timedelta(days=d)) for d in (0, 1, 2, 4)]
        s = growth.stats({"created": (self.now - timedelta(days=9)).timestamp()}, runs, [{"steps": [1, 2, 3, 4]}], self.now.timestamp())
        self.assertEqual((s["days"], s["streak"], s["runs"]), (10, 3, 4))
        self.assertEqual(s["ai_saved"], 16)
        self.assertGreater(s["hours_saved"], 0)

    def test_levels_and_unlocks(self):
        runs = [run(self.now) for _ in range(52)]
        s = growth.stats({"created": self.now.timestamp()}, runs, [], self.now.timestamp())
        self.assertEqual(s["unlocked"], ["scarf", "party"])
        self.assertEqual(s["next"], {"at": 100, "acc": "star"})
        self.assertEqual(growth.level_up(9, 10), "scarf")
        self.assertIsNone(growth.level_up(10, 11))

    def test_diary_in_first_person(self):
        t = growth.diary_entry({"name": "Bari Flats", "look": {"kind": "octopus"}},
                               [{"kind": "fixed", "text": "Step 3 changed"}], [run(self.now), run(self.now)])
        self.assertIn("I ", t)
        self.assertIn("2 runs", t)
        self.assertIn("fixed", t.lower())
```

- [ ] **Step 2: Run it and check that it fails.**
- [ ] **Step 3: Implement `growth.py`.**
  - days = floor((now − created)/86400) + 1;
  - streak = consecutive local dates ending today or yesterday with ≥1 ok replay;
  - ai_saved = Σ steps per ok replay − Σ ai_calls, where steps per run comes from `run["steps"]` or else the first skill's step count;
  - hours_saved = ok runs × steps × 20 s / 3600, rounded to 0.1;
  - `unlocked` = accs whose threshold ≤ ok runs;
  - `diary_entry` is a template in the first person: "Today I did {n} runs and checked {items} results; {new} were new." plus "I fixed a step that moved." if there's a fixed event, plus "I got stuck once and asked for help." if there's a problem, plus a line picked by quirk.
- [ ] **Step 4: Engine.**
  - `_replay` stores `steps=len(skill["steps"])` on the run via `_finish`.
  - After `_finish(ok)`, compute `level_up(ok_before, ok_before + 1)`. If there's a level-up: `store.event(bid, "level", f"Reached {n} runs: unlocked {acc}")`, a bot message "🎉 {n} runs! I unlocked a {acc}.", and `bus.publish("level", bot=bid, acc=acc)`.
  - `tick` at `hm == quiet_from`: if there's no diary for today, write `diary_entry`, with one optional `llm.chat` polish when `chat` is set. The polish prompt is "Rewrite in your voice, keep all facts, ≤ 4 sentences". It falls back to the template on any error.
- [ ] **Step 5: UI.**
  - `critter.js` gets the 4 accessory drawings.
  - The `TABS` list adds `["diary", "Diary"], ["about", "About you"]`.
  - The Diary tab shows stats tiles (days, streak, hours saved, AI calls saved, level progress bar to the next accessory), then diary entries newest first.
  - The About you tab lists memory with inline edit and Forget. It's moved from the Settings tab, and Settings links to it.
  - In Make it yours, accessories not in `growth.unlocked` show a lock and "at N runs".
  - On a `level` event: `confetti()`, the `proud` mood, and the `rise` sound.
- [ ] **Step 6: Run the tests.** Live check: make runs reach 10 (by PATCHing the run count via repeated Run now on Travel Bookwatch, which uses a real site with 0 AI). Confetti, the scarf unlocking, and the Diary tab showing stats should all happen. Commit: "Growth: streaks, hours saved, levels that unlock accessories, a daily diary, About you".

---

## Part 4 · World

### Task 8: Team life (ask_bot, loop guard, Team room)

**Files:**
- Modify:
  - `inky/bots.py`: `CHAT_SYSTEM` gets `OTHER BOTS`; action `ask_bot`; `chat(..., sender=None)`; hop guard;
  - `inky/server.py`: `GET /api/team`;
  - `inky/ui/views.js`: `VIEWS.team`, plus peer messages in `drawMsgs`;
  - `inky/ui/app.js`: a nav link "Team".
- Test: `tests/test_engine.py` (new `TeamTest` with `FakeLLM` scripted replies)

**Interfaces:**
- Produces:
  - action `{"type": "ask_bot", "bot": "<name>", "text": "…"}`;
  - `Engine.ask_bot(from_bid, to_name, text)` returns the target's reply str, or raises ValueError;
  - peer messages are stored as `role="peer", sender=<from name>, sender_id=<from id>, team=True`;
  - `GET /api/team?limit=` returns `{"feed": [...]}` from messages with `team=True` or `paper=True`, and events of kind `level`.

- [ ] **Step 1: Write the failing test.**

```python
class TeamTest(unittest.TestCase):
    def setUp(self):
        self.E = make_engine()
        self.a = self.E.create_bot({"name": "Bari Flats", "job": "find flats"})["id"]
        self.b = self.E.create_bot({"name": "Flat Checker", "job": "message agencies"})["id"]

    def tearDown(self):
        self.E.close()

    def test_ask_bot_reaches_the_other_bot_and_is_guarded(self):
        E = self.E
        E.llm.script = [{"reply": "On it, I'll ask before sending.", "actions": []}] * 5
        r = E.ask_bot(self.a, "flat checker", "Found one: bari-3. Want to message the agency?")
        self.assertIn("ask before", r)
        peer = [m for m in E.store.find("messages", bot_id=self.b) if m["role"] == "peer"]
        self.assertEqual(peer[0]["sender"], "Bari Flats")
        with self.assertRaises(ValueError):
            E.ask_bot(self.a, "bari flats", "hi me")
        E.ask_bot(self.a, "Flat Checker", "2")
        E.ask_bot(self.a, "Flat Checker", "3")
        with self.assertRaises(ValueError):
            E.ask_bot(self.a, "Flat Checker", "4: too many hops")
        self.assertEqual(len(E.store.find("needs", status="open")), 0)
```

`make_engine()`'s FakeLLM must support `script`: each call pops the next dict and returns its JSON. Extend `FakeLLM` in `tests/test_engine.py` if it doesn't already.
- [ ] **Step 2: Run it and check that it fails** (no `ask_bot`).
- [ ] **Step 3: Implement.**
  - `self.hops = {}`, keyed `(from, to)` → a list of timestamps.
  - `ask_bot` resolves the target by case-insensitive name (exact, then startswith). It raises ValueError if the target isn't found, if the target is the sender, or if there are ≥3 hops for the pair in the last hour. It then records the hop and calls `self.chat(to, f"{from_name}: {text}", source=f"bot:{from}", sender=(from_id, from_name))` and returns the reply.
  - In `chat`, if `sender` is given, the stored message uses `role="peer", sender=name, sender_id=id, team=True` instead of `"you"`, and the bot's reply message gets `team=True`.
  - In the LLM history, peer messages become `{"role": "user", "content": "(from <name>) <text>"}`.
  - The `apply_action` branch `ask_bot` runs `self.ask_bot` in a thread (so a chat turn never blocks on another bot's turn) and returns `f"asked {a['bot']}"`.
  - `CHAT_SYSTEM` adds the line `OTHER BOTS: {others}` (name — job — status) and the action doc line `{{"type":"ask_bot","bot":"<name>","text":"<what you need>"}}   (ask or tell another bot; anything irreversible still needs the user's yes)`.
- [ ] **Step 4: Team room.**
  - `GET /api/team` merges and sorts by ts (desc, limit 100). Each item is `{ts, bot, name, look, kind: peer|reply|paper|level, text, sender}`.
  - `VIEWS.team` shows the feed as chat bubbles with each critter (in its mood) and "Bari Flats → Flat Checker" labels.
  - The nav link "Team" sits under Activity.
  - `drawMsgs` renders `role==="peer"` like a bot message with the sender's critter and the label `${sender}`.
- [ ] **Step 5: Run the tests.** Live check: in Bari Flats' chat, "tell Flat Checker to get ready to message the agency for bari-3". Flat Checker's chat should show the peer message and a reply, and Team should show both. Commit: "Team life: bots can talk to each other (guarded), Team room".

### Task 9: Office view

**Files:** Modify `inky/ui/views.js` (`VIEWS.bots.refresh`, a Cards/Office toggle), `inky/ui/app.css`

**Interfaces:** Consumes `moodOf`, `inQuiet`, `botCritter` and `screenUrl`.

- [ ] **Step 1: The toggle.** Add a `seg` control "Cards · Office" next to "Your bots", saved in `localStorage.inkyHome`.
- [ ] **Step 2: The office.** A `.office` grid of `.desk` tiles, each holding:
  - a 64 px critter in its mood, sitting behind a desk (a CSS rounded rect);
  - a monitor on the desk: a mini `<img>` of the live screen when working, otherwise a dark screen with the status text;
  - a name plate.
  When all bots are in quiet hours, add `.office.night` (a dim overlay and a moon icon), and their critters are asleep via `moodOf`. Clicking a desk opens the bot. The live images refresh with the existing 2.5 s timer.
- [ ] **Step 3: Check by eye** in the browser pane at desktop and mobile width (the grid wraps at 375 px). Commit: "Office view: your bots at their desks".

### Task 10: Rituals (hatch, good night, first-run tour, goodbye)

**Files:**
- Modify:
  - `inky/bots.py`: `create_bot` posts an intro message; `tick` posts good night at `quiet_from` (with the diary);
  - `inky/ui/views.js`: the new-bot flow navigates with `?hatch=1`; the bot page plays the hatch; the delete button shows a farewell; the tour after setup;
  - `inky/ui/app.css`.
- Test: `tests/test_engine.py` (intro message on create; `good_night` rule)

**Interfaces:**
- Produces: `Engine.good_night(bid, now)` returns a str, or None when the bot didn't run today.

- [ ] **Step 1: Write the failing test.**

```python
    def test_intro_and_good_night(self):
        E = make_engine()
        bid = E.create_bot({"name": "Tiny", "job": "watch a page", "look": {"kind": "blob"}})["id"]
        first = E.store.find("messages", bot_id=bid, desc=False)[0]
        self.assertIn("Tiny", first["text"])
        self.assertIsNone(E.good_night(bid, time.time()))
        E.store.insert("runs", {"kind": "replay", "items": 3, "new": 1}, bot_id=bid, status="ok")
        self.assertIn("1 new", E.good_night(bid, time.time()))
        E.close()
```

- [ ] **Step 2: Run it and check that it fails.**
- [ ] **Step 3: Implement.**
  - `create_bot` adds `store.message(bid, "bot", f"Hi! I'm {name}. {bio or summary} {catchphrase}", intro=True)`.
  - `good_night` counts today's ok replays and their new results. It returns "Good night! Today I did {runs} runs and found {new} new. Back at it in the morning." or None.
  - `tick`: at `hm == quiet_from`, once per day (the `night_day` field on the bot), post the good night if not None, mark it `unprompted=True, team=True`, and write the diary (Task 7).
- [ ] **Step 4: UI.**
  - **Hatch:** `VIEWS.new` creates the bot and goes to `#/bot/<id>/computer?hatch=1`. The bot page, if `qs.hatch`, shows a centered overlay: an ink splash (SVG circles scaling out), then the critter scales from 0 with a bounce, the intro text bubble appears, `confetti()`, and the `rise` sound. It dismisses after 2.4 s or on click.
  - **Tour:** after setup finishes (`#/setup` Ready → Start) and `!localStorage.inkyTour`, show 4 coach marks positioned at `#nav .navbot`, `.tabs a[href$=computer]`, `.needlink` and a centered "⌥Space" card. It has Next and Skip, and sets `inkyTour=1`.
  - **Goodbye:** the Delete bot… button opens a modal with the critter waving and "{name} packed its {tentacles|whiskers|goo}. Delete for good?", with Cancel and Delete. Delete plays a 600 ms shrink-and-fade on the critter, then calls the existing delete.
- [ ] **Step 5: Run the tests,** then check each ritual by eye with computer control. Commit: "Rituals: hatch, intro, good night, first-run tour, goodbye".

---

## Part 1 · The app (Tauri) and native presence

### Task 11: Engine: free port, engine.json, a browser installed on demand

**Files:**
- Modify:
  - `inky/__main__.py`: port 0 support, writing and removing `engine.json`, the frozen-app defaults;
  - `inky/server.py`: `POST /api/setup/browser`, and `GET /api/setup` adds `browser_ready`;
  - `inky/ui/views.js`: a "Getting your bots a browser…" screen when not ready.
- Test: `tests/test_engine.py` (new `EngineFileTest`)

**Interfaces:**
- Produces:
  - `inky/__main__.py: write_engine_file(home, url, pid)` and `remove_engine_file(home)`;
  - the file `~/.inky/engine.json` contains `{"url","pid","version"}`;
  - `health.browser_ready()` returns a bool;
  - `POST /api/setup/browser` starts the install in a thread and publishes `{"kind":"browser","line":str,"done":bool,"ok":bool}`.

- [ ] **Step 1: Write the failing test.**

```python
class EngineFileTest(unittest.TestCase):
    def test_port_zero_and_engine_file(self):
        import subprocess, json as j
        home = tempfile.mkdtemp()
        p = subprocess.Popen([sys.executable, "-m", "inky", "--port", "0", "--home", home, "--no-open"], stdout=subprocess.PIPE, text=True)
        try:
            url = p.stdout.readline().strip().rsplit(" ", 1)[-1]
            self.assertRegex(url, r"^http://127\.0\.0\.1:\d+$")
            info = j.load(open(os.path.join(home, "engine.json")))
            self.assertEqual((info["url"], info["pid"]), (url, p.pid))
            self.assertTrue(j.load(urllib.request.urlopen(url + "/api/ping"))["ok"])
        finally:
            p.terminate(); p.wait(10)
        self.assertFalse(os.path.exists(os.path.join(home, "engine.json")))
```

- [ ] **Step 2: Run it and check that it fails** (no engine.json).
- [ ] **Step 3: Implement.**
  - In `main()`, after `serve()`, set `port = srv.server_port` and build `url` from it, print it, and `write_engine_file(home, url, os.getpid())`.
  - In the `finally` and in the SIGTERM handler, call `remove_engine_file`.
  - If `getattr(sys, "frozen", False)`: `os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(home) / "browsers"))`.
  - `browser_ready()`: `from playwright.sync_api import sync_playwright`; `with sync_playwright() as p: return Path(p.chromium.executable_path).exists()`, returning False on any exception.
  - The install runs `[driver_node, driver_cli, "install", "chromium"]`, using `playwright._impl._driver.compute_driver_executable()` (it returns a (node, cli) tuple in Playwright 1.63), and streams its stdout lines onto the bus.
- [ ] **Step 4: UI.** On load, if `GET /api/setup` returns `browser_ready: false`, show a bare page with a critter (curious mood), "Getting your bots a browser…", a progress log of the last line, and Retry. When `done && ok`, reload.
- [ ] **Step 5: Run the tests, then commit:** "Engine: free port, engine.json for the app, browser install on demand".

### Task 12: Engine binary (PyInstaller)

**Files:** Create `desktop/scripts/build-engine.py` and `desktop/scripts/engine-entry.py`; modify `.gitignore` (`desktop/src-tauri/binaries/`, `build/`, `dist/`)

**Interfaces:** Produces `desktop/src-tauri/binaries/inky-engine-<rustc host triple>[.exe]`, a onefile binary that runs `inky.__main__.main()`.

- [ ] **Step 1:** Ask the user before downloading PyInstaller (a PyPI package, about 1.5 MB, into `.venv`).
- [ ] **Step 2: `engine-entry.py`:** `from inky.__main__ import main; main()`.
- [ ] **Step 3: `build-engine.py`** runs `[sys.executable, "-m", "PyInstaller", "--onefile", "--name", f"inky-engine-{triple}", "--collect-all", "playwright", "--add-data", f"inky/ui{os.pathsep}inky/ui", "--add-data", f"inky/overlay.js{os.pathsep}inky", "--paths", ".", "desktop/scripts/engine-entry.py", "--distpath", "desktop/src-tauri/binaries", "--workpath", "build/pyi", "--specpath", "build/pyi"]`. The triple comes from `rustc -vV` (the `host:` line). The engine must find its UI and overlay through `Path(__file__).parent`, which works in onefile via `_MEIPASS`, because PyInstaller keeps package-relative data at `inky/...`.
- [ ] **Step 4: Smoke test:** run the binary with `--port 0 --home <tmp> --no-open`, curl `/api/ping`, then kill it. Commit: "Engine binary for the app (PyInstaller)".

### Task 13: Tauri shell: engine sidecar, main window

**Files:** Create `desktop/package.json`, `desktop/src-tauri/Cargo.toml`, `desktop/src-tauri/build.rs`, `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/capabilities/default.json`, `desktop/src-tauri/src/main.rs`, `desktop/src-tauri/src/engine.rs`, and `desktop/src-tauri/icons/*` (generated from the critter SVG with `tauri icon`)

**Interfaces:**
- Produces:
  - `engine::discover(home: &Path) -> Option<String>` reads `engine.json` and returns the url when `/api/ping` answers;
  - `engine::parse_url(line: &str) -> Option<String>`;
  - the managed state `Engine { url: String, token: String, child: Option<CommandChild> }`.

- [ ] **Step 1: Check free disk** (at least 6 GB). If it's short, stop and ask the user to free space, and offer `npm cache clean --force` (2.1 GB).
- [ ] **Step 2:** `npm i -D @tauri-apps/cli@^2` in `desktop/`, after asking about the download (about 20 MB).
- [ ] **Step 3: Write the Rust unit tests** in `engine.rs`: `parse_url("Inky is running at http://127.0.0.1:53211")` returns `Some("http://127.0.0.1:53211")`; garbage returns None; `discover` on a temp home without engine.json returns None.
- [ ] **Step 4: Implement `main.rs`.**
  - `setup`: resolve home = `~/.inky`. Try `discover`, otherwise spawn the sidecar `binaries/inky-engine` with args `--port 0 --no-open --home <home>` and wait for the stdout line via `parse_url` (30 s timeout, then an error dialog).
  - Read the token from `home/api_token`.
  - Create the main window with `WebviewUrl::External(url)`, title "Inky", 1280×820, minimum 900×600.
  - On exit, kill the child only if the app spawned it.
- [ ] **Step 5:** `cargo test` in `desktop/src-tauri` passes, and `npm run tauri dev` opens the app on the live engine. Commit: "Tauri app: starts or attaches to the engine, native window".

### Task 14: Tray, badge, shortcuts, bar window

**Files:** Modify `desktop/src-tauri/src/main.rs`; create `desktop/src-tauri/src/tray.rs`; modify `inky/ui/app.js` (the `native()` bridge prefers `window.__TAURI__.core.invoke`)

**Interfaces:**
- Consumes `GET /api/state` with the `X-Inky-Token` header.
- Produces the Tauri command `bar(msg: {type, hash?})`, where hide hides the bar and open focuses main and navigates to `url + "/" + hash`.

- [ ] **Step 1: Tray.** The critter template icon plus 3 frame icons. A 4 s poll thread refreshes the menu (the same items as InkyBar) and the badge (`set_badge_count` on macOS and Linux, `set_overlay_icon` on Windows), and animates frames while any bot is working or learning.
- [ ] **Step 2: Shortcuts** with `tauri-plugin-global-shortcut`: `Alt+Space` (falling back to `Ctrl+Alt+Space`) toggles the bar, `Ctrl+Alt+P` pauses all, `Ctrl+Alt+Escape` stops screen bots.
- [ ] **Step 3: The bar window**: transparent, undecorated, always on top, skip-taskbar, 720×500, URL `url + "/?bar=1#/bar"`, hidden at start. Showing it positions it at the top center, focuses it and evals `inkyBarOpen()`. It hides on blur.
- [ ] **Step 4: Change `app.js` `native()`:** `if (window.__TAURI__) return window.__TAURI__.core.invoke("bar", { msg: m }); try { window.webkit.messageHandlers.inky.postMessage(m); } catch (e) {}`. The capability allows the `bar` command for the remote origin `http://127.0.0.1:*`, with `withGlobalTauri: true`.
- [ ] **Step 5: Check with computer control** (the app is native, so full tier): the tray menu lists the bots, ⌥Space opens the bar, typing `@Flat` filters, and Esc hides. Commit: "Tray, badge, global shortcuts and the floating bar in the app".

### Task 15: Notifications, autostart, buddy, file association; retire InkyBar

**Files:** Modify `desktop/src-tauri/src/main.rs`, `tauri.conf.json` (fileAssociations for `.json` with the names `*.inky.json` and `*.skill.json`); create `desktop/buddy.html`; delete `native/mac/`; modify `inky/__main__.py` (drop `--bar`), `inky/ui/views.js` (Settings: Launch at login and Buddy toggles, backed by Tauri commands when present), `.github/workflows/ci.yml` (drop the inkybar job)

- [ ] **Step 1: Notifications.** The tray poll diffs needs and new results. For each new need, send a notification "<bot> needs you" with the title; clicking it focuses main at `#/needs`. New results give "<bot>: N new". Both respect quiet hours.
- [ ] **Step 2: Autostart.** Add `tauri-plugin-autostart` and the commands `autostart_get` and `autostart_set`.
- [ ] **Step 3: The buddy window**: 120×120, transparent, always on top, undecorated, skip-taskbar, at the bottom-right edge of the primary monitor, showing `buddy.html`. It shows the critter of the first bot that needs you, peeking in with a CSS slide. It is shown when needs > 0 and the setting `buddy` is on, and hidden otherwise. Clicking it invokes `open_needs`.
- [ ] **Step 4: File association.** Opening a file imports it: POST `/api/import` or `/api/bots/:id/skills/import` depending on its content, then focus main.
- [ ] **Step 5: Delete `native/mac/`,** the `--bar` flag, the inkybar CI job and the menu-bar lines in Settings; the Settings shortcut text now says "with the Inky app".
- [ ] **Step 6: Check with computer control and commit:** "Notifications, launch at login, desktop buddy, open .inky files; InkyBar retired".

### Task 16: CI builds and the final check

**Files:** Modify `.github/workflows/ci.yml` (a `desktop` job: matrix macOS/Windows/Ubuntu → build engine → `tauri build` → upload artifacts), `docs/superpowers/test-report-2026-09-30.md`

- [ ] **Step 1: Add the CI job.** On Ubuntu, install `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf` first.
- [ ] **Step 2:** Push `build` (already approved for CI on this branch), then read the results and fix failures.
- [ ] **Step 3: Full check with computer control** of every new feature. Add a "Third pass" table to the test report. Commit and push.
