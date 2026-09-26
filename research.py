"""Scrape sale and rent listings for the three cities via Apify Store actors.

    uv run python research.py --max 20     # test run, ~$0.30
    uv run python research.py --max 5000   # full run, capped per job by --usd
"""
import argparse
import json
import os
from decimal import Decimal
from pathlib import Path

from apify_client import ApifyClient
from dotenv import load_dotenv

IDEALISTA = "igolaizola/idealista-scraper"
IMMOBILIARE = "memo23/immobiliare-scraper"
OTODOM = "trev0n/otodom-scraper"

JOBS = {
    "porto-sale-idealista": (IDEALISTA, {"country": "pt", "location": "Porto", "operation": "sale", "propertyType": "homes"}),
    "porto-rent-idealista": (IDEALISTA, {"country": "pt", "location": "Porto", "operation": "rent", "propertyType": "homes"}),
    "bari-sale-idealista": (IDEALISTA, {"country": "it", "location": "Bari", "operation": "sale", "propertyType": "homes"}),
    "bari-rent-idealista": (IDEALISTA, {"country": "it", "location": "Bari", "operation": "rent", "propertyType": "homes"}),
    "bari-sale-immobiliare": (IMMOBILIARE, {"startUrls": [{"url": "https://www.immobiliare.it/vendita-case/bari/"}]}),
    "bari-rent-immobiliare": (IMMOBILIARE, {"startUrls": [{"url": "https://www.immobiliare.it/affitto-case/bari/"}]}),
    "lodz-sale-otodom": (OTODOM, {"searchType": "sprzedaz", "propertyType": "mieszkanie", "location": "lodzkie/lodz/lodz/lodz"}),
    "lodz-rent-otodom": (OTODOM, {"searchType": "wynajem", "propertyType": "mieszkanie", "location": "lodzkie/lodz/lodz/lodz"}),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max", type=int, default=20, help="max listings per job")
    p.add_argument("--usd", type=Decimal, default=Decimal("12"), help="hard spend cap per job")
    p.add_argument("--only", nargs="*", help="job names to run")
    args = p.parse_args()

    load_dotenv()
    client = ApifyClient(os.environ["APIFY_TOKEN"])
    out = Path("data")
    out.mkdir(exist_ok=True)

    jobs = {k: v for k, v in JOBS.items() if not args.only or k in args.only}
    runs = {}
    for name, (actor, run_input) in jobs.items():
        run_input = {**run_input, "maxItems": args.max}
        runs[name] = client.actor(actor).start(run_input=run_input, max_items=args.max, max_total_charge_usd=args.usd)
        print(f"started {name}")

    for name, run in runs.items():
        run = client.run(run.id).wait_for_finish()
        items = list(client.dataset(run.default_dataset_id).iterate_items())
        (out / f"{name}.json").write_text(json.dumps(items, ensure_ascii=False))
        print(f"{run.status:10} {name}: {len(items)} listings")


if __name__ == "__main__":
    main()
