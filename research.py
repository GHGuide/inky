"""Scrape sale and rent listings for the three cities via Apify Store actors.

    uv run python research.py            # test run: 20 per job, about $0.30
    uv run python research.py --full     # full run: about 48,000 listings, about $55

Raw items land in data/raw/<city>-<sale|rent>-<source>.json. Each job has a hard USD cap.
"""
import argparse
import json
import os
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
from dotenv import load_dotenv

IDEALISTA = "igolaizola/idealista-scraper"      # $0.0009 per listing
IMMOBILIARE = "memo23/immobiliare-scraper"      # $0.0007 per listing
OTODOM = "trev0n/otodom-scraper"                # $0.0020 per listing

# name: (actor, input, listings in the full run)
JOBS = {
    "porto-sale-idealista": (IDEALISTA, {"country": "pt", "location": "Porto", "operation": "sale", "propertyType": "homes"}, 5000),
    "porto-rent-idealista": (IDEALISTA, {"country": "pt", "location": "Porto", "operation": "rent", "propertyType": "homes"}, 5000),
    "bari-sale-idealista": (IDEALISTA, {"country": "it", "location": "Bari", "operation": "sale", "propertyType": "homes"}, 5000),
    "bari-rent-idealista": (IDEALISTA, {"country": "it", "location": "Bari", "operation": "rent", "propertyType": "homes"}, 5000),
    "bari-sale-immobiliare": (IMMOBILIARE, {"startUrls": ["https://www.immobiliare.it/vendita-case/bari/"], "includeAgencyDetails": False}, 7500),
    "bari-rent-immobiliare": (IMMOBILIARE, {"startUrls": ["https://www.immobiliare.it/affitto-case/bari/"], "includeAgencyDetails": False}, 7500),
    "lodz-sale-otodom": (OTODOM, {"searchType": "sprzedaz", "propertyType": "mieszkanie", "location": "lodzkie/lodz/lodz/lodz"}, 6500),
    "lodz-rent-otodom": (OTODOM, {"searchType": "wynajem", "propertyType": "mieszkanie", "location": "lodzkie/lodz/lodz/lodz"}, 6500),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true", help="full run sizes instead of 20 per job")
    p.add_argument("--usd", type=Decimal, default=Decimal("15"), help="hard spend cap per job")
    p.add_argument("--only", nargs="*", help="job names to run")
    p.add_argument("--parallel", type=int, default=4, help="runs at the same time")
    p.add_argument("--max", type=int, help="listings per job, overrides the default size")
    p.add_argument("--timeout", type=int, default=0, help="run time limit in seconds (actor default if 0)")
    args = p.parse_args()

    load_dotenv()
    client = ApifyClient(os.environ["APIFY_TOKEN"])
    out = Path(os.environ.get("INKY_DATA", "data")) / "raw"
    out.mkdir(parents=True, exist_ok=True)

    pending = [(k, v) for k, v in JOBS.items() if not args.only or k in args.only]
    active, total_usd, total_items = {}, 0.0, 0
    while pending or active:
        while pending and len(active) < args.parallel:  # the Apify plan allows 5 runs at once
            name, (actor, run_input, full) = pending[0]
            n = args.max or (full if args.full else 20)
            try:
                run = client.actor(actor).start(run_input={**run_input, "maxItems": n}, max_items=n, max_total_charge_usd=args.usd,
                                                  run_timeout=timedelta(seconds=args.timeout) if args.timeout else None)
            except ApifyApiError as e:
                if "concurrent" not in str(e):
                    raise
                break  # no free slot yet, wait for a run to finish
            pending.pop(0)
            active[name] = run.id
            print(f"started {name} ({n} max)", flush=True)
        time.sleep(10)
        for name, run_id in list(active.items()):
            run = client.run(run_id).get()
            status = str(getattr(run.status, "value", run.status))
            if status in ("READY", "RUNNING"):
                continue
            del active[name]
            items = list(client.dataset(run.default_dataset_id).iterate_items())
            (out / f"{name}.json").write_text(json.dumps(items, ensure_ascii=False))
            usd = run.usage_total_usd or 0.0
            total_usd += usd
            total_items += len(items)
            print(f"{status:10} {name}: {len(items)} listings, ${usd:.2f}", flush=True)
    print(f"total: {total_items} listings, ${total_usd:.2f}")


if __name__ == "__main__":
    main()
