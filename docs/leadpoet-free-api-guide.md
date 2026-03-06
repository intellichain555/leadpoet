# Leadpoet (SN71) Miner: Free API Tier Feasibility Guide

**Date:** 2026-02-27
**Miner code:** `/home/ubuntu/leadpoet`
**API config:** `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/.env`

---

## TL;DR — Can You Mine With Free APIs?

| API | Free Tier | Miner Daily Usage | Verdict |
|-----|-----------|-------------------|---------|
| Firecrawl | 500 credits ONE-TIME (not monthly) | ~1 call/day (default config) | Works for ~2 weeks with defaults, then dead |
| Google CSE | Dead for new users (Jan 2026) | 0 calls/day (bypassed in default config) | Not needed — default config skips it |
| OpenRouter | 50 req/day free (or 1,000/day with $10 deposit) | 100-150 calls/day (validator requests) | **WILL NOT WORK** on 50/day limit. Needs $10 deposit for 1,000/day |

**Bottom line:** Free APIs alone will NOT sustain mining. The minimum viable setup costs **$10 one-time** (OpenRouter deposit) plus either **$9/month** (Firecrawl Hobby) or self-hosting Firecrawl. Google CSE is not needed.

---

## 1. Firecrawl (firecrawl.dev)

### What the Miner Uses It For
- Scrapes company websites to extract structured lead data (company name, team members, contact info)
- Uses the `/scrape` endpoint with **LLM extraction** (JSON schema + prompt) — this costs more credits than a plain scrape
- File: `miner_models/lead_sorcerer_main/src/crawl.py`

### Free Tier Limits
| Metric | Value |
|--------|-------|
| Credits | **500 total, ONE-TIME** (not monthly, never renews) |
| Concurrent browsers | 2 |
| Rate limit (scrape) | 10 requests/minute |
| Rate limit (crawl) | 1 request/minute |
| Rate limit (search) | 5 requests/minute |

### Miner Consumption (Default Config)
The default `icp_config.json` has a single `specific_url` and 14-day caching:
- **Day 1:** 1 Firecrawl scrape call (with LLM extraction = ~5 credits)
- **Days 2-14:** 0 calls (cache hit)
- **Average:** ~0.36 credits/day with default single-URL config

With default config, 500 free credits would last **months**. But the default config only scrapes 1 hardcoded URL (`founderadvisors.tech`), which is useless for real mining.

### Miner Consumption (Real Mining Config)
To actually generate diverse leads, you'd add multiple search queries and remove `specific_urls`:
- ~5-20 new domain scrapes per day (after dedup/caching)
- Each LLM extraction scrape = ~5 credits
- **25-100 credits/day**
- 500 free credits = **5-20 days** then you're done forever

### Options After Free Credits Run Out

| Option | Cost | Credits | Notes |
|--------|------|---------|-------|
| Hobby plan | $9/month (annual) or $16/month | 3,000/month | 5 concurrent, enough for casual mining |
| Standard plan | $49/month | 50,000/month | 10 concurrent, serious mining |
| **Self-host** (open source) | Server cost only | **Unlimited** | Firecrawl is open source — you can run it yourself |

### Self-Hosting Firecrawl
Firecrawl is fully open source: https://github.com/mendableai/firecrawl

You can run it on the same server as the miner:
```bash
git clone https://github.com/mendableai/firecrawl.git
cd firecrawl
docker compose up -d
```
Then set `FIRECRAWL_BASE_URL=http://localhost:3002` in your environment. **Unlimited scrapes, zero API cost.** However, the LLM extraction feature requires your own LLM backend (or you can modify the miner to use plain scraping + your own LLM).

### Recommendation
- **Start with free 500 credits** to test the miner works
- **Then either self-host** (if comfortable with Docker) **or get the $9/month Hobby plan**

---

## 2. Google Custom Search Engine (GSE)

### What the Miner Uses It For
- Discovers company domains by searching Google for ICP-matching businesses
- File: `miner_models/lead_sorcerer_main/src/domain.py`

### Critical News: GSE Is Dead for New Users (Jan 2026)
Google **discontinued the Custom Search JSON API for new customers** in January 2026:
- New users **cannot sign up** for the JSON API
- The free Programmable Search widget is now limited to 50 domains (no full-web search)
- Existing users get 100 queries/day free until Jan 2027 migration deadline

### Does the Miner Need It?
**NO — with the default config, GSE is completely bypassed.**

