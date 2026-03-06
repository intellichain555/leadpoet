# Leadpoet Miner: Search API Comparison — Brave vs SerpApi vs Serper vs Google CSE

**Date:** 2026-02-27

---

## What the Miner Needs From a Search API

The miner's `GSESearchClient` (in `domain.py`) is simple. It only extracts **3 fields** per result:

```python
# domain.py line 604-610
{
    "url":     item.get("link", ""),      # Result URL
    "title":   item.get("title", ""),     # Page title
    "snippet": item.get("snippet", ""),   # Description text
}
```

The response must have results in `response["items"]` — each item needs `link`, `title`, and `snippet`.

These 3 fields are then passed to the LLM scorer which rates how well each company matches the ICP. The search API's job is just to **find relevant company websites** for queries like `"startup advisory services founder contact"`.

---

## Comparison Table

| Feature | Google CSE | Brave Search | SerpApi | Serper.dev |
|---------|-----------|-------------|---------|------------|
| **Source** | Google index | Own index (30B+ pages) | Scrapes Google | Scrapes Google |
| **Result quality** | Google-grade | Weaker for niche B2B | Google-grade | Google-grade |
| **Free tier** | Dead for new users (Jan 2026) | ~1,000 queries/month ($5 credit) | 250 queries/month | 2,500 queries one-time |
| **Free renewal** | N/A | Monthly $5 credit | Monthly 250 | Never (one-time) |
| **Cheapest paid** | $5/1K queries | $5/1K queries | $25/month (1K queries) | $50/month (50K queries) |
| **Effective $/1K** | $5.00 | $5.00 | $25.00 | $1.00 |
| **Rate limit (free)** | 100/day | ~33/day (at $5 credit) | 50/hour | N/A |
| **Auth method** | Query param `key=` | Header `X-Subscription-Token` | Query param `api_key=` | Header `X-API-KEY` |
| **Has `link`?** | Yes | Yes (`url`) | Yes (`link`) | Yes (`link`) |
| **Has `title`?** | Yes | Yes | Yes | Yes |
| **Has `snippet`?** | Yes | Yes (`description`) | Yes (`snippet`) | Yes (`snippet`) |
| **Python SDK** | No | No | Yes (`pip install serpapi`) | No |
| **New user signup** | Blocked | Open | Open | Open |

---

## Result Quality for B2B Lead Discovery

This is the critical question: can the search API find niche company websites from queries like `"business consulting firm advisor email"`?

### Google-Based APIs (SerpApi, Serper.dev) — Best Quality
- These query actual Google, so results are identical to what you'd see in a browser
- Google excels at finding specific companies, niche B2B sites, company directories
- Best for long-tail queries like `"SaaS startup founder CTO contact San Francisco"`
- **Winner for lead generation use case**

### Brave Search — Acceptable but Weaker
- Uses its own independent index (30 billion+ pages)
- Good for popular/well-known companies
- **Weaker for niche/small B2B companies** — its index is smaller than Google's
- May miss newer or smaller company websites that Google indexes
- For lead generation where you need to find obscure small businesses, this is a disadvantage

### Google CSE — Dead
- Closed to new users in January 2026
- Cannot sign up for the JSON API anymore
- Not an option

---

## Drop-In Compatibility

The miner expects `response["items"]` with each item having `link`, `title`, `snippet`. Here's what each API returns:

### Google CSE (current code)
```json
{
  "items": [
    {"title": "...", "link": "https://...", "snippet": "..."}
  ]
}
```

### Brave Search API
```json
{
  "web": {
    "results": [
      {"title": "...", "url": "https://...", "description": "..."}
    ]
  }
}
```
**Differences:** Results in `web.results` not `items`. Uses `url` not `link`. Uses `description` not `snippet`. Needs adapter code.

### SerpApi (Google engine)
```json
{
  "organic_results": [
    {"title": "...", "link": "https://...", "snippet": "...", "position": 1}
  ]
}
```
**Differences:** Results in `organic_results` not `items`. Fields `link`, `title`, `snippet` **match exactly**. Easiest to adapt.

### Serper.dev
```json
{
  "organic": [
    {"title": "...", "link": "https://...", "snippet": "...", "position": 1}
  ]
}
```
**Differences:** Results in `organic` not `items`. Fields `link`, `title`, `snippet` **match exactly**. Very easy to adapt.

