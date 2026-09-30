// UI logic that must stay right: moods, quiet hours, blink timing, sound voices. Run: node --test inky/ui/
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { moodOf, inQuiet, blinkDelay } = require("./life.js");

const now = new Date(2026, 8, 30, 12, 0).getTime();
const bot = (o) => ({ id: 1, status: "idle", needs: 0, schedule: { quiet_from: "23:00", quiet_to: "07:00" }, ...o });

test("state moods", () => {
  assert.equal(moodOf(bot({ status: "working" }), {}, now), "focused");
  assert.equal(moodOf(bot({ status: "learning" }), {}, now), "curious");
  assert.equal(moodOf(bot({ status: "needs_you", need_kind: "decision" }), {}, now), "waving");
  assert.equal(moodOf(bot({ status: "needs_you", need_kind: "problem" }), {}, now), "worried");
  assert.equal(moodOf(bot({}), {}, now), "calm");
  // a run waiting on your yes is still "working", but it should wave at you
  assert.equal(moodOf(bot({ status: "working", needs: 1, need_kind: "decision" }), {}, now), "waving");
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

const { voiceOf } = require("./sound.js");
test("each bot has a stable voice of its own", () => {
  const a = { id: 1, look: { kind: "octopus", color: "#E9A23B" } }, b = { id: 2, look: { kind: "cat", color: "#7C6CF2" } };
  assert.deepEqual(voiceOf(a), voiceOf({ ...a }));
  assert.notEqual(voiceOf(a).base, voiceOf(b).base);
  assert.ok(voiceOf(a).base >= 330 && voiceOf(a).base <= 880);
  assert.equal(voiceOf(b).wave, "triangle");
});

const { nextBehaviour } = require("./life.js");
test("idle behaviours: the same for a seed, different between critters, fitting the mood", () => {
  const beats = (seed, mood = "calm") => [0, 1, 2, 3, 4].map((n) => nextBehaviour(seed, n, mood));
  assert.deepEqual(beats(3), beats(3));
  const seen = new Set();
  for (let s = 1; s <= 40; s++) { const k = JSON.stringify(beats(s)); assert.ok(!seen.has(k), `seed ${s} repeats another critter`); seen.add(k); }
  const names = new Set();
  for (let n = 0; n < 60; n++) {
    assert.ok(["none", "sway"].includes(nextBehaviour(7, n, "asleep").name));
    assert.notEqual(nextBehaviour(7, n, "focused").name, "yawn");
    const b = nextBehaviour(7, n, "calm");
    assert.ok(b.at >= 2500 && b.at <= 9000, `delay ${b.at}`);
    names.add(b.name);
  }
  assert.ok(names.size >= 5, "a calm critter does lots of different things");
});
