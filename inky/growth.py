"""How a bot grows: days on the job, streaks, the time and AI calls it saved you, levels that unlock accessories,
and a short diary of its day in the first person. Pure functions over runs and events."""
import math
from datetime import datetime, timedelta

LEVELS = [(10, "scarf"), (50, "party"), (100, "star"), (500, "crown")]
SECONDS_PER_STEP = 20  # rough time a person spends on one step by hand

QUIRK_LINES = {
    "octopus": "All eight arms are tired, in a good way.",
    "cat": "Now for a well-earned nap.",
    "blob": "Squishing off to bed, happy.",
}


def ok_runs(runs):
    return [r for r in runs if r.get("kind") == "replay" and r.get("status") == "ok"]


def stats(bot, runs, skills, now):
    good = ok_runs(runs)
    steps_default = len(skills[0]["steps"]) if skills else 0
    steps = [r.get("steps") or steps_default for r in good]
    created = bot.get("created") or now
    days = int((now - created) // 86400) + 1
    dates = {datetime.fromtimestamp(r["ts"]).date() for r in good}
    today = datetime.fromtimestamp(now).date()
    d = today if today in dates else today - timedelta(days=1)  # a streak lives until tonight
    streak = 0
    while d in dates:
        streak += 1
        d -= timedelta(days=1)
    n = len(good)
    unlocked = [acc for at, acc in LEVELS if n >= at]
    nxt = next(({"at": at, "acc": acc} for at, acc in LEVELS if n < at), None)
    return {"days": days, "streak": streak, "runs": n,
            "ai_saved": max(0, sum(steps) - sum(r.get("ai_calls") or 0 for r in good)),
            "hours_saved": round(sum(steps) * SECONDS_PER_STEP / 3600, 1),
            "level": len(unlocked), "unlocked": unlocked, "next": nxt}


def unlocked(n_ok_runs):
    return [acc for at, acc in LEVELS if n_ok_runs >= at]


def level_up(before, after):
    return next((acc for at, acc in LEVELS if before < at <= after), None)


def diary_entry(bot, events, runs):
    good = ok_runs(runs)
    kind = (bot.get("look") or {}).get("kind", "octopus")
    if not good and not events:
        return "A quiet day. Nobody needed me, so I kept an eye on things."
    items = sum(r.get("items") or 0 for r in good)
    new = sum(r.get("new") or 0 for r in good)
    parts = [f"Today I did {len(good)} run{'s' if len(good) != 1 else ''}"
             + (f" and checked {items} results; {new} {'was' if new == 1 else 'were'} new." if items else ".")]
    kinds = {e.get("kind") for e in events}
    if "fixed" in kinds:
        parts.append("A button moved on the site and I fixed my step without bothering you.")
    if "problem" in kinds:
        parts.append("I got stuck once and asked you for help.")
    if "level" in kinds:
        parts.append("And I reached a new level!")
    parts.append(QUIRK_LINES.get(kind, QUIRK_LINES["octopus"]))
    return " ".join(parts)
