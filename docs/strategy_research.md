# Strategy Research

Scoring rules, ICP definitions, and strategic parameters that drive lead quality evaluation.
All values here are the source of truth — code references are provided for each rule.

---

## 1. ICP Definitions & Bonuses

ICP (Ideal Customer Profile) segments define high-value lead targets. Leads matching an ICP receive bonus points during scoring.

**Code**: `validator_models/checks_icp.py:27-317`

### ICP #1: AI/ML/NLP + Robotics/Aerospace/Defence — Decision Makers (+100)

- **Sub-industries**: Artificial Intelligence, Machine Learning, Natural Language Processing, Predictive Analytics, Robotics, Autonomous Vehicles, Aerospace, Defense and Space, Drones
- **Roles**: CEO, CTO, COO, CFO, CMO, Chief AI Officer, Chief Data Officer, Chief Product Officer, VP/Director of Engineering/AI/ML/Product/Technology/Research, Software Engineers (all levels)
- **Restrictions**: None (global)
- **Bonus**: +100

### ICP #2: Cyber Security / IT Mgmt — Midwest US, 10-50 employees (+100)

- **Sub-industries**: Cyber Security, IT Management
- **Roles**: Owner, Co-owner, Business Owner, Founder, Co-founder, CEO, President
- **Regions**: Illinois, Indiana, Michigan, Ohio, Wisconsin, Iowa, Kansas, Minnesota, Missouri, Nebraska, North Dakota, South Dakota
- **Employee range**: 10-50
- **Bonus**: +100

### ICP #3: Cyber Security — Decision Makers, all US (+50)

- **Sub-industries**: Cyber Security, Network Security, IT Management, Information Services
- **Roles**: C-Suite (CEO, CTO, COO, CISO, CIO), VP/Director of Security/IT/Engineering, Owner
- **Regions**: All US states
- **Bonus**: +50 (default)

### ICP #4: UAE/Dubai Investors (+100)

- **Sub-industries**: Angel Investment, Asset Management, Hedge Funds, Impact Investing, Incubators, Real Estate Investment, Venture Capital, Web3 Investor, Web3 Fund, Wealth Management
- **Roles**: Partners (GP, Managing, Venture, Investment, Limited), Portfolio/Fund/Investment/Asset Manager, C-Suite, Investor, VC, Wealth Manager, Private Banker, Family Office roles
- **Regions**: United Arab Emirates, UAE, Dubai, Emirati
- **Bonus**: +100

### ICP #5: Small/Local Businesses — Owners, US only (+50)

- **Sub-industries**: Local Business, Local, Retail, Restaurants, Food and Beverage, Professional Services, Home Services, Real Estate, Construction, Automotive, Health Care, Fitness, Beauty, Consulting
- **Roles**: Owner, Co-owner, Business Owner, Sole Proprietor, Franchise Owner, Franchisee, Store/Shop Owner, Founder, CEO, President, Managing Director, Principal, Partner, Proprietor, Operator, Entrepreneur
- **Regions**: All US states
- **Bonus**: +50 (default)

### ICP #6: Blockchain/Crypto/Web3 — Investors & Leaders (+100)

- **Sub-industries**: Blockchain, Cryptocurrency, Bitcoin, Ethereum, Web3 Investor, Web3 Fund
- **Roles**: Partners, Portfolio/Fund/Investment managers, C-Suite, Investor, VC, Token/Crypto Fund Manager, DeFi Lead, Web3 Investor
- **Restrictions**: None (global)
- **Bonus**: +100

### ICP #7: Biotech/Pharma — Decision Makers (+50)

- **Sub-industries**: Biotechnology, Biopharma, Pharmaceutical, Genetics, Life Science, Bioinformatics, Clinical Trials
- **Roles**: C-Suite (CEO, CTO, COO, CFO, CSO, CMO, Chief Commercial Officer), VP/Director of R&D/Clinical/Regulatory/BD, BD/Licensing roles
- **Restrictions**: None (global)
- **Bonus**: +50 (default)

### ICP #8: Wealth Mgmt / VC / Hedge Funds (+100)