The bypass logic (in `orchestrator.py` lines 235-265):
- When `specific_urls` is set in `icp_config.json`, domain discovery is skipped entirely
- The miner uses the hardcoded URLs instead of searching Google
- **Result: 0 GSE API calls**

### What If You Want Domain Discovery?
If you remove `specific_urls` to enable automatic domain discovery, you need a search API. Since GSE is dead for new users, alternatives:

| Alternative | Free Tier | Cost |
|-------------|-----------|------|
| **Brave Search API** | 2,000 queries/month | $5/month for 20K queries |
| **SerpApi** | 100 searches/month | $50/month for 5K |
| **Serper.dev** | 2,500 queries (one-time) | $50/month for 50K |
| **Bing Web Search API** | 1,000 queries/month | $7/1K queries |

You'd need to modify `domain.py` to swap the `GSESearchClient` class — it's isolated and easy to replace. The miner just needs results with `link`, `title`, and `snippet` fields.

### Recommendation
- **Don't set up GSE at all** — leave it blank, use `specific_urls` mode
- If you need domain discovery later, use Brave Search API (2,000 free/month)
- Set dummy values in `.env` to avoid startup errors: `GSE_API_KEY=not_used` and `GSE_CX=not_used`

---

## 3. OpenRouter (openrouter.ai)

### What the Miner Uses It For

**Two separate use cases with different models:**

#### A. Domain Scoring (only when GSE is active)
- Scores discovered domains against ICP
- Model: `gpt-4o-mini` (primary), `gpt-3.5-turbo` (fallback)
- **BYPASSED in default config** (no domain discovery = no scoring)
- File: `domain.py`

#### B. Validator Request Handling (always active)
When a validator queries your miner, 2-3 LLM calls happen:

| Function | Model | Purpose | Calls |
|----------|-------|---------|-------|
| `classify_industry()` | gpt-4o-mini | Map buyer description to industry | 1 per request |
| `classify_roles()` | gpt-4o-mini | Extract requested job roles | 0-1 per request |
| `rank_leads()` | o3-mini:online | Score/rank leads for buyer ICP | 1 per request |

File: `intent_model.py`

### Free Tier Limits

| Tier | Daily Limit | Rate Limit | Models |
|------|-------------|------------|--------|
| Free (no purchase) | **50 requests/day** | 20 RPM | 29 free models only |
| Free (with $10+ deposit) | **1,000 requests/day** | 20 RPM | 29 free models + paid with credits |

### Miner Consumption
- ~2-3 calls per validator request
- With ~50 validator requests/day: **100-150 OpenRouter calls/day**
- **50/day free limit is NOT enough**
- **1,000/day limit (with $10 deposit) IS enough**

### The Model Problem

The miner defaults to **paid models**:
- `gpt-4o-mini` — $0.15/$0.60 per million tokens (cheap but not free)
- `o3-mini:online` — $1.10/$4.40 per million tokens (expensive, web-search-augmented)

Free OpenRouter models that could work:

| Free Model | Quality | Good For |
|------------|---------|----------|
| `qwen/qwen3-235b-a22b:free` | High | Lead ranking (replace o3-mini) |
| `meta-llama/llama-3.3-70b-instruct:free` | High | Lead ranking |
| `google/gemma-3-27b-it:free` | Medium | Industry/role classification |
| `mistralai/mistral-small-3.1-24b-instruct:free` | Medium | Classification |

### How to Use Free Models
Set environment variables in `.env`:
```bash
LEADSORCERER_PRIMARY_MODEL=qwen/qwen3-235b-a22b:free
LEADSORCERER_FALLBACK_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

**Caveat:** The `rank_leads()` function in `intent_model.py` uses a separate hardcoded default of `openai/o3-mini:online` (line 198). The env var override applies to this too, but check if the `:online` web search feature is critical for ranking quality. Free models don't support `:online`.

### Cost Estimates

| Scenario | Daily Cost |
|----------|-----------|
| Free models + $10 deposit | $0.00/day (free models, 1000/day limit) |
| gpt-4o-mini only | ~$0.01-0.05/day |
| Default config (gpt-4o-mini + o3-mini:online) | ~$0.05-0.30/day |

### Recommendation
1. **Deposit $10 on OpenRouter** to unlock 1,000 req/day for free models
2. **Set models to free tier:**
   ```
   LEADSORCERER_PRIMARY_MODEL=qwen/qwen3-235b-a22b:free
   LEADSORCERER_FALLBACK_MODEL=meta-llama/llama-3.3-70b-instruct:free
   ```
3. The $10 deposit also gives you credits for occasional paid model use if needed
4. **Alternative:** Point `OPENROUTER_BASE_URL` to a local LLM or Chutes API for zero cost

---

## 4. Minimum Viable Free Setup

### `.env` Configuration
```bash
# Google Search — NOT NEEDED (bypassed in default config)
GSE_API_KEY=not_used
GSE_CX=not_used

