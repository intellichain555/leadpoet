"""
Crawl RocketReach profile pages using crawl4ai with manual Cloudflare bypass.

1. Opens a visible browser window
2. Navigates to RocketReach — you manually solve the Cloudflare challenge
3. Once past, the script crawls each profile URL and extracts available data
4. Outputs miner-compatible lead JSON

Usage:
    python scripts/crawl_rocketreach.py
    python scripts/crawl_rocketreach.py --input docs/dataset_rocketreach-pr-226_2026-03-06_04-36-22-452.json --out data/rocketreach_leads.json
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


def parse_profile_markdown(md: str, url: str) -> dict | None:
    """Extract whatever lead fields are publicly visible from the rendered page."""
    if not md or "security verification" in md.lower():
        return None

    lines = md.strip().splitlines()
    lead = {
        "full_name": "", "first": "", "last": "", "email": "",
        "role": "", "linkedin": "", "description": "",
        "business": "", "website": "", "company_linkedin": "",
        "employee_count": "", "industry": "", "sub_industry": "",
        "country": "", "state": "", "city": "",
        "hq_country": "", "hq_state": "", "hq_city": "",
        "source_url": url, "source_type": "public_registry",
        "license_doc_hash": "", "license_doc_url": "",
    }

    text = md

    # Name — usually the first heading or large text
    name_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
    if name_match:
        raw_name = name_match.group(1).strip()
        # Strip suffixes like "Email & Phone Number"
        raw_name = re.sub(r"\s*(Email|Phone|Number|&|\|).*$", "", raw_name, flags=re.IGNORECASE).strip()
        lead["full_name"] = raw_name
        parts = raw_name.split(None, 1)
        lead["first"] = parts[0] if parts else ""
        lead["last"] = parts[1] if len(parts) > 1 else ""

    # Email
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if email_match:
        lead["email"] = email_match.group(0)

    # LinkedIn
    li_match = re.search(r"https?://(?:www\.)?linkedin\.com/in/[\w-]+", text)
    if li_match:
        lead["linkedin"] = li_match.group(0)

    # Title/role — look for common patterns
    role_match = re.search(r"(?:Title|Role|Position)[:\s]*(.+)", text, re.IGNORECASE)
    if role_match:
        lead["role"] = role_match.group(1).strip()[:80]

    # Company
    co_match = re.search(r"(?:Company|Employer|Works? at)[:\s]*(.+)", text, re.IGNORECASE)
    if co_match:
        lead["business"] = co_match.group(1).strip()

    # Location
    loc_match = re.search(r"(?:Location|Based in|City)[:\s]*(.+)", text, re.IGNORECASE)
    if loc_match:
        lead["city"] = loc_match.group(1).strip()

    # Industry
    ind_match = re.search(r"(?:Industry)[:\s]*(.+)", text, re.IGNORECASE)
    if ind_match:
        lead["industry"] = ind_match.group(1).strip()

    # Employee count
    emp_match = re.search(r"(?:Employees|Company Size)[:\s]*(.+)", text, re.IGNORECASE)
    if emp_match:
        lead["employee_count"] = emp_match.group(1).strip()

    # Company website
    web_match = re.search(r"(?:Website)[:\s]*(https?://\S+)", text, re.IGNORECASE)
    if web_match:
        lead["website"] = web_match.group(1).strip()
        lead["source_url"] = lead["website"]

    return lead


async def main(input_path: Path, output_path: Path, batch_size: int = 5):
    with open(input_path) as f:
        dataset = json.load(f)

    # Filter person entries only
    person_urls = [
        item["url"] for item in dataset
        if item.get("type") == "person" and item.get("url")
    ]
    print(f"Found {len(person_urls)} person profiles to crawl")

    if not person_urls:
        print("No person URLs found.")
        return

    # Headed browser so user can solve Cloudflare challenge
    browser_config = BrowserConfig(
        headless=False,
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=30000,
    )

    leads = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Step 1: Navigate to first URL and wait for user to pass Cloudflare
        print("\n=== MANUAL STEP ===")
        print(f"Opening: {person_urls[0]}")
        print("Solve the Cloudflare challenge in the browser window.")
        input("Press ENTER here once you've passed the challenge...")

        # Step 2: Now crawl all profile URLs using the authenticated session
        for i in range(0, len(person_urls), batch_size):
            batch = person_urls[i : i + batch_size]
            print(f"\nCrawling batch {i // batch_size + 1} ({len(batch)} URLs)...")

            for url in batch:
                try:
                    result = await crawler.arun(url=url, config=run_config)
                    if result.markdown:
                        lead = parse_profile_markdown(result.markdown, url)
                        if lead and lead.get("full_name"):
                            leads.append(lead)
                            print(f"  OK: {lead['full_name']}")
                        else:
                            print(f"  SKIP (no data): {url}")
                            # Save raw markdown for debugging
                            debug_path = output_path.parent / "rocketreach_debug.md"
                            with open(debug_path, "a") as df:
                                df.write(f"\n\n=== {url} ===\n{result.markdown[:2000]}\n")
                            print(f"  (raw saved to {debug_path})")
                    else:
                        print(f"  SKIP (empty): {url}")
                except Exception as e:
                    print(f"  ERROR: {url} — {e}")

            # Small delay between batches
            if i + batch_size < len(person_urls):
                await asyncio.sleep(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Extracted {len(leads)} leads -> {output_path}")

    if leads:
        print("\nSample lead:")
        print(json.dumps(leads[0], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="docs/dataset_rocketreach-pr-226_2026-03-06_04-36-22-452.json",
    )
    parser.add_argument("--out", default="data/rocketreach_leads.json")
    parser.add_argument("--batch", type=int, default=5)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    input_path = Path(args.input) if Path(args.input).is_absolute() else root / args.input
    output_path = Path(args.out) if Path(args.out).is_absolute() else root / args.out

    asyncio.run(main(input_path, output_path, args.batch))
