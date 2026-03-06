# Leadpoet Miner API Usage Analysis

**Date:** 2026-02-27
**Codebase:** /home/ubuntu/leadpoet

---

## Executive Summary

The Leadpoet miner uses three paid APIs in a pipeline: Google Custom Search (GSE) for domain discovery, Firecrawl for website scraping/extraction, and OpenRouter for LLM scoring/classification. The miner runs a **continuous sourcing loop** (default interval: 60 seconds) that calls `get_leads(1)` each iteration, generating 1 lead per cycle.

**Critical finding:** With the default `icp_config.json` (which includes `specific_urls`), GSE search is **bypassed entirely**. This makes Firecrawl and OpenRouter the only per-lead costs in default mode.

---

## 1. Firecrawl Usage

### Files and Locations
- **Main client:** `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/crawl.py`
  - `CrawlTool.__init__` (line 207-214) -- client initialization
  - `_extract_single_company` (line 1321-1473) -- single-company scrape
  - `_extract_database_site` (line 1475-1598) -- multi-URL database scrape

### Endpoint Used
- **`firecrawl_client.scrape()`** -- the Firecrawl v2 scrape endpoint with JSON extraction format
- NOT using `crawl` or `search` endpoints

### Pages Scraped Per Domain/Lead

**Standard single-company mode** (line 1363-1399):
- **1 scrape call per domain** -- only the primary URL (`urls_to_extract[0]`)
- The code builds 3 URLs (homepage, /about, /contact) via `_build_extraction_urls()` (lines 356-364) but only the **first URL** is actually scraped (line 1366-1368: `"url": urls_to_extract[0]`)
- Comment at line 56: "COST OPTIMIZED - SINGLE SCRAPE OPERATION"
- Uses `formats: [{"type": "json", "schema": ..., "prompt": ...}]` for structured extraction

**Database site mode** (line 1475-1598):
- **1 scrape call per specific URL** -- iterates over all URLs in `urls_to_extract`
- Only triggered when `site_type == "information_database"` (requires explicit ICP config)
- Not the default path

### Caching
- 14-day artifact cache (line 1077-1079: `crawl_ttl_days` defaults to 14)
- Content hash verification for freshness (line 1095-1099)
- Firecrawl's own `max_age: 172800` (2-day server-side cache, line 1379)

### Credits Per Run

With default `icp_config.json` settings:
- `max_domains_per_run = 20` (icp_config.json line 44), but...
- Sourcing loop calls `get_leads(1)` which sets `max_domains_per_run = min(max(1*2, 5), 20) = 5` (main_leads.py line 316-317)
- With `specific_urls: ["https://www.founderadvisors.tech/"]`, bypass mode creates 1 lead record from the URL
- **Result: 1 Firecrawl scrape call per sourcing cycle** (unless cache hit)

**Cost per scrape:** The `costs.yaml` tracks $0.001 per extract. Actual Firecrawl pricing for scrape+JSON extraction is approximately **1 credit** per scrape (Firecrawl credits vary by plan; scrape with LLM extraction costs more than plain scrape).

### Scrape Parameters (line 1365-1382)
```python
scrape_params = {
    "url": urls_to_extract[0],
    "formats": [{"type": "json", "schema": FIRECRAWL_EXTRACT_SCHEMA, "prompt": full_prompt}],
    "wait_for": 5000,           # 5s JS render wait
    "only_main_content": False,
    "max_age": 172800,          # 2-day server cache
    "block_ads": True,
    "remove_base64_images": True,
}
```

Note: The `formats: [{"type": "json", ...}]` with a schema+prompt triggers Firecrawl's **LLM extraction** feature, which typically costs more credits than a plain scrape.

---

## 2. Google Search (GSE) Usage

### Files and Locations
- **GSE client:** `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/domain.py`
  - `GSESearchClient` class (lines 66-98)
  - `_search_query` method (lines 618-666)
  - `_search_and_score_domains` method (lines 668-714)
  - `DomainTool.run()` (lines 884-1005)

