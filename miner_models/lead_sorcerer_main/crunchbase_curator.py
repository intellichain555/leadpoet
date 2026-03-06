"""
Crunchbase AI/ML company curator.

Phase 1 of the aiml_crunchbase pipeline:
  1. Serper.dev queries (site:crunchbase.com/organization) to discover AI/ML companies
  2. Serper query per company name to find the actual website URL
     (Crunchbase blocks crawl4ai via Cloudflare, so we use Serper instead)
  3. Persist results to data/curated/aiml_crunchbase.jsonl

The JSONL file tracks status per company: pending → done | failed | no_website
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

logger = logging.getLogger("crunchbase_curator")

CURATED_FILE = "aiml_crunchbase.jsonl"
TARGET_COMPANY_COUNT = 1000
MIN_PENDING_THRESHOLD = 50  # re-curate when fewer than this remain

# 30 diverse queries to maximise unique AI/ML company coverage.
# Each returns up to 100 Google results via Serper (num=100).
AIML_QUERIES = [
    'site:crunchbase.com/organization "artificial intelligence" startup founded',
    'site:crunchbase.com/organization "machine learning" company',
    'site:crunchbase.com/organization "deep learning" startup',
    'site:crunchbase.com/organization "computer vision" company',
    'site:crunchbase.com/organization "natural language processing" startup',
    'site:crunchbase.com/organization "generative AI" company',
    'site:crunchbase.com/organization "AI SaaS" startup',
    'site:crunchbase.com/organization "robotics" "artificial intelligence"',
    'site:crunchbase.com/organization "AI platform" startup funding',
    'site:crunchbase.com/organization "conversational AI" company',
    'site:crunchbase.com/organization "AI analytics" startup',
    'site:crunchbase.com/organization "autonomous" "AI" startup',
    'site:crunchbase.com/organization "AI healthcare" company',
    'site:crunchbase.com/organization "AI fintech" startup',
    'site:crunchbase.com/organization "AI cybersecurity" company',
    'site:crunchbase.com/organization "MLOps" startup',
    'site:crunchbase.com/organization "AI infrastructure" company',
    'site:crunchbase.com/organization "predictive AI" startup',
    'site:crunchbase.com/organization "large language model" company',
    'site:crunchbase.com/organization "AI drug discovery" startup',
    'site:crunchbase.com/organization "speech recognition" "AI" company',
    'site:crunchbase.com/organization "recommendation engine" "machine learning"',
    'site:crunchbase.com/organization "AI supply chain" startup',
    'site:crunchbase.com/organization "edge AI" company',
    'site:crunchbase.com/organization "AI marketing" startup',
    'site:crunchbase.com/organization "reinforcement learning" company',
    'site:crunchbase.com/organization "AI enterprise" startup series',
    'site:crunchbase.com/organization "neural network" startup founded',
    'site:crunchbase.com/organization "AI automation" company',
    'site:crunchbase.com/organization "foundation model" startup',
]

# Domains to exclude when extracting a company website from a Crunchbase page
EXCLUDED_DOMAINS = {
    "crunchbase.com", "linkedin.com", "twitter.com", "x.com",
    "facebook.com", "github.com", "youtube.com", "instagram.com",
    "medium.com", "wikipedia.org", "google.com", "apple.com",
    "microsoft.com", "amazonaws.com", "cloudfront.net",
    "googleapis.com", "gstatic.com", "w3.org",
}


class CrunchbaseCurator:
    """Curate AI/ML startup companies from Crunchbase via Serper + crawl4ai."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.curated_dir = self.data_dir / "curated"
        self.curated_file = self.curated_dir / CURATED_FILE
        self.serper_key = os.environ.get("SERPER_API_KEY", "")

    # ── JSONL persistence ──────────────────────────────────────────────

    def _load_curated_list(self) -> List[Dict[str, Any]]:
        companies: List[Dict[str, Any]] = []
        if self.curated_file.exists():
            with open(self.curated_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            companies.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return companies

    def _save_curated_list(self, companies: List[Dict[str, Any]]):
        self.curated_dir.mkdir(parents=True, exist_ok=True)
        with open(self.curated_file, "w") as f:
            for company in companies:
                f.write(json.dumps(company) + "\n")

    def _append_company(self, record: Dict[str, Any]):
        self.curated_dir.mkdir(parents=True, exist_ok=True)
        with open(self.curated_file, "a") as f:
            f.write(json.dumps(record) + "\n")

    # ── Public API ─────────────────────────────────────────────────────

    def get_pending_companies(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the next *limit* companies with status=pending."""
        return [
            c for c in self._load_curated_list()
            if c.get("status") == "pending"
        ][:limit]

    def mark_company_done(self, crunchbase_slug: str):
        self._update_status(crunchbase_slug, "done")

    def mark_company_failed(self, crunchbase_slug: str, reason: str = ""):
        self._update_status(crunchbase_slug, "failed", reason)

    def _update_status(self, slug: str, status: str, reason: str = ""):
        companies = self._load_curated_list()
        for c in companies:
            if c.get("crunchbase_slug") == slug:
                c["status"] = status
                c["updated_at"] = datetime.now(timezone.utc).isoformat()
                if reason:
                    c["failure_reason"] = reason
                break
        self._save_curated_list(companies)

    def needs_curation(self) -> bool:
        """True when the pending pool is below threshold."""
        pending = [
            c for c in self._load_curated_list()
            if c.get("status") == "pending"
        ]
        return len(pending) < MIN_PENDING_THRESHOLD

    def stats(self) -> Dict[str, int]:
        """Return counts by status."""
        companies = self._load_curated_list()
        counts: Dict[str, int] = {}
        for c in companies:
            s = c.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        counts["total"] = len(companies)
        return counts

    # ── Phase 1: Curation ──────────────────────────────────────────────

    async def run_curation(self) -> int:
        """
        Full curation pipeline.  Returns count of new companies added.
        """
        print("[CrunchbaseCurator] Starting curation of AI/ML companies...")

        existing = self._load_curated_list()
        existing_slugs: Set[str] = {
            c["crunchbase_slug"] for c in existing if c.get("crunchbase_slug")
        }
        print(f"[CrunchbaseCurator] {len(existing_slugs)} companies already curated")

        # Step 1: discover Crunchbase org URLs via Serper
        new_orgs = await self._discover_crunchbase_orgs(existing_slugs)
        print(f"[CrunchbaseCurator] Discovered {len(new_orgs)} new Crunchbase org URLs")

        if not new_orgs:
            print("[CrunchbaseCurator] No new organisations found")
            return 0

        # Step 2: crawl each CB page to extract company website
        new_count = 0
        batch_size = 10

        for i in range(0, len(new_orgs), batch_size):
            batch = new_orgs[i:i + batch_size]
            results = await self._extract_websites_batch(batch)

            for record in results:
                self._append_company(record)
                if record.get("website"):
                    new_count += 1

            done = min(i + batch_size, len(new_orgs))
            print(
                f"[CrunchbaseCurator] Processed {done}/{len(new_orgs)}, "
                f"{new_count} with websites"
            )

        total_stats = self.stats()
        print(
            f"[CrunchbaseCurator] Curation complete: +{new_count} with websites.  "
            f"Total: {total_stats}"
        )
        return new_count

    # ── Serper discovery ───────────────────────────────────────────────

    async def _discover_crunchbase_orgs(
        self, existing_slugs: Set[str],
    ) -> List[Dict[str, str]]:
        """
        Use Serper.dev to find Crunchbase /organization/ pages via Google.
        Returns list of {url, slug, title, snippet}.
        """
        if not self.serper_key:
            print("[CrunchbaseCurator] ERROR: SERPER_API_KEY not set")
            return []

        all_orgs: Dict[str, Dict[str, str]] = {}  # slug → record

        for idx, query in enumerate(AIML_QUERIES):
            print(
                f"[CrunchbaseCurator] Query {idx+1}/{len(AIML_QUERIES)}: "
                f"{query[:70]}..."
            )
            try:
                resp = await self._serper_search(query, num=100)
                results = resp.get("organic", [])

                for r in results:
                    link = r.get("link", "")
                    slug = self._extract_org_slug(link)
                    if not slug or slug in existing_slugs or slug in all_orgs:
                        continue
                    all_orgs[slug] = {
                        "url": link,
                        "slug": slug,
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", ""),
                    }

                print(
                    f"  -> {len(results)} results, "
                    f"{len(all_orgs)} unique orgs so far"
                )
                await asyncio.sleep(1.0)  # rate-limit

            except Exception as e:
                print(f"  -> ERROR: {e}")
                continue

        return list(all_orgs.values())

    async def _serper_search(self, query: str, num: int = 100) -> Dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": num},
                headers={
                    "X-API-KEY": self.serper_key,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _extract_org_slug(url: str) -> Optional[str]:
        m = re.search(r"crunchbase\.com/organization/([a-zA-Z0-9_-]+)", url)
        return m.group(1).lower() if m else None

    # ── crawl4ai website extraction ────────────────────────────────────

    async def _extract_websites_batch(
        self, orgs: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """Crawl a batch of Crunchbase org pages and extract website URLs."""
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        browser_cfg = BrowserConfig(
            headless=True,
            extra_args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        crawler_cfg = CrawlerRunConfig(
            wait_until="domcontentloaded",
            page_timeout=30000,
            word_count_threshold=10,
        )

        results: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                for org in orgs:
                    website = await self._crawl_cb_page(
                        crawler, crawler_cfg, org["url"],
                    )

                    results.append({
                        "crunchbase_slug": org["slug"],
                        "crunchbase_url": org["url"],
                        "company_name": self._clean_title(org.get("title", "")),
                        "snippet": org.get("snippet", ""),
                        "website": website,
                        "status": "pending" if website else "no_website",
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    })

                    await asyncio.sleep(0.5)

        except Exception as e:
            print(f"[CrunchbaseCurator] Browser error: {e}")

        return results

    async def _crawl_cb_page(
        self, crawler, config, url: str,
    ) -> Optional[str]:
        """Extract the company's own website from a Crunchbase org page."""
        try:
            result = await crawler.arun(url=url, config=config)
            if not result.success or not result.markdown:
                return None

            md = result.markdown

            # Pattern 1: Markdown-link labelled "Website" / "Visit Website"
            # Pattern 2: bare URL near "Website" heading
            # Pattern 3: first external https:// URL that isn't a known platform
            patterns = [
                r"\[(?:Visit\s*Website|Website|Homepage)\]\((https?://[^\)]+)\)",
                r"(?:Website|Homepage)\s*[:\|]\s*(https?://[^\s\)>\]]+)",
                r"(https?://(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s\)]*)?)",
            ]

            for pattern in patterns:
                for match in re.findall(pattern, md, re.IGNORECASE):
                    clean = match.rstrip(".,;:")
                    domain = re.sub(r"https?://(www\.)?", "", clean).split("/")[0].lower()
                    if domain and not any(domain.endswith(ex) for ex in EXCLUDED_DOMAINS):
                        return f"https://{domain}"

            return None

        except Exception as e:
            logger.warning(f"Failed to crawl {url}: {e}")
            return None

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip Crunchbase boilerplate from the Google result title."""
        for suffix in [" - Crunchbase Company Profile & Funding",
                       " - Crunchbase",
                       " | Crunchbase"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]
        return title.strip()
