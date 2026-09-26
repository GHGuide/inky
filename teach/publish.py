"""Publish the learned program as the Apify actor "inky-tecnocasa-homes", run it once and check it.

    .venv/bin/python teach/publish.py             # upload teach/actor + the program, build, run (maxItems 20), check
    .venv/bin/python teach/publish.py --run-only  # only run and check the published actor

Does what `apify push` does (source files + a build, through the Apify API) with the token read from .env,
so the token is never stored by a CLI login. Writes teach/published.json.
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
ACTOR = HERE / "actor"
PROGRAM = HERE / "tecnocasa.program.json"
PUBLISHED = HERE / "published.json"
FILES = [".actor/actor.json", "Dockerfile", ".dockerignore", "package.json", "package-lock.json", "main.js", "program.json"]
VERSION = "0.1"
RUN_INPUT = {"maxItems": 20, "maxPrice": 200000, "city": "Bari"}
sys.path.insert(0, str(HERE))
from check import normalized  # noqa: E402


def status(x):
    return str(getattr(x.status, "value", x.status))


def publish(client, name):
    shutil.copy(PROGRAM, ACTOR / "program.json")
    files = [{"name": f, "format": "TEXT", "content": (ACTOR / f).read_text()} for f in FILES if (ACTOR / f).exists()]
    spec = json.loads((ACTOR / ".actor/actor.json").read_text())
    actor = client.actor(f"{client.user().get().username}/{name}").get()
    if actor is None:
        actor = client.actors().create(name=name, title=spec["title"], description=spec["description"],
                                       is_public=False, default_run_memory_mbytes=256)
        client.actor(actor.id).versions().create(version_number=VERSION, source_type="SOURCE_FILES",
                                                 source_files=files, build_tag="latest")
    else:
        client.actor(actor.id).version(VERSION).update(source_type="SOURCE_FILES", source_files=files, build_tag="latest")
    build = client.actor(actor.id).build(version_number=VERSION, wait_for_finish=60)
    while status(build) in ("READY", "RUNNING"):
        time.sleep(5)
        build = client.build(build.id).get()
    print(f"build {status(build)}: https://console.apify.com/actors/{actor.id}/builds/{build.id}", flush=True)
    assert status(build) == "SUCCEEDED", "the build failed, see the build log in Apify Console"
    return actor


def run_once(client, actor_id):
    """One run at a time: the Apify plan allows 5 and the full scrape may use 4."""
    for _ in range(30):
        try:
            return client.actor(actor_id).call(run_input=RUN_INPUT, memory_mbytes=256, run_timeout=timedelta(minutes=5))
        except ApifyApiError as e:
            if "concurrent" not in str(e).lower():
                raise
            print("no free Apify run slot, waiting 60 s", flush=True)
            time.sleep(60)
    sys.exit("no free Apify run slot for 30 minutes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-only", action="store_true")
    args = ap.parse_args()
    if not PROGRAM.exists():
        sys.exit("No program yet: run .venv/bin/python teach/learn.py first.")
    load_dotenv(HERE.parent / ".env")
    client = ApifyClient(os.environ["APIFY_TOKEN"])
    name = json.loads((ACTOR / ".actor/actor.json").read_text())["name"]
    username = client.user().get().username

    actor = client.actor(f"{username}/{name}").get() if args.run_only else publish(client, name)
    assert actor, f"{username}/{name} is not published yet"
    run = run_once(client, actor.id)
    items = list(client.dataset(run.default_dataset_id).iterate_items())
    good = [i for i in items if isinstance(i.get("price"), int) and 1000 < i["price"] <= RUN_INPUT["maxPrice"]
            and isinstance(i.get("size_m2"), int) and 10 < i["size_m2"] < 1000 and i.get("title")
            and str(i.get("url", "")).startswith("https://www.tecnocasa.it/")]
    n = normalized(items)
    result = {
        "actor": f"{username}/{name}", "actor_id": actor.id,
        "actor_url": f"https://console.apify.com/actors/{actor.id}",
        "run_url": f"https://console.apify.com/view/runs/{run.id}", "run_status": status(run),
        "dataset_id": run.default_dataset_id, "run_input": RUN_INPUT,
        "items": len(items), "sensible_items": len(good), "normalized_items": n,
        "usage_usd": run.usage_total_usd, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PUBLISHED.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    assert status(run) == "SUCCEEDED" and len(items) == 20 and len(good) == 20 and n == 20, "the test run is not 20 sensible listings"
    print(f"ok: {result['actor']} returned 20 sensible listings -> {PUBLISHED}")


if __name__ == "__main__":
    main()