---

## Code Change Needed (Minimal)

To swap GSE for any alternative, you only need to modify `GSESearchClient.search()` in `domain.py` (lines 66-98) and `_search_query()` (line 643-656 where `items` is referenced). Total: ~20 lines of code.

### For SerpApi (easiest — fields match):
```python
class SerpApiSearchClient:
    def __init__(self, api_key: str, semaphore_pool):
        self.api_key = api_key
        self.semaphore_pool = semaphore_pool

    async def search(self, query: str, page: int = 1) -> Dict[str, Any]:
        async with self.semaphore_pool:
            params = {
                "api_key": self.api_key,
                "engine": "google",
                "q": query,
                "start": (page - 1) * 10,
                "num": 10,
            }
            async with httpx.AsyncClient(timeout=(3.0, 10.0)) as client:
                resp = await client.get("https://serpapi.com/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                # Remap to GSE format so downstream code works unchanged
                return {"items": data.get("organic_results", [])}
```

### For Serper.dev (also easy — fields match):
```python
class SerperSearchClient:
    def __init__(self, api_key: str, semaphore_pool):
        self.api_key = api_key
        self.semaphore_pool = semaphore_pool

    async def search(self, query: str, page: int = 1) -> Dict[str, Any]:
        async with self.semaphore_pool:
            payload = {"q": query, "page": page, "num": 10}
            headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=(3.0, 10.0)) as client:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                return {"items": data.get("organic", [])}
```

### For Brave (needs field remapping):
```python
class BraveSearchClient:
    def __init__(self, api_key: str, semaphore_pool):
        self.api_key = api_key
        self.semaphore_pool = semaphore_pool

    async def search(self, query: str, page: int = 1) -> Dict[str, Any]:
        async with self.semaphore_pool:
            params = {"q": query, "count": 10, "offset": (page - 1) * 10}
            headers = {"X-Subscription-Token": self.api_key, "Accept": "application/json"}
            async with httpx.AsyncClient(timeout=(3.0, 10.0)) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params=params, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
                # Remap Brave fields to GSE format
                items = []
                for r in data.get("web", {}).get("results", []):
                    items.append({
                        "link": r.get("url", ""),
                        "title": r.get("title", ""),
                        "snippet": r.get("description", ""),
                    })
                return {"items": items}
```

---

## Recommendation

### Best Overall: Serper.dev

| Reason | Detail |
|--------|--------|
| **Google-quality results** | Actually queries Google — identical result quality |
| **Free to start** | 2,500 queries one-time (no credit card) |
| **Cheapest at scale** | $1.00/1K queries (vs $5/1K for Brave, $25/1K for SerpApi) |
| **Field compatibility** | `link`, `title`, `snippet` match GSE exactly |
| **Easy to integrate** | POST endpoint, simple JSON, ~15 lines of adapter code |
| **High throughput** | Up to 300 QPS on paid plans |

### Daily Usage Estimate
With default miner config (fast mode, 2 queries):
- **2 search calls per sourcing cycle** (when GSE is active)
- With 48h SERP cache: **~2-10 unique API calls/day** after warm-up
- 2,500 free Serper credits = **250-1,250 days** of mining (effectively free forever in default mode)

### Runner-Up: Brave Search

Good if you want a **monthly renewable** free allowance ($5/month credit ≈ 1,000 queries). But weaker results for niche B2B company discovery. Use this if you value ongoing free access over result quality.

### Skip: SerpApi

Google-quality results but **10-25x more expensive** than Serper ($25/1K vs $1/1K). The 250/month free tier is the smallest of all options. No advantage over Serper.dev since both query Google.

---

## Summary

| API | Quality for Lead Mining | Free Quota | Cost at Scale | Code Change | Verdict |
|-----|------------------------|------------|---------------|-------------|---------|
| Google CSE | Best | Dead (new users blocked) | $5/1K | Current code | Cannot use |
| **Serper.dev** | **Best (real Google)** | **2,500 one-time** | **$1/1K** | **~15 lines** | **Best choice** |
| Brave Search | Acceptable | ~1,000/month | $5/1K | ~20 lines | OK backup |
| SerpApi | Best (real Google) | 250/month | $25/1K | ~15 lines | Too expensive |