### API Called
- **Google Custom Search JSON API v1** (`https://www.googleapis.com/customsearch/v1`)
- Requires `GSE_API_KEY` and `GSE_CX` environment variables

### Queries Per Run

**Default config has `specific_urls` set, so GSE is BYPASSED entirely.**

The bypass logic is in `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/orchestrator.py`:
- `should_bypass_domain_discovery()` (lines 235-265): Returns `True` when `specific_urls` is non-empty
- `_run_traditional_pipeline()` (lines 398-513): Skips `domain_tool.run()` entirely in bypass mode

**If GSE were used** (no specific_urls):
- Default queries in icp_config.json: 2 queries (lines 4-7)
- `search.max_pages = 5` (line 33), but `mode: "fast"` caps it to `min(1, max_pages) = 1` page (domain.py line 484)
- Each page = 1 GSE API call returning 10 results
- **Total: 2 queries x 1 page = 2 GSE API calls per run** (in fast mode)
- In "thorough" mode: 2 queries x 5 pages = **10 GSE API calls per run**

### What It Searches For
- Queries from icp_config.json (e.g., "startup advisory services founder contact", "business consulting firm advisor email")
- Results are used to discover company domains for subsequent crawling

### Is It Critical?
- **NO in default config** -- bypassed when specific_urls are provided
- **YES if you remove specific_urls** -- it becomes the only domain discovery mechanism
- Could be replaced with any search API (Serper, Brave, SearXNG) by swapping the `GSESearchClient` class

### Cost
- `costs.yaml`: $0.0005 per request
- Google CSE free tier: 100 queries/day free, then $5 per 1,000 queries ($0.005 each)
- In default bypass mode: **$0/day for GSE**

---

## 3. OpenRouter (LLM) Usage

### Files and Locations

LLM calls happen in **two separate modules**:

#### A. Domain Scoring (domain.py)
- **File:** `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/domain.py`
- **Class:** `LLMScorer` (lines 106-220)
- **Models:**
  - Primary: `LEADSORCERER_PRIMARY_MODEL` env var, default `"gpt-4o-mini"` (line 115)
  - Fallback: `LEADSORCERER_FALLBACK_MODEL` env var, default `"gpt-3.5-turbo"` (line 116)
- **Base URL:** `OPENROUTER_BASE_URL` env var, default `"https://openrouter.ai/api/v1"` (line 112)
- **Purpose:** Score each discovered domain against the ICP (0-1 score + reason + flags)
- **Calls per run:** 1 LLM call per unique domain from GSE results (deduplicated, line 741-742)
- **BYPASSED in default mode** (specific_urls skip domain discovery entirely)

#### B. Intent Model / Lead Ranking (intent_model.py)
- **File:** `/home/ubuntu/leadpoet/miner_models/intent_model.py`
- **Models (lines 198-203):**
  - Primary: `LEADSORCERER_PRIMARY_MODEL` env var, default `"openai/o3-mini:online"`
  - Fallback: `LEADSORCERER_FALLBACK_MODEL` env var, default `"deepseek/deepseek-r1:online"`
  - Classification: `"openai/gpt-4o-mini"` (hardcoded, line 203)
- **Three LLM functions:**

  1. **`classify_industry()`** (lines 46-128)
     - Called when: Validator sends a request with `business_desc`
     - Models: `gpt-4o-mini` (primary), then fallback model
     - Purpose: Map buyer description to industry category
     - **1 LLM call per validator request** (with fallback)

  2. **`classify_roles()`** (lines 519-600)
     - Called when: Buyer description contains role keywords
     - Models: `gpt-4o-mini` (primary), then fallback model
     - Purpose: Extract requested roles from buyer text
     - **0-1 LLM call per validator request** (only if roles detected)

  3. **`_score_batch()` / `rank_leads()`** (lines 233-323, 422-459)
     - Called when: Leads need ranking before returning to validator
     - Models: `openai/o3-mini:online` (primary), `deepseek/deepseek-r1:online` (fallback)
     - Purpose: Score all leads in a single batch prompt against buyer ICP
     - **1 LLM call per ranking batch** (all leads scored in single prompt)
     - Uses `:online` suffix which means web-search-augmented models (more expensive)