- **Sub-industries**: Asset Management, Venture Capital, Hedge Funds, Financial Services, Impact Investing
- **Roles**: Leadership (CEO, MD, Partner, Founder), Investment (CIO, Portfolio/Fund Manager, Investment Analyst), Private Markets (PE, Real Estate, Infrastructure), Operations & Finance, Wealth roles
- **Restrictions**: None (global)
- **Bonus**: +100

### ICP #9: FinTech/Banking/Payments — Decision Makers (+50)

- **Sub-industries**: FinTech, Banking, Payments, Financial Services, Credit Cards, Mobile Payments, Transaction Processing
- **Roles**: C-Suite, Risk & Compliance Leadership (CRO, CCO, VP/Director of Risk/Compliance), Compliance Operations
- **Restrictions**: None (global)
- **Bonus**: +50 (default)

### ICP #10: Robotics / Aerospace / Defence — Technical & Leadership (+50)

- **Sub-industries**: Robotics, Autonomous Vehicles, Aerospace, Defense and Space, Drones, 3D Printing
- **Roles**: C-Suite, VP/Director of Engineering, Engineers (Software, Mechanical, Systems, Robotics, Aerospace)
- **Restrictions**: None (global)
- **Bonus**: +50 (default)

---

## 2. Enterprise Company Rules

**Code**: `validator_models/checks_icp.py:838-867`, `validator_models/automated_checks.py:1000-1046`

Enterprise = employee count minimum >= 10,001.

Rep score is capped for enterprise companies to discourage low-effort scraping of large, well-known companies:

| Condition | Rep Score Cap |
|-----------|---------------|
| Enterprise + ICP match | 10 points max |
| Enterprise + no ICP match | 5 points max |

Formula: `final_rep = raw_rep + min(0, target - raw_rep)`

---

## 3. Rep Score Components

**Code**: `validator_models/automated_checks.py:54`

**MAX_REP_SCORE = 48** (sum of all components)

### Typical Rep Score Range (subnet71.com, 2026-03-02)

| Metric | Rep Score |
|--------|-----------|
| Theoretical max | 48 |
| Best operator avg | 31.6 |
| Subnet-wide avg | 25.0 |
| Median operator | 25.5 |
| Lowest operator avg | 10.8 |
| Enterprise cap (no ICP) | 5 |
| Enterprise cap (with ICP) | 10 |

**Normal range for a good lead: 20–35 rep.** Most accepted leads from top operators land in this band. Scores above 35 require hitting multiple high-value components (SEC filings + GDELT press + Companies House + strong WHOIS). Scores below 15 typically come from small/new companies with no public records.

| Component | Max Points | Source |
|-----------|-----------|--------|
| Wayback Machine | 6 | Archive snapshots + age bonus |
| SEC EDGAR | 12 | Filing count tiers |
| WHOIS/DNSBL | 10 | Stability (3) + Registrant (3) + Hosting (3) + DNSBL (1) |
| GDELT Press | 10 | Press wire (5) + Trusted domain (5) mentions |
| Companies House | 10 | Exact/close match + active/inactive status |

### Wayback Scoring Tiers

| Snapshots | Score |
|-----------|-------|
| <10 | min(1.2, snapshots x 0.12) |
| 10-50 | 1.8 + (snapshots - 10) x 0.03 |
| 50-200 | 3.6 + (snapshots - 50) x 0.008 |
| >200 | 5.4 + min(0.6, (snapshots - 200) x 0.0006) |
| Age >= 5 years | +0.6 bonus |

### SEC Filing Tiers

| Filings | Score |
|---------|-------|
| 1-5 | min(3.6, filings x 0.72) |
| 6-20 | 7.2 |
| 21-50 | 9.6 |
| 50+ | 12.0 |

### WHOIS/DNSBL Breakdown

- **WHOIS Stability** (0-3): >=180 days since update = 3, >=90 = 2, >=30 = 1, <30 = 0
- **Registrant Consistency** (0-3): 3+ corporate signals = 3, 2 = 2, 1 = 1, 0 = 0
- **Hosting Provider** (0-3): Reputable (AWS, Google, Cloudflare, Azure) = 3, else 0
- **DNSBL** (0-1): Not blacklisted = 1, Blacklisted = 0

### GDELT Mention Tiers (same for press wire and trusted domain)

| Mentions | Score (each bucket) |
|----------|-----|
| 10+ | 5.0 |
| 5-9 | 4.0 |
| 3-4 | 3.0 |
| 1-2 | 2.0 |
| 0 | 0 |

