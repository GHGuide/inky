"""A bot's character: how chatty and playful it is, a catchphrase and a quirk.
It only shapes how a bot talks. Approval, safety and problem wording never come from here."""
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
          "never type passwords, never solve robot checks, and never pretend something happened.")


def normalize(p, kind):
    base = dict(DEFAULTS.get(kind) or DEFAULTS["octopus"])
    base.update({k: v for k, v in (p or {}).items() if v is not None and k in base})
    for k in ("chatty", "playful"):
        base[k] = min(1.0, max(0.0, float(base[k])))
    base["emoji"] = bool(base["emoji"])
    for k in ("catchphrase", "quirk", "bio"):
        base[k] = str(base[k])[:160]
    return base


def part_of_day(h):
    return "morning" if 5 <= h < 12 else "afternoon" if h < 17 else "evening" if h < 22 else "night"


def prompt_lines(bot, user_name, now, events):
    p = normalize(bot.get("persona"), (bot.get("look") or {}).get("kind", "octopus"))
    talk = "chatty and warm" if p["chatty"] > 0.6 else "brief" if p["chatty"] < 0.4 else "friendly and to the point"
    mood = "playful" if p["playful"] > 0.6 else "calm and serious" if p["playful"] < 0.4 else "light"
    who = (f"YOUR CHARACTER: {talk}, {mood}. Quirk: {p['quirk']}. Catchphrase (use rarely): \"{p['catchphrase']}\"."
           + (f" In your own words: {p['bio']}" if p["bio"] else "")
           + (" Emoji are fine, at most one." if p["emoji"] else " No emoji."))
    lines = [who]
    if user_name:
        lines.append(f"You call the user {user_name}.")
    lines.append(f"It is {part_of_day(now.hour)} ({now.strftime('%a %H:%M')}).")
    if events:
        lines.append("RECENTLY: " + "; ".join(f"{datetime.fromtimestamp(e['ts']).strftime('%a')}: {e['text']}" for e in events[-6:]))
    lines.append("If you got something wrong, say so plainly and say what you'll do differently.")
    lines.append(SAFETY)
    return "\n".join(lines)