### Total LLM Calls Per Cycle

**Sourcing loop** (every 60 seconds):
- Calls `get_leads(1)` which runs the orchestrator pipeline
- With specific_urls bypass: **0 LLM calls for domain scoring** (domain tool skipped)
- The Firecrawl extraction uses Firecrawl's built-in AI, NOT OpenRouter
- **Result: 0 OpenRouter calls per sourcing cycle**

**Validator request** (on-demand, when validator queries miner):
- 1x `classify_industry()` = **1 LLM call** (gpt-4o-mini)
- 0-1x `classify_roles()` = **0-1 LLM call** (gpt-4o-mini, conditional)
- 1x `rank_leads()` -> `_score_batch()` = **1 LLM call** (o3-mini:online or deepseek-r1:online)
- **Total: 2-3 OpenRouter calls per validator request**

### Model Costs (OpenRouter pricing, approximate)
| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| openai/gpt-4o-mini | $0.15/M tokens | $0.60/M tokens | Used for classification |
| openai/o3-mini:online | $1.10/M tokens | $4.40/M tokens | With web search, used for ranking |
| deepseek/deepseek-r1:online | $0.55/M tokens | $2.19/M tokens | Fallback for ranking |

### Could Free Models Work?
- **For classification** (industry/role): Yes, free models like `meta-llama/llama-3.1-8b-instruct:free` could handle simple JSON extraction
- **For lead ranking**: Possibly, but quality matters for scoring accuracy. The `:online` (web-search) feature is not available on free models
- Environment variables `LEADSORCERER_PRIMARY_MODEL` and `LEADSORCERER_FALLBACK_MODEL` make it easy to swap models
- Base URL is also configurable via `OPENROUTER_BASE_URL`, allowing Chutes.ai or other providers

---

## 4. Daily Consumption Estimates

### Scenario A: Default Config (specific_urls mode)

**Sourcing loop runs every 60 seconds with `get_leads(1)`:**

| Metric | Value |
|--------|-------|
| Cycles per day | 1,440 (24h x 60min) |
| Firecrawl scrapes per cycle | 1 (unless cached) |
| Firecrawl cache TTL | 14 days |
| Effective Firecrawl calls/day | ~1 (same URL re-cached) |
| GSE calls per cycle | 0 (bypassed) |
| OpenRouter calls per cycle | 0 (no domain scoring in pipeline) |

Since the default config only has 1 specific URL (`https://www.founderadvisors.tech/`), and the cache TTL is 14 days:
- **Day 1:** 1 Firecrawl call, then cached for 14 days
- **Days 2-14:** 0 Firecrawl calls (cache hits)
- **Average: ~0.07 Firecrawl calls/day**

**Validator requests** (on-demand, not scheduled):
- Per request: 2-3 OpenRouter calls
- Frequency depends entirely on validator behavior (could be 0-100+/day)
- Estimated token usage per request: ~500-1000 input tokens, ~200 output tokens

### Scenario B: Custom Config (GSE-based domain discovery, no specific_urls)

**Sourcing loop runs every 60 seconds with `get_leads(1)`:**

| Metric | Per Cycle | Per Day (1,440 cycles) |
|--------|-----------|----------------------|
| GSE API calls | 2 (fast mode) | 2,880 |
| Unique domains discovered | ~10-20 | ~14,400-28,800 (with dedup much less) |
| LLM scoring calls (domain) | ~10-20 per cycle | ~14,400-28,800 |
| Firecrawl scrapes | ~5 (passing domains) | ~7,200 |

**BUT**: Domain history deduplication and SERP cache (24h TTL) dramatically reduce this:
- After first cycle, most domains are already known (domain_ttl_days=180)
- GSE results cached for 48 hours (domain_serp_ttl_hours=48 in default config)
- Realistic after warm-up: ~10-50 new API calls/day total