### Companies House

| Match | Score |
|-------|-------|
| Exact match + active | 10.0 |
| Exact match + inactive | 8.0 |
| Close match + active | 8.0 |
| Close match + inactive | 6.0 |

---

## 4. Company Size Adjustments

**Code**: `validator_models/checks_icp.py:870-1089`

### Small Company Bonuses

| Condition | Bonus |
|-----------|-------|
| <=10 employees in major hub | +50 |
| <=50 employees (anywhere) | +20 |

Major hubs: NYC, SF, LA, Austin, Chicago, Toronto, London, Berlin, Paris, Tokyo, Singapore, Hong Kong, Dubai, and others.

### Large Company Penalties

| Employee Count | Penalty |
|----------------|---------|
| 1,001-5,000 | -10 |
| 5,001-10,000 | -15 |
| 10,001+ (enterprise) | No ICP penalty (already capped by rep score) |

### Bonus Cap

- Dynamic cap: `max(50, icp_bonus)` if ICP bonus > 0, else 50
- Penalties stack after capping

---

## 5. Intent Signal Freshness

**Code**: `qualification/scoring/lead_scorer.py:617-637`

| Signal Age | Multiplier |
|------------|------------|
| <= 2 months | 1.0x (full credit) |
| <= 12 months | 0.5x |
| > 12 months | 0.25x |

### Date Requirements by Source

**Date NOT required** (full score allowed): GitHub, Company Website, Wikipedia, Review Sites

**Date IS required** (max 15 pts if undated, 0.5x decay): LinkedIn, Job Boards, News, Social Media

---

## 6. Source Quality Multipliers

**Code**: `qualification/scoring/lead_scorer.py:415-425`

| Source | Multiplier |
|--------|------------|
| LinkedIn | 1.0 |
| Job Board | 1.0 |
| GitHub | 1.0 |
| News | 0.9 |
| Company Website | 0.85 |
| Social Media | 0.8 |
| Review Site | 0.75 |
| Wikipedia | 0.6 |
| Other | 0.3 |

Applied as: `weighted_score = raw_score x (confidence / 100) x source_multiplier`

---

## 7. Fuzzy Match Thresholds

**Code**: `qualification/scoring/pre_checks.py:75-77`

| Field | Threshold |
|-------|-----------|
| Industry | 80% |
| Sub-industry | 70% |
| Role | 60% (more lenient for title variations) |

---

## 8. Lead Scoring Maximums

**Code**: `gateway/qualification/config.py`

| Component | Max Points |
|-----------|-----------|
| ICP Fit | 20 |
| Decision Maker | 30 |
| Intent Signal | 50 |
| **Total** | **100** |

---

## 9. Cost & Time Limits

**Code**: `gateway/qualification/config.py:48-50`

| Parameter | Limit |
|-----------|-------|
| Max cost per lead | $0.05 |
| Max time per lead | 15.0 seconds |
| Hard model timeout | 30.0 seconds |

### Variability Penalties

| Condition | Penalty |
|-----------|---------|
| Cost > 2x average ($0.10) | -5 points |
| Time > 2x average (30s) | -5 points |

---

## 10. Champion & Screening Rules

**Code**: `gateway/qualification/config.py:56-79`

| Parameter | Value |
|-----------|-------|
| Screening 1 threshold | 20% of max score |
| Screening 2 threshold | 40% of max score |
| Prune threshold | 10% of champion score |
| Dethroning threshold | +10% better than current champion |
| Minimum champion score | 10.0 / 100 |
| Rebenchmark time | 12:05 AM UTC daily |

---

## 11. Hardcoding & Fabrication Detection

| Check | Threshold |
|-------|-----------|
| Structural similarity | 70% (templated response detection) |
| Intent fabrication (confidence = 0) | Entire lead score = 0 |
| Intent verification confidence | >= 70% required |

---

## 12. Miner Performance Analysis (subnet71.com, 2026-03-02)

**Data source**: `https://www.subnet71.com/api/dashboard`

### Subnet-Wide Summary

| Metric | Value |
|--------|-------|
| Total submissions | 1,273,821 |
| Accepted | 1,027,060 (81%) |
| Rejected | 241,260 |
| Avg rep score | 25.0 |
| Unique miners | 112 |
| Active miners (>100 subs) | 108 |
| Latest epoch | 21,259 |

