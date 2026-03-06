"""
Download all RocketReach search results (paginated) for the ICP query.

Usage:
    RR_API_KEY=your_key python scripts/rocketreach_download.py
    RR_API_KEY=your_key python scripts/rocketreach_download.py --max 10000
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import requests

API_KEY = os.environ.get("RR_API_KEY", "")
BASE_URL = "https://api.rocketreach.co/v2"

HEADERS = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json",
}

QUERY = {
    "current_title": [
        "CEO", "CTO", "CFO", "COO", "CMO", "CIO", "CISO",
        "Chief Executive Officer", "Chief Technology Officer",
        "Chief Financial Officer", "Chief Operating Officer",
    ],
    "location": ["United States"],
    "company_industry": ["Information Technology & Services", "Computer Software"],
    "company_size": [
        "1-10", "11-50", "51-200", "201-500",
        "501-1000", "1001-5000", "5001-10000",
    ],
}

PAGE_SIZE = 100


def search_page(start: int) -> dict:
    resp = requests.post(
        f"{BASE_URL}/api/search",
        headers=HEADERS,
        json={"query": QUERY, "page_size": PAGE_SIZE, "start": start},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=10000, help="Max profiles to download")
    parser.add_argument("--out", default="data/rocketreach_leads_all.json")
    args = parser.parse_args()

    if not API_KEY:
        print("Set RR_API_KEY environment variable first")
        sys.exit(1)

    root = Path(__file__).resolve().parents[1]
    out_path = Path(args.out) if Path(args.out).is_absolute() else root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_profiles = []
    start = 1

    # First request to get total
    print("Fetching page 1...")
    data = search_page(start)
    total = data.get("pagination", {}).get("total", 0)
    profiles = data.get("profiles", [])
    all_profiles.extend(profiles)
    target = min(total, args.max)
    print(f"Total available: {total}, downloading up to: {target}")

    while len(all_profiles) < target:
        start = data.get("pagination", {}).get("next", start + PAGE_SIZE)
        if start > target:
            break

        page_num = (start // PAGE_SIZE) + 1
        print(f"Fetching page {page_num} (start={start}, collected={len(all_profiles)})...")

        time.sleep(1)  # rate limit courtesy

        try:
            data = search_page(start)
            profiles = data.get("profiles", [])
            if not profiles:
                print("No more results.")
                break
            all_profiles.extend(profiles)
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error: {e}")
            if e.response.status_code == 429:
                print("Rate limited. Waiting 30s...")
                time.sleep(30)
                continue
            break
        except Exception as e:
            print(f"Error: {e}")
            break

    with open(out_path, "w") as f:
        json.dump(all_profiles, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Downloaded {len(all_profiles)} profiles -> {out_path}")


if __name__ == "__main__":
    main()