### Scenario C: Validator Request Costs

| API | Calls | Est. Cost |
|-----|-------|-----------|
| classify_industry | 1x gpt-4o-mini | ~$0.0001 |
| classify_roles | 0-1x gpt-4o-mini | ~$0.0001 |
| rank_leads (batch) | 1x o3-mini:online | ~$0.001-0.005 |
| **Total per request** | 2-3 calls | **~$0.001-0.006** |

With 50 validator requests/day: **~$0.05-0.30/day for LLM**

---

## 5. Summary: API Call Flow Per Lead

### Path 1: Sourcing Loop (Background, Every 60s)

```
get_leads(1)
  -> orchestrator.run_pipeline()
    -> IF specific_urls present:
         BYPASS domain discovery (0 GSE, 0 LLM calls)
         Create lead records from URLs
       ELSE:
         domain_tool.run()
           -> GSE: 2 queries x 1 page = 2 API calls
           -> LLM (gpt-4o-mini): 1 call per unique domain (~10-20)
    -> crawl_tool.run()
         -> Firecrawl scrape: 1 call per passing domain (cache check first)
  -> convert to legacy format
  -> submit to gateway
```

### Path 2: Validator Request (On-Demand)

```
forward(synapse) or handle_lead_request(request)
  -> classify_industry(business_desc)        # 1 LLM call (gpt-4o-mini)
  -> classify_roles(business_desc)           # 0-1 LLM call (gpt-4o-mini)
  -> get_leads_from_pool()                   # No API calls (local pool)
  -> IF pool empty:
       get_leads(num_leads * 2)              # Full pipeline (see Path 1)
  -> rank_leads(leads, description)          # 1 LLM call (o3-mini:online)
  -> return top leads
```

---

## 6. Key Configuration Files

| File | Purpose |
|------|---------|
| `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/icp_config.json` | ICP definition, queries, caps, thresholds |
| `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/config/costs.yaml` | Internal cost tracking per API |
| `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/domain.py` | GSE search + LLM domain scoring |
| `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/crawl.py` | Firecrawl website extraction |
| `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/src/orchestrator.py` | Pipeline coordinator |
| `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/main_leads.py` | Integration wrapper |
| `/home/ubuntu/leadpoet/miner_models/intent_model.py` | LLM-based lead ranking/classification |
| `/home/ubuntu/leadpoet/neurons/miner.py` | Miner entry point, sourcing loop |

## 7. Environment Variables

| Variable | Required | Used By | Default |
|----------|----------|---------|---------|
| `FIRECRAWL_KEY` | Yes | crawl.py | None |
| `GSE_API_KEY` | Yes* | domain.py | None |
| `GSE_CX` | Yes* | domain.py | None |
| `OPENROUTER_KEY` | Yes | domain.py, intent_model.py | None |
| `OPENROUTER_BASE_URL` | No | domain.py, intent_model.py | `https://openrouter.ai/api/v1` |
| `LEADSORCERER_PRIMARY_MODEL` | No | domain.py, intent_model.py | `gpt-4o-mini` (domain), `openai/o3-mini:online` (intent) |
| `LEADSORCERER_FALLBACK_MODEL` | No | domain.py, intent_model.py | `gpt-3.5-turbo` (domain), `deepseek/deepseek-r1:online` (intent) |

*GSE keys are required by the code but not actually used when specific_urls bypass is active.

---

## 8. Cost Optimization Opportunities

1. **GSE is already bypassed** in default config -- no savings needed there
2. **Firecrawl** effectively makes ~1 call per 14 days with default single URL -- minimal cost
3. **OpenRouter is the main cost driver** during validator requests:
   - Replace `o3-mini:online` with cheaper model for ranking
   - Use `OPENROUTER_BASE_URL` to point to Chutes.ai or local LLM
   - Classification could use free models since it's simple JSON extraction
4. **For serious mining** (multiple URLs/queries), Firecrawl LLM extraction at scale is the biggest cost concern -- consider self-hosted alternatives or Firecrawl's Growth plan