### Operator Landscape

108 active miners are controlled by 9 operators (grouped by coldkey). Performance is consistent within each operator's miners, confirming each runs a single strategy across all hotkeys.

| Rank | Coldkey | Miners | Total Subs | Per Miner | Acc Rate | Weighted Avg Rep |
|------|---------|--------|-----------|-----------|----------|-----------------|
| 1 | `5HgV..` | 28 | 295,855 | 10,566 | 75.4% | 31.6 |
| 2 | `5FNQ..` | 10 | 101,792 | 10,179 | 84.0% | 26.4 |
| 3 | `5Ebe..` | 10 | 118,474 | 11,847 | 85.0% | 25.5 |
| 4 | `5G1P..` | 10 | 116,655 | 11,665 | 85.2% | 25.3 |
| 5 | `5Eyg..` | 14 | 143,198 | 10,228 | 84.1% | 25.1 |
| 6 | `5EjZ..` | 10 | 94,957 | 9,495 | 84.9% | 24.4 |
| 7 | `5Hbt..` | 10 | 81,600 | 8,160 | 84.4% | 24.3 |
| 8 | `5DwF..` | 12 | 317,345 | 26,445 | 79.1% | 18.7 |
| 9 | `5DcE..` | 1 | 833 | 833 | 79.4% | 10.8 |

### Aggregate Rejection Reasons (all miners)

| Reason | Count | % of Rejections |
|--------|-------|-----------------|
| Invalid Role | 74,318 | 30.9% |
| Invalid Industry | 22,869 | 9.5% |
| Invalid Source URL | 19,935 | 8.3% |
| Invalid City | 18,758 | 7.8% |
| Invalid Website | 17,958 | 7.5% |
| Invalid Company | 17,552 | 7.3% |
| Invalid LinkedIn | 15,185 | 6.3% |
| Invalid Description | 11,895 | 4.9% |
| Invalid Email | 8,710 | 3.6% |
| Email Verification Error | 7,617 | 3.2% |

### Operator #1 vs Operator #8 — Rejection Reason Comparison

These two operators represent the highest-rep (31.6) and lowest-rep (18.7) multi-miner strategies.

| Reason | Operator #1 (`5HgV..`, rep=31.6) | Operator #8 (`5DwF..`, rep=18.7) |
|--------|----------------------------------|----------------------------------|
| Invalid Role | 18.3% | 37.8% |
| Invalid City | 12.1% | 8.2% |
| Invalid Website | 10.7% | 12.9% |
| Invalid Industry | 9.7% | 7.9% |
| Invalid Email | 9.4% | — |
| Invalid Company | 6.9% | — |
| Invalid Description | — | 8.4% |
| Invalid LinkedIn | — | 6.2% |

Key differences:
- Operator #8 has **2x the Invalid Role rejection rate** (37.8% vs 18.3%)
- Operator #8 runs **2.5x more volume per miner** (26,445 vs 10,566 subs/miner)
- Operator #1 has a **lower acceptance rate** (75.4% vs 79.1%) but **higher rep scores** — suggesting they submit harder-to-validate leads that score higher when accepted

### Acceptance Rate Distribution (active miners)

| Bracket | Miners |
|---------|--------|
| Below 70% | 3 |
| 70-80% | 35 |
| Above 80% | 70 |

### Rep Score Distribution (active miners)

| Metric | Value |
|--------|-------|
| Min | 10.8 |
| Median | 25.5 |
| Max | 37.4 |

### Data Limitations

The subnet71.com lead-search API exposes only `repScore`, `decision`, and `rejectionReason` per lead. It does **not** expose lead content (role, industry, company name, employee count, region, source type). Therefore:

- Rejection reason distributions and rep score aggregates are provable
- Operator grouping by coldkey is provable
- Volume and acceptance rate comparisons are provable
- Claims about specific targeting strategies (company size, ICP segment, role quality) **cannot be verified** from the public API — they would require direct database or gateway log access

---

## 13. Incentive Calculation Formula

**Code**: `neurons/validator.py:2720-3191`

### Per-Lead Scoring

Each approved lead earns an `effective_rep_score` for the miner:

```
effective_rep_score = max(0, rep_score + icp_adjustment)
```

