"""
Test RocketReach API - fetch first person profile without spending credits.

Usage:
    RR_API_KEY=your_key python scripts/rocketreach_api_test.py
"""

import json
import os
import sys
from pathlib import Path
import requests

API_KEY = os.environ.get("RR_API_KEY", "")
BASE_URL = "https://api.rocketreach.co/v2"

HEADERS = {
    "Api-Key": API_KEY,
    "Content-Type": "application/json",
}


def search_icp() -> dict:
    """Search C-Suite at US IT & Software companies, 1-10k employees."""
    resp = requests.post(
        f"{BASE_URL}/api/search",
        headers=HEADERS,
        json={
            "query": {
                "current_title": ["CEO", "CTO", "CFO", "COO", "CMO", "CIO", "CISO",
                                  "Chief Executive Officer", "Chief Technology Officer",
                                  "Chief Financial Officer", "Chief Operating Officer"],
                "location": ["United States"],
                "company_industry": ["Information Technology & Services", "Computer Software"],
                "company_size": ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000"],
            },
            "page_size": 5,
            "start": 1,
        },
        timeout=15,
    )
    print(f"[search ICP] status={resp.status_code}")
    return resp.json()


def main():
    if not API_KEY:
        print("Set RR_API_KEY environment variable first:")
        print("  export RR_API_KEY=your_api_key_here")
        sys.exit(1)

    out_path = Path(__file__).resolve().parents[1] / "data" / "rocketreach_search.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("=== Testing RocketReach API (search only, no credits) ===\n")

    print("--- ICP Search (C-Suite, US, IT & Software, 1-10k employees) ---")
    icp_result = search_icp()

    profiles = icp_result.get("profiles", [])
    print(f"Got {len(profiles)} results (total: {icp_result.get('pagination', {}).get('total', '?')})")

    with open(out_path, "w") as f:
        json.dump(icp_result, f, indent=2, ensure_ascii=False)

    print(f"Saved to {out_path}")
    if profiles:
        print(f"\nFirst result: {profiles[0].get('name')} - {profiles[0].get('current_title')} at {profiles[0].get('current_employer')}")


if __name__ == "__main__":
    main()