# OpenRouter — sign up, deposit $10, use free models
OPENROUTER_KEY=sk-or-v1-your-key-here
LEADSORCERER_PRIMARY_MODEL=qwen/qwen3-235b-a22b:free
LEADSORCERER_FALLBACK_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Firecrawl — sign up for free 500 credits
FIRECRAWL_KEY=fc-your-key-here

# Data directory
LEADPOET_DATA_DIR=./data
```

### Total Cost

| Item | Cost | Frequency |
|------|------|-----------|
| OpenRouter deposit | $10 | One-time (unlocks 1,000/day free) |
| Firecrawl free tier | $0 | 500 credits total, then need plan |
| Google CSE | $0 | Not used |
| **Total to start** | **$10** | One-time |

### After Firecrawl Free Credits Run Out

| Option | Monthly Cost |
|--------|-------------|
| Self-host Firecrawl (Docker) | $0 |
| Firecrawl Hobby plan | $9-16/month |

---

## 5. Risks and Limitations of Free Tier Mining

### Performance Risk
- **Free OpenRouter models are deprioritized** during peak times — slower responses
- Lead ranking quality may be lower with free models vs o3-mini
- Lower quality rankings = lower reputation scores = less emission

### Rate Limit Risk
- 1,000 req/day limit on OpenRouter (with $10 deposit) should be enough for ~300-500 validator requests/day
- If the subnet gets busier, you might hit limits
- Free models have **no SLA** — they can be removed or rate-limited without notice

### Firecrawl Sustainability
- 500 one-time credits is a trial, not a plan
- For real mining with diverse domains, you'll burn through them in days
- Self-hosting is the only truly free long-term option, but requires Docker setup

### Quality vs Cost Tradeoff
The miner's emission depends on lead quality scores (0-48 points). Using weaker free LLMs for ranking could mean:
- Less accurate ICP matching
- Lower reputation scores per lead
- Less emission compared to miners using paid models
- However, the scoring is done by **validators**, not your LLM — your LLM just ranks which leads to return. The actual quality depends on the leads you source, not your ranking model.

---

## 6. Where to Get API Keys

### Firecrawl
1. Go to https://www.firecrawl.dev/
2. Sign up (no credit card needed)
3. Go to Dashboard > API Keys
4. Copy key (starts with `fc-`)

### OpenRouter
1. Go to https://openrouter.ai/
2. Sign up (no credit card needed for free models)
3. Go to Settings > API Keys > Create Key
4. Deposit $10 via Settings > Credits to unlock 1,000/day limit
5. Copy key (starts with `sk-or-v1-`)

### Google CSE (NOT NEEDED)
- Skip this entirely — the miner bypasses it in default config
- Set `GSE_API_KEY=not_used` and `GSE_CX=not_used` in `.env`

---

## 7. Where to Put the Keys

All keys go in one file:

**`/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/.env`**

```bash
# Google Search — not used
GSE_API_KEY=not_used
GSE_CX=not_used

# OpenRouter
OPENROUTER_KEY=sk-or-v1-xxxxxxxxxxxx

# Firecrawl
FIRECRAWL_KEY=fc-xxxxxxxxxxxx

# Free model overrides
LEADSORCERER_PRIMARY_MODEL=qwen/qwen3-235b-a22b:free
LEADSORCERER_FALLBACK_MODEL=meta-llama/llama-3.3-70b-instruct:free

# Data directory
LEADPOET_DATA_DIR=./data
```

---

## 8. Summary Table

| API | Required? | Free Tier Viable? | Minimum Cost | Notes |
|-----|-----------|-------------------|--------------|-------|
| Firecrawl | Yes | Short-term only (500 credits) | $0 start, then $9/month or self-host | Self-hosting is free forever |
| Google CSE | No | N/A (bypassed) | $0 | Dead for new users anyway |
| OpenRouter | Yes | With $10 deposit only | $10 one-time | Free models work, 1000 req/day |
| **Total** | | | **$10 one-time + $0-9/month** | |