- `rep_score`: 0-48 from automated checks (Section 3)
- `icp_adjustment`: -15 to +100 from ICP matching + company size adjustments (Sections 1, 4)
- Legacy format (old leads): `effective_rep_score = rep_score × icp_multiplier` (1.0 / 1.5 / 5.0)

**Code**: `neurons/validator.py:2803`

### Epoch Accumulation

Per epoch, each miner's total score is the sum of all their approved leads:

```
miner_score[epoch] = Σ effective_rep_score (across all approved leads in epoch)
```

**Code**: `neurons/validator.py:2811`

### Rolling Window

Scores are aggregated over a **30-epoch rolling window**:

```
rolling_score[miner] = Σ miner_score[epoch] for last 30 epochs
```

**Code**: `neurons/validator.py:3538` (`get_rolling_epoch_scores()`)

### Weight Distribution

**Constants** (`neurons/validator.py:2921-2936`):

| Parameter | Value |
|-----------|-------|
| `BASE_BURN_SHARE` | 0.0 (0%) |
| `CHAMPION_SHARE` | 0.05 (5%) |
| `MAX_SOURCING_SHARE` | 0.95 (95%) |
| `SOURCING_FLOOR_THRESHOLD` | 125,000 approved leads |
| `ROLLING_WINDOW` | 30 epochs |

### Sourcing Threshold Gate

```
if rolling_lead_count >= 125,000:
    effective_sourcing_share = 0.95  (full 95%)
else:
    effective_sourcing_share = (rolling_lead_count / 125,000) × 0.95
    remainder burned
```

**Code**: `neurons/validator.py:3105-3118`

### Per-Miner Weight

```
miner_proportion = miner_rolling_rep / total_registered_rolling_rep
miner_weight = effective_sourcing_share × miner_proportion
```

**Code**: `neurons/validator.py:3183-3184`

### Champion Share

5% goes to the qualification model champion (or burned if no champion exists).

### Burn

All unallocated shares are burned to UID 0:
- Base burn (0%)
- Unused sourcing share (if below 125K threshold)
- Unused champion share (if no champion)
- Deregistered miner share (rep from miners no longer on metagraph)

### Consensus

**Code**: `gateway/utils/consensus.py`

Multiple validators independently score each lead. Final rep score uses weighted consensus:

```
weight = v_trust × stake
final_rep_score = Σ(rep_score × weight) / Σ(weight)
approved if approval_ratio > 0.5
```

### Strategic Implications

- **Rep score maximization matters more than volume**: A miner submitting 100 leads with avg rep 40 earns more than one submitting 400 leads with avg rep 8
- **ICP bonuses are massive**: A +100 ICP bonus on a 30 rep lead = 130 effective points — 3.25x more weight than the raw rep alone
- **Enterprise companies are capped**: 10,001+ employees → max 5-10 rep points regardless of actual score
- **Small companies get bonuses**: ≤10 employees in a major hub = +50, ≤50 employees = +20

---

## 14. Qualification Model Competition

> **This is NOT mining.** Qualification models are AI agents submitted by miners that evaluate lead quality. The champion earns 5% of emissions — completely separate from the 95% sourcing share.

### 14a. How It Differs from Mining

| | Sourcing (Mining) | Qualification Model |
|---|---|---|
| **What it does** | Finds and submits leads from the web | Evaluates existing leads against ICPs |
| **Emissions share** | 95% (split by rep score) | 5% (single champion takes all) |
| **Execution** | Miner runs on own infrastructure | Validator runs model in sandbox (AWS Nitro Enclave) |
| **API access** | Miner uses own API keys | Model uses validator proxy (keys injected server-side) |
| **Competition** | All miners earn proportionally | King-of-the-hill — 1 champion only |
| **Input** | ICP config, then finds prospects | Given a lead + ICP, returns structured evaluation |
| **Output** | Lead records submitted to gateway | `LeadOutput` struct (no PII allowed) |

**Code**: `gateway/qualification/config.py`, `qualification/scoring/lead_scorer.py`

### 14b. LLMs Used in Evaluation

The **validator** (not the miner's model) uses these LLMs to score submitted leads:

| Purpose | Model | Provider | Cost |
|---------|-------|----------|------|
| ICP Fit scoring (0-20 pts) | `gpt-4o-mini` | OpenRouter | Per-token |
| Decision Maker scoring (0-30 pts) | `gpt-4o-mini` | OpenRouter | Per-token |
| Intent Signal verification (0-50 pts) | `gpt-4o-mini` | OpenRouter | Per-token |
| Hardcoding detection (pre-execution) | `claude-sonnet-4.5` | OpenRouter | $3/$15 per 1M tokens |
| ICP prompt generation (admin) | `o3-mini` | OpenRouter | — |

**Code**: `qualification/scoring/lead_scorer.py:357,404,572`, `qualification/validator/hardcoding_detector.py:52-55`, `gateway/tasks/icp_generator.py:44`

**Key**: The validator's scoring LLM is fixed (`gpt-4o-mini`). Miners cannot influence which model scores their output.

### 14c. What the Miner's Model Can Use

Miner qualification models can call LLMs and APIs **only through the validator proxy**. Models never see API keys.

**Allowed LLM Provider**: OpenRouter (any model available there, routed through proxy)

| API Provider | What It Provides | Cost Model |
|---|---|---|
| **OpenRouter** | LLM inference (any model) | PER_TOKEN ($0.00015/token) |
| **ScrapingDog** | LinkedIn, Google Search, job boards | PER_CREDIT ($0.0005/credit) |
| **BuiltWith** | Technology stack detection | PER_CALL ($0.01) |
| **Crunchbase** | Funding data, investors | PER_CALL ($0.01) |
| **Desearch** | Decentralized search (social media) | PER_CALL ($0.002) |
| **Data Universe** | Social media data (X, Reddit, YouTube) | PER_CALL ($0.00005) |
| **Jobs Data API** | Hiring signals | PER_CALL ($0.01) |
| **NewsAPI.org** | Company news, press releases | PER_CALL ($0.001) |

**Free APIs** (no keys needed): DuckDuckGo, Wikipedia, SEC EDGAR, Wayback Machine, GDELT, UK Companies House, Wikidata.

**Code**: `qualification/validator/local_proxy.py`

### 14d. Cost & Time Limits

**Code**: `gateway/qualification/config.py:46-51`

| Parameter | Value |
|-----------|-------|
| Max cost per lead (avg) | $0.05 |
| Max time per lead (avg) | 15 seconds |
| Hard timeout per lead | 30 seconds (instant fail, score = 0) |
| Total evaluation timeout | 60 minutes |
| Total leads evaluated | 100 (TOTAL_ICPS × LEADS_PER_ICP = 100 × 1) |
| Max total cost | ~$5.00 (100 × $0.05) |

**Variability Penalties**:

| Condition | Penalty |
|-----------|---------|
| Cost ≤ $0.05/lead | None |
| Cost > $0.10/lead (2× avg) | -5 points |
| Time ≤ 15s/lead | None |
| Time > 30s/lead (2× avg) | -5 points |

### 14e. Submission Requirements

| Parameter | Value |
|-----------|-------|
| Submission cost | $5 TAO (2 free/day, UTC reset) |
| Max tarball size | 10 MB |
| Max total file size | 200 KB |
| Rate limit | 1 submission per evaluation set (20 epochs) |
| Hardcoding rejection threshold | 70% confidence |

### 14f. Sandbox Security

Models run in AWS Nitro Enclave with **allowlist-only** Python libraries:

**Allowed**: json, re, datetime, math, random, collections, itertools, functools, typing, dataclasses, requests, httpx, aiohttp, pandas, numpy, pydantic, fuzzywuzzy, rapidfuzz, beautifulsoup4, dateutil, duckduckgo_search, openai (proxy), supabase (read-only)

**Blocked**: subprocess, ctypes, pickle, marshal, multiprocessing, cffi, shutil, os.system, eval, exec

**Code**: `qualification/validator/sandbox_security.py`

### 14g. Progressive Evaluation Pipeline

```
Submission → Hardcoding Detection (Claude Sonnet 4.5) → Screening 1 → Screening 2 → Final Benchmark
```

| Stage | ICPs | Pass Threshold | Fail Status |
|-------|------|---------------|-------------|
| Screening 1 | 5 | ≥ 20% of max score | FAILED_SCREENING_1 |
| Screening 2 | 20 | ≥ 40% of max score | FAILED_SCREENING_2 |
| Final Benchmark | 75 | Scored in full | FINISHED |

### 14h. Per-Lead Scoring (3 Components)

| Component | Max Points | Scored By |
|-----------|-----------|-----------|
| ICP Fit | 20 | gpt-4o-mini — how well lead matches ICP criteria |
| Decision Maker | 30 | gpt-4o-mini — is this person a buyer/decision-maker |
| Intent Signal | 50 | gpt-4o-mini — verified intent with time decay |
| **Total** | **100** | |

Intent Signal time decay:

| Signal Age | Multiplier |
|------------|------------|
| ≤ 2 months | 1.0x |
| ≤ 12 months | 0.5x |
| > 12 months | 0.25x |

**Date NOT required** (full score): GitHub, Company Website, Wikipedia, Review Sites
**Date IS required** (max 15 pts if undated): LinkedIn, Job Boards, News, Social Media

### 14i. Champion System

| Parameter | Value |
|-----------|-------|
| Dethroning threshold | Challenger must beat by > 10% |
| Minimum champion score | 10.0 / 100 |
| Min champion duration | 1 epoch |
| Evaluation set rotation | Every 20 epochs (~3.33 hours) |
| Rebenchmark time | 12:05 AM UTC daily |
| Champion emissions | 5% of subnet total |

### 14j. Final Score Formula

**Code**: `neurons/validator.py:4499-4524`

```
raw_avg_score = average(per_lead_scores) across 100 ICPs
fabrication_rate = fabricated_dates / leads_scored
integrity_multiplier = max(0, 1.0 - (max(0, fabrication_rate - 0.05) × 3.0))
final_score = raw_avg_score × integrity_multiplier
```

Fabrication penalty table:

| Fabrication Rate | Integrity Multiplier |
|-----------------|---------------------|
| ≤ 5% | 1.00 |
| 10% | 0.85 |
| 15% | 0.70 |
| 20% | 0.55 |
| 30% | 0.25 |
| ≥ 38.3% | 0.00 |

### 14k. Required Output Fields

Models must return `LeadOutput` with these fields:

```
lead_id, business, company_linkedin, company_website, employee_count,
industry, sub_industry, country, city, state, role, role_type, seniority,
intent_signals (min 1)
```

**Instant zero if PII included**: email, full_name, first_name, last_name, phone, linkedin_url

**Code**: `gateway/qualification/models.py:119-179`

### 14l. Current Competition State (subnet71.com, 2026-03-02)

| Metric | Value |
|--------|-------|
| Total submissions | 1 |
| Unique miners | 1 |
| Champion model | "FinalVersion001" |
| Champion miner | `5ECsyg7i...` |
| Champion final score | 15.47 / 100 |
| Raw average score | 19.58 / 100 |
| Leads scoring 0 | 55 / 100 |
| Fabrication rate | 12% (12/100) |
| Integrity multiplier | 0.79 |

### 14m. Strategic Implications

- **Virtually uncontested**: Only 1 submission exists. Submitting a working model almost guarantees becoming champion
- **Champion earns 5% of all subnet emissions** — for a single model submission
- **Current champion scores 15.47/100** — enormous room for improvement
- **55% of ICPs scored 0** — basic improvements to lead matching could double the score
- **Eliminating fabrication** alone would boost from 15.47 → 19.58 (+26%)
- **Cost budget is generous**: $0.05/lead allows meaningful LLM calls via OpenRouter proxy
- **Low barrier**: 2 free submissions/day, $5 TAO for additional submissions

### 14n. Key Files Reference

| File | Purpose |
|------|---------|
| `gateway/qualification/config.py` | All configuration constants |
| `gateway/qualification/models.py` | LeadOutput, ICP models |
| `qualification/scoring/lead_scorer.py` | Scoring pipeline (gpt-4o-mini) |
| `qualification/scoring/intent_verification.py` | Intent signal verification |
| `qualification/scoring/champion.py` | Champion selection logic |
| `qualification/validator/hardcoding_detector.py` | Claude Sonnet 4.5 pre-check |
| `qualification/validator/sandbox_security.py` | Library allowlist, blocked patterns |
| `qualification/validator/local_proxy.py` | API proxy, cost tracking |
| `miner_qualification_models/sample_model/` | Sample model for reference |
