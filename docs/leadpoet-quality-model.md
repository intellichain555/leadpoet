# LeadPoet (SN71) Miner Quality & Scoring Model

> Complete reference with verbatim source code quotes and file:line references.
> Generated: 2026-03-02

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Rate Limits & Daily Budget](#2-rate-limits--daily-budget)
3. [Gateway Required Fields](#3-gateway-required-fields)
4. [Validator Stage 0: Hardcoded Checks](#4-validator-stage-0-hardcoded-checks)
5. [Validator Stage 1: DNS Layer](#5-validator-stage-1-dns-layer)
6. [Validator Stage 2: Domain Reputation](#6-validator-stage-2-domain-reputation)
7. [Validator Stage 3: Email Verification](#7-validator-stage-3-email-verification)
8. [Validator Stage 4: LinkedIn Verification](#8-validator-stage-4-linkedin-verification)
9. [Validator Stage 5: Role/Region/Industry Verification](#9-validator-stage-5-roleregionindustry-verification)
10. [Rep Score (0-48 points)](#10-rep-score-0-48-points)
11. [ICP Adjustment System](#11-icp-adjustment-system)
12. [Qualification Scoring (0-100 points)](#12-qualification-scoring-0-100-points)
13. [Pre-Checks (Auto-Zero)](#13-pre-checks-auto-zero)
14. [Intent Model (Miner-Side)](#14-intent-model-miner-side)
15. [Weight Formula & Emissions](#15-weight-formula--emissions)
16. [Miner Sourcing Loop](#16-miner-sourcing-loop)

---

## 1. Architecture Overview

The pipeline is: **Miner → Gateway → Validator → Scoring → Emission Weights**.

- **Miner** sources leads using Serper search + crawl4ai web scraping + LLM extraction
- **Gateway** performs structural validation (required fields, rate limiting)
- **Validator** runs automated checks in 6 stages (Stage 0-5) + Rep Score
- **Qualification** scores leads on a 0-100 scale using LLM-based evaluation
- **Reward** calculates epoch weights determining emissions

---

## 2. Rate Limits & Daily Budget

**Source:** `gateway/utils/rate_limiter.py:48-51`

```python
# Rate limit constants
# Production limits to maintain lead quality and prevent spam
MAX_SUBMISSIONS_PER_DAY = 1000
MAX_REJECTIONS_PER_DAY = 250
MIN_SECONDS_BETWEEN_SUBMISSIONS = 20  # Cooldown between submissions (anti-spam)
```

**Key facts:**
- 1000 submissions per day max
- **250 rejections per day** (note: code says 250, not 200 as some docs claim)
- 20-second cooldown between submissions (anti-spam)
- Resets at midnight UTC (`rate_limiter.py:53-65`)
- **ALL rejections count** — both gateway rejections and validator rejections increment the rejection counter

---

## 3. Gateway Required Fields

**Source:** `gateway/api/submit.py:1840-1858`

```python
REQUIRED_FIELDS = [
    "business",         # Company name
    "full_name",        # Contact full name
    "first",            # First name
    "last",             # Last name
    "email",            # Email address
    "role",             # Job title
    "website",          # Company website
    "industry",         # Primary industry (must match Crunchbase industry_group)
    "sub_industry",     # Sub-industry/niche (must match Crunchbase industry key)
    "country",          # Country (REQUIRED)
    "city",             # City (REQUIRED for all leads)
    # "state" - REQUIRED for US only (validated in region validation section below)
    "linkedin",         # LinkedIn URL (person)
    "company_linkedin", # Company LinkedIn URL
    "source_url",       # Source URL where lead was found
    "description",      # Company description
    "employee_count"    # Company size/headcount
]
```

That's **16 required fields** (15 always + state for US leads). Any missing field = instant gateway rejection, which counts against the 250/day rejection budget.

---

## 4. Validator Stage 0: Hardcoded Checks

**Source:** `validator_models/automated_checks.py:614-622`

```python
checks_stage0_instant = [
    check_required_fields,      # Required fields validation (HARD)
    check_email_regex,          # RFC-5322 regex validation (HARD)
    check_name_email_match,     # Name in email check (HARD)
    check_general_purpose_email,# General purpose email filter (HARD)
    check_free_email_domain,    # Reject free email domains (HARD)
    check_disposable,           # Filter throwaway email providers (HARD)
]
```

All Stage 0 checks are **HARD** — failure = instant rejection.

### 4a. Required Fields Validation

**Source:** `validator_models/automated_checks.py:60-118`

Checks: industry, sub_industry, role, country, city, contact_name (full_name OR first+last). State required for US leads only.

```python
# Special check: state is required for US leads
us_aliases = ["united states", "usa", "us", "u.s.", "u.s.a.", "america", "united states of america"]
```

### 4b. Email Regex (RFC-5322 + RFC-6531)

**Source:** `validator_models/automated_checks.py:120-191`

```python
# RFC-5322 simplified regex (original ASCII validation)
pattern_ascii = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

# RFC-6531 - Internationalized Email (Unicode support)
pattern_unicode = r"^[\w._%+-]+@[\w.-]+\.[a-zA-Z]{2,}$"
```

Also rejects emails with `+` in local part:

```python
# Reject emails with "+" sign (prevents duplicate submission exploit via email aliasing)
if "+" in email.split("@")[0]:
```
(`automated_checks.py:162-175`)

### 4c. Name-Email Match (HARD)

**Source:** `validator_models/automated_checks.py:193-319`

Two-strategy matching system with `MIN_NAME_MATCH_LENGTH = 3` (`automated_checks.py:240`).

**Strategy 1** — Pattern matching (`automated_checks.py:244-264`):

```python
# Strategy 1: Check if normalized name patterns appear in local part
patterns = []
if len(first_normalized) >= MIN_NAME_MATCH_LENGTH:
    patterns.append(first_normalized)  # john
if len(last_normalized) >= MIN_NAME_MATCH_LENGTH:
    patterns.append(last_normalized)  # doe
patterns.append(f"{first_normalized}{last_normalized}")  # johndoe
if len(first_normalized) > 0:
    patterns.append(f"{first_normalized[0]}{last_normalized}")  # jdoe
    patterns.append(f"{last_normalized}{first_normalized[0]}")  # doej
```

**Strategy 2** — Prefix matching (`automated_checks.py:266-297`):

```python
# Strategy 2: Check if local part matches shortened versions of the name
# e.g., "greg" matches "gregory" (local_part is prefix of name)
if first_normalized.startswith(local_normalized):
    name_match = True
```

Also checks name prefixes (3-6 chars) in local part (`automated_checks.py:284-297`):

```python
for length in range(MIN_NAME_MATCH_LENGTH, min(len(first_normalized) + 1, 7)):
    name_prefix = first_normalized[:length]
    if name_prefix == local_normalized or name_prefix in local_normalized:
        name_match = True
```

### 4d. General-Purpose Email Filter (HARD)

**Source:** `validator_models/automated_checks.py:321-379`

```python
general_purpose_prefixes = [
    'info@', 'hello@', 'owner@', 'ceo@', 'founder@', 'contact@', 'support@',
    'team@', 'admin@', 'office@', 'mail@', 'connect@', 'help@', 'hi@',
    'welcome@', 'inquiries@', 'general@', 'feedback@', 'ask@', 'outreach@',
    'communications@', 'crew@', 'staff@', 'community@', 'reachus@', 'talk@',
    'service@'
]
```

27 blocked prefixes. Any match = instant rejection.

### 4e. Free Email Domain Filter (HARD)

**Source:** `validator_models/automated_checks.py:381-439`

```python
free_domains = {
    'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk', 'yahoo.fr',
    'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'aol.com', 'mail.com', 'protonmail.com', 'proton.me',
    'icloud.com', 'me.com', 'mac.com',
    'zoho.com', 'yandex.com', 'gmx.com', 'mail.ru'
}
```

20 blocked domains. B2B leads must use corporate email.

### 4f. Disposable Email Filter (HARD)

**Source:** `validator_models/automated_checks.py:441-481`

Uses `is_disposable_email()` from `checks_email.py`. Comprehensive list defined in `qualification/scoring/pre_checks.py:80-93`:

```python
DISPOSABLE_EMAIL_DOMAINS: Set[str] = {
    "tempmail.com", "throwaway.com", "mailinator.com", "10minutemail.com",
    "guerrillamail.com", ... "minutemail.com",
}
```

### 4g. HEAD Request Check

**Source:** `validator_models/automated_checks.py:639-718`

Runs in background during Stage 1. Validates the company website responds.

---

## 5. Validator Stage 1: DNS Layer

**Source:** `validator_models/automated_checks.py:642-703`

```python
# OPTIMIZATION: Run all Stage 1 DNS checks in parallel
results = await asyncio.gather(
    check_domain_age(lead),     # HARD
    check_mx_record(lead),      # HARD
    check_spf_dmarc(lead),      # SOFT - always passes, appends data
    return_exceptions=True
)
```

- **Domain Age** — HARD check. Domain must be old enough to be legitimate.
- **MX Record** — HARD check. Domain must have mail exchange records.
- **SPF/DMARC** — SOFT check. Always passes but data is collected for rep score.

---

## 6. Validator Stage 2: Domain Reputation

**Source:** `validator_models/automated_checks.py:720-753`

```python
# Stage 2: Lightweight Domain Reputation Checks (HARD)
# - DNSBL (Domain Block List) - Spamhaus DBL lookup
passed, rejection_reason = await check_dnsbl(lead)
```

DNSBL blacklisted domain = instant rejection.

---

## 7. Validator Stage 3: Email Verification

**Source:** `validator_models/automated_checks.py:745-753`

```python
# STOP HERE - Stage 3 (email verification) is handled by batch process
automated_checks_data["passed"] = True  # Passed Stage 0-2
```

Email verification is done via **TrueList batch process** — separate from the main check pipeline. Emails are submitted in batch and polled for results.

---

## 8. Validator Stage 4: LinkedIn Verification

**Source:** `validator_models/automated_checks.py:797-802`

```python
"stage_4_linkedin": {
    "linkedin_verified": False,
    "gse_search_count": 0,
    "llm_confidence": "none"
}
```

Uses `check_linkedin_gse()` from `checks_linkedin.py`. Verifies LinkedIn profile exists via Google Search Engine (GSE) queries. LLM evaluates match confidence.

---

## 9. Validator Stage 5: Role/Region/Industry Verification

**Source:** `validator_models/automated_checks.py:803-812`

```python
"stage_5_verification": {
    "role_verified": False,
    "region_verified": False,
    "industry_verified": False,
    "extracted_role": None,
    "extracted_region": None,
    "extracted_industry": None,
    "early_exit": None
}
```

Cross-references lead data against external sources to verify accuracy.

---

## 10. Rep Score (0-48 points)

**Source:** `validator_models/automated_checks.py:54`

```python
MAX_REP_SCORE = 48  # Wayback (6) + SEC (12) + WHOIS/DNSBL (10) + GDELT (10) + Companies House (10) = 48
```

### 10a. Wayback Machine (0-6 points)

**Source:** `validator_models/checks_repscore.py:78-90`

```python
# Scoring logic (UPDATED: max 6 points for Wayback):
if snapshots < 10:
    score = min(1.2, snapshots * 0.12)
elif snapshots < 50:
    score = 1.8 + (snapshots - 10) * 0.03
elif snapshots < 200:
    score = 3.6 + (snapshots - 50) * 0.008
else:
    score = 5.4 + min(0.6, (snapshots - 200) * 0.0006)

# Age bonus
if age_years >= 5:
    score = min(6, score + 0.6)
```

More archived snapshots = higher score. 5+ year-old domains get a bonus.

### 10b. SEC Edgar (0-12 points)

**Source:** `validator_models/checks_repscore.py:280-293`

```python
# Scoring logic (UPDATED: max 12 points for SEC):
# - 1-5 filings: 3.6 points
# - 6-20 filings: 7.2 points
# - 21-50 filings: 9.6 points
# - 50+ filings: 12 points

if total_filings <= 5:
    score = min(3.6, total_filings * 0.72)
elif total_filings <= 20:
    score = 7.2
elif total_filings <= 50:
    score = 9.6
else:
    score = 12
```

SEC-registered companies with many filings score highest. This is the largest single rep score component.

### 10c. WHOIS/DNSBL Reputation (0-10 points)

**Source:** `validator_models/checks_repscore.py:650-809`

Four sub-components:

**WHOIS Stability (0-3 points)** (`checks_repscore.py:663-689`):
```python
# >= 180 days (6 months): 3.0 points (very stable)
# >= 90 days (3 months): 2.0 points (stable)
# >= 30 days (1 month): 1.0 points (acceptable)
# < 30 days: 0 points (unstable)
if whois_updated_days >= 180:
    details["whois_stability"] = 3.0
```

**Registrant Consistency (0-3 points)** (`checks_repscore.py:701-753`):
```python
# Score based on signals count
# 3+ signals: 3 points  (corporate registrant, reputable hosting, established domain)
# 2 signals: 2 points
# 1 signal: 1 point
```

Checks for: corporate registrar keywords (Inc, LLC, Corp, etc.), reputable hosting (AWS, Google, Cloudflare, Azure), domain age > 1 year.

**Hosting Provider Reputation (0-3 points)** (`checks_repscore.py:755-781`):
```python
reputable_providers = ["aws", "google", "cloudflare", "azure", "amazon"]
if found_provider:
    details["hosting_provider"] = 3.0
```

**DNSBL Reputation (0-1 point)** (`checks_repscore.py:783-804`):
```python
if not dnsbl_blacklisted:
    details["dnsbl"] = 1.0
```

### 10d. GDELT Mentions (0-10 points)

**Source:** `validator_models/checks_repscore.py:494-527`

```python
# Press wire mentions: 0-5 points
# - 1+ mention: 2 points
# - 3+ mentions: 3 points
# - 5+ mentions: 4 points
# - 10+ mentions: 5 points

# Trusted domain mentions: 0-5 points
# (same tier structure)
```

Total = press_score (0-5) + trusted_score (0-5) = 0-10 points.

### 10e. Companies House UK (0-10 points)

**Source:** `validator_models/checks_repscore.py:609-614`

```python
if company_upper == ch_name:
    score = 10.0 if status == "active" else 8.0
elif company_upper in ch_name or ch_name in company_upper:
    score = 8.0 if status == "active" else 6.0
```

UK-registered companies only. Active exact match = 10 points.

---

## 11. ICP Adjustment System

### 11a. ICP Bonus (Default +50, High-Value +100)

**Source:** `validator_models/checks_icp.py:831-833`

```python
# Get bonus: use custom "bonus" field, or default to 50
icp_bonus = icp.get("bonus", 50)
highest_bonus = max(highest_bonus, icp_bonus)
```

High-value ICPs that get **+100 bonus**:

| ICP | Source |
|-----|--------|
| AI/ML/Data Engineering | `checks_icp.py:56` — `"bonus": 100` |
| Cyber Security Midwest (10-50 emp) | `checks_icp.py:75` — `"bonus": 100` |
| UAE Investors | `checks_icp.py:134` — `"bonus": 100` |
| Blockchain/Crypto/Web3 Investors | `checks_icp.py:186` — `"bonus": 100` |
| Wealth Management/Family Office | `checks_icp.py:255` — `"bonus": 100` |

### 11b. Enterprise Company Cap

**Source:** `validator_models/checks_icp.py:838-867`

```python
def is_enterprise_company(lead: dict) -> bool:
    """
    Enterprise companies get a rep score multiplier that caps their final score:
    - ICP match: target = 10, multiplier = min(0, 10 - raw_rep_score)
    - No ICP match: target = 5, multiplier = min(0, 5 - raw_rep_score)
    """
    ...
    return emp_min >= 10001
```

Companies with 10,001+ employees are capped at 5 or 10 rep score points regardless of actual score.

### 11c. Employee Size Adjustments

**Source:** `validator_models/checks_icp.py:1043-1066`

```python
# Small company in major hub bonus (+50 points)
if emp_max <= 10 and is_major_hub:
    bonus += 50

# Small company bonus (+20 points for ≤50 employees)
elif emp_max <= 50:
    bonus += 20

# Large company penalty (stacks with capped bonus)
if 5000 < emp_min < 10001:
    penalty = 15     # 5,001-10,000 employees: -15 points

elif 1000 < emp_min <= 5000:
    penalty = 10     # 1,001-5,000 employees: -10 points
```

Summary of ICP adjustment formula (`checks_icp.py:870-903`):
```
ICP match only = +50
High-value ICP (AI/Crypto/etc.) = +100
ICP + ≤50 employees = +70 → capped to +50
High-value ICP + >1k employees = +100 - 10 = +90
Small hub (≤10 + NYC) = +50
Non-ICP + ≤50 employees = +20
Non-ICP + >5k employees = -15
```

---

## 12. Qualification Scoring (0-100 points)

**Source:** `qualification/scoring/lead_scorer.py:56-60`

```python
# Score component maximums
MAX_ICP_FIT_SCORE = 20
MAX_DECISION_MAKER_SCORE = 30
MAX_INTENT_SIGNAL_SCORE = 50
MAX_TOTAL_SCORE = MAX_ICP_FIT_SCORE + MAX_DECISION_MAKER_SCORE + MAX_INTENT_SIGNAL_SCORE
```

**Total: 100 points** = ICP Fit (0-20) + Decision Maker (0-30) + Intent Signal (0-50).

### 12a. Source Type Multipliers

**Source:** `qualification/scoring/lead_scorer.py:415-425`

```python
SOURCE_TYPE_MULTIPLIERS = {
    "linkedin": 1.0,           # High-value: professional network
    "job_board": 1.0,          # High-value: explicit hiring intent
    "github": 1.0,             # High-value: technical activity
    "news": 0.9,               # Good: public announcements
    "company_website": 0.85,   # Medium: could be generic content
    "social_media": 0.8,       # Medium: less reliable intent signals
    "review_site": 0.75,       # Medium-low: indirect signal
    "wikipedia": 0.6,          # Low-medium: reliable but indirect intent
    "other": 0.3,              # LOW: catch-all category indicates fallback
}
```

**Takeaway:** LinkedIn, job board, and GitHub sources get full credit. "other" source type gets only 30%.

### 12b. Intent Signal Time Decay

**Source:** `qualification/scoring/lead_scorer.py:617-637`

```python
def calculate_time_decay_multiplier(age_months: float) -> float:
    """
    Decay tiers:
    - ≤2 months: 100% (1.0x)
    - ≤12 months: 50% (0.5x)
    - >12 months: 25% (0.25x)
    """
    if age_months <= CONFIG.INTENT_SIGNAL_DECAY_50_PCT_MONTHS:
        return 1.0
    elif age_months <= CONFIG.INTENT_SIGNAL_DECAY_25_PCT_MONTHS:
        return 0.5
    else:
        return 0.25
```

Fresh intent signals (≤2 months) get full credit. Older signals decay aggressively.

---

## 13. Pre-Checks (Auto-Zero)

These checks run BEFORE LLM scoring. Failure = automatic score of 0.

**Source:** `qualification/scoring/pre_checks.py:116-196`

```python
async def run_automatic_zero_checks(lead, icp, run_cost_usd, run_time_seconds, seen_companies):
```

**8 auto-zero checks:**

| # | Check | Source |
|---|-------|--------|
| 1 | Hard time limit (30s) | `pre_checks.py:142-147` |
| 2 | Industry fuzzy match (80%) | `pre_checks.py:149-153` |
| 3 | Sub-industry fuzzy match (70%) | `pre_checks.py:155-159` |
| 4 | Role fuzzy match (60%) | `pre_checks.py:161-165` |
| 5 | Country match | `pre_checks.py:167-171` |
| 6 | Seniority level (within 1 level of ICP) | `pre_checks.py:173-180` |
| 7 | Data quality (placeholders, suspicious chars) | `pre_checks.py:182-186` |
| 8 | Duplicate company (first lead per company wins) | `pre_checks.py:188-192` |

### Fuzzy matching thresholds

**Source:** `qualification/scoring/pre_checks.py:74-77`

```python
INDUSTRY_MATCH_THRESHOLD = 80   # 80% for industry
SUB_INDUSTRY_MATCH_THRESHOLD = 70  # 70% for sub-industry
ROLE_MATCH_THRESHOLD = 60       # 60% for role (more lenient for variations)
```

### Placeholder text detection

**Source:** `qualification/scoring/pre_checks.py:96-101`

```python
PLACEHOLDER_PATTERNS: List[str] = [
    "test", "asdf", "xxx", "sample", "example", "lorem", "ipsum",
    "foo", "bar", "baz", "qwerty", "dummy", "fake", "placeholder",
    "demo", "temp", "null", "undefined", "n/a", "na", "none",
    "tbd", "todo", "fixme", "testing", "aaa", "bbb", "ccc",
]
```

---

## 14. Intent Model (Miner-Side)

**Source:** `miner_models/intent_model.py:30-33`

```python
FIT_WEIGHT_INDUSTRY = 0.45
FIT_WEIGHT_REGION   = 0.15
FINAL_SCORE_FIT_W   = 0.6
FINAL_SCORE_INT_W   = 0.4
```

### Lead Ranking Formula

**Source:** `miner_models/intent_model.py:425-462`

```python
async def rank_leads(leads, description):
    """
    Blend existing conversion_score (fit / legitimacy) with fresh
    intent_score from the LLM or heuristic:
        final = 0.6 * conversion + 0.4 * intent
    """
```

The miner ranks its own leads before submission using:
- `final = 0.6 * conversion_score + 0.4 * intent_score`
- Role filtering based on buyer description
- Intent scoring via LLM or heuristic fallback

---

## 15. Weight Formula & Emissions

### Epoch Configuration

**Source:** `Leadpoet/validator/reward.py:12-15`

```python
EPOCH_DURATION_MINUTES = 72
EPOCH_DURATION_BLOCKS = 360
BITTENSOR_BLOCK_TIME_SECONDS = 12
```

One epoch = 72 minutes = 360 blocks. Weights are calculated at epoch boundaries.

### Final Weight Formula

**Source:** `Leadpoet/validator/reward.py:733-743`

```python
# Calculate final weight: Wm = 0.10 x Km + 0.45 x Sm + 0.45 x Cm
W_weights = {}
for miner in all_miners:
    K_m = K_weights.get(miner, 0.0)  # 10% all-sourcers
    S_m = S_weights.get(miner, 0.0)  # 45% sourcers-of-curated
    C_m = C_weights.get(miner, 0.0)  # 45% curators

    W_m = 0.10 * K_m + 0.45 * S_m + 0.45 * C_m
    W_weights[miner] = W_m
```

**Three weight components:**

| Component | Weight | Description |
|-----------|--------|-------------|
| K (all-sourcers) | 10% | Volume of leads sourced |
| S (sourcers-of-curated) | 45% | Quality of sourced leads that pass curation |
| C (curators) | 45% | Curation accuracy |

**Sourcing (S) is the most impactful for miners** — 45% of weight comes from sourcing leads that pass quality checks.

### Emissions Distribution

**Source:** `Leadpoet/validator/reward.py:745-753`

```python
total_weight = sum(W_weights.values())
emissions = {}
if total_weight > 0:
    for miner, weight in W_weights.items():
        emissions[miner] = total_emission * (weight / total_weight)
```

Emissions are proportional to weight share.

---

## 16. Miner Sourcing Loop

**Source:** `neurons/miner.py:178-189`

```python
async def sourcing_loop(self, interval: int, miner_hotkey: str):
    print(f"Starting continuous sourcing loop (interval: {interval}s)")
    while True:
        ...
        new_leads = await get_leads(1, industry=None, region=None)
```

Currently sources **1 lead per cycle**. After sourcing:
- Leads go through source provenance validation
- Each lead is sanitized with `sanitize_prospect()`
- 20-second anti-spam cooldown between submissions (`miner.py:320`)

**Source:** `neurons/miner.py:320`

```python
# Anti-spam cooldown between submissions
await asyncio.sleep(20)
```

---

## 17. Role Verification Deep Dive (Stage 4)

The validator **actively verifies** that the claimed role matches real publicly-available data. Faking roles (e.g., labeling everyone "CEO") will get leads rejected and burn the 250/day rejection budget.

### 17a. Verification Pipeline (3 steps)

**Source:** `validator_models/stage4_person_verification.py:725-843`

**Step 1 — Rule-based matching** against Google search results (`stage4_helpers.py:1811-1842`):

```python
def validate_role_rule_based(gt_role, search_results, linkedin_url, full_name):
    # First try URL-matched result (LinkedIn slug match)
    for result in search_results:
        result_lid = get_linkedin_id(result.get('link', ''))
        if result_lid and expected_lid and result_lid == expected_lid:
            combined = f"{result.get('title', '')} {result.get('snippet', '')}"
            if check_role_matches(gt_role, combined):
                return True, 'url_match'

    # Then try name-matched results
    for result in search_results:
        if check_name_in_result(full_name, result, linkedin_url):
            combined = f"{result.get('title', '')} {result.get('snippet', '')}"
            if check_role_matches(gt_role, combined):
                return True, 'name_match'
    return False, None
```

The matching logic (`stage4_helpers.py:1791-1808`) normalizes the role, extracts key words (skip "the", "and", "of"), and checks all key words appear in the search result text.

**Step 2 — Targeted role query** (`stage4_person_verification.py:743-765`):

```python
rq_query = f'linkedin.com/in/{expected_lid}+role'
rq_results, rq_error = await search_google_async(rq_query, api_key)
```

If rule-based fails, a second Google search is done specifically for the LinkedIn profile + role. Result is checked with the same `check_role_matches()` function.

**Step 3 — LLM verification** (`stage4_helpers.py:1845-1920`):

If both rule-based checks fail, sends search results to Gemini Flash with a **strict anti-fabrication prompt**:

```python
prompt = f'''You are a strict job title verifier. You can ONLY verify a role
if you see evidence of it in the search results below. NEVER assume or guess.

RULES (follow in order):
1. FAIL if "{claimed_role}" contains company name
2. FAIL if "{claimed_role}" is generic (e.g., "Job Title", "N/A", "Title", "Employee")
3. FAIL if LinkedIn shows different company than "{company}"
4. FAIL if different function (Sales≠Product, Engineer≠Marketing)
5. FAIL if NO job title or role text appears in any result above.
   Do NOT assume "CEO", "Manager", or any title unless you can quote it.
6. PASS only if a matching role is explicitly written in the results:
   - Ignore seniority (Manager≈Sr.Manager)
   - Match synonyms (Developer≈Engineer, VP≈Vice President)
   - Match abbreviations (Dev≈Developer, Mgr≈Manager)
7. Use OTHER RESULTS only if role not found in LINKEDIN RESULT

JSON only: {{"role_pass": bool, "role_found": ""}}'''
```

**On failure → lead rejected** (`stage4_person_verification.py:799-810`):

```python
result['rejection_reason'] = {
    "message": f"Role '{role}' not verified by LLM",
    "failed_fields": ["role"],
    "claimed_role": role
}
```

### 17b. Stage 5 Enforces Stage 4 Result

**Source:** `validator_models/stage5_verification.py:3255-3272`

```python
# ROLE & LOCATION: Trust Stage 4 verification
role_verified_by_stage4 = lead.get("role_verified", False)

if role_verified_by_stage4:
    print(f"   ✅ ROLE: Already verified in Stage 4 (method: {role_method})")
else:
    print(f"   ❌ ROLE: Not verified in Stage 4")
    return False, {
        "message": "Role was not verified in Stage 4",
        "failed_fields": ["role"]
    }
```

If Stage 4 didn't verify the role → Stage 5 instant rejection.

### 17c. Miner Strategy: Pre-Validate & Discover Roles

Since the validator uses **Google search results** to verify roles, the miner can reuse the same approach to:

1. **Pre-validate before submission**: Run `check_role_matches(role, google_snippet)` locally using the validator's own logic (`stage4_helpers.py:1791-1808`) before submitting. If it fails locally, it will fail at the validator too — skip this lead and save a rejection slot.

2. **Discover the real role**: Instead of trusting the LLM-extracted role from website crawling, search Google for `"linkedin.com/in/{slug}"` and extract the actual role from the search snippet (LinkedIn titles typically appear as "Name - Role - Company" in Google results). This gives the **validator-verifiable** role.

3. **Match against ICP roles**: Iterate the ICP `role_details` list from `checks_icp.py` (e.g., "ceo", "cto", "founder", "vp of engineering") and check which ones match the Google-visible role. Only submit the lead if the real role matches an ICP target role — maximizing both acceptance rate and ICP bonus.

4. **Reuse validator functions directly**: The key functions are importable:
   - `stage4_helpers.check_role_matches(gt_role, text)` — rule-based role matching
   - `stage4_helpers.validate_role_rule_based(role, results, linkedin_url, name)` — full rule-based pipeline
   - `stage4_helpers.validate_role_with_llm(name, company, role, ...)` — LLM fallback
   - `common.get_seniority_rank(title)` — seniority classification

5. **Cost**: The validator uses Google search (ScrapingDog/GSE API) for role verification. The miner could use Serper (already integrated, $0.0005/request) to do the same pre-check. At 2-5K leads/day, filtering out bad roles before submission saves far more in rejection budget than it costs in Serper queries.

**Key files:**
- `validator_models/stage4_helpers.py:1791-1920` — role matching + LLM verification logic
- `validator_models/stage4_person_verification.py:725-843` — orchestration pipeline
- `validator_models/stage5_verification.py:3255-3272` — Stage 5 enforcement
- `validator_models/checks_icp.py` — ICP role_details lists to match against

---

## Summary: What Makes a High-Scoring Lead

1. **Pass all Stage 0 checks**: Corporate email, name matches email, no general-purpose prefix, no free domain
2. **Strong Rep Score (up to 48 pts)**: SEC filings (12), GDELT press coverage (10), WHOIS stability (10), Companies House (10), Wayback archives (6)
3. **ICP Match (+50 or +100)**: Target the high-value ICPs (AI/ML, Crypto, Cyber Midwest, UAE investors, Wealth Mgmt)
4. **Small companies**: ≤50 employees get +20 bonus; ≤10 in major hub get +50 bonus
5. **Avoid enterprise (10,001+)**: Rep score capped at 5-10 points
6. **Fresh intent signals**: ≤2 months old for full credit
7. **High-value sources**: LinkedIn, job boards, GitHub get 1.0x multiplier
8. **Match ICP precisely**: Industry (80%), sub-industry (70%), role (60%) fuzzy thresholds
9. **Real LinkedIn profiles**: Verified via GSE search in Stage 4
10. **Corporate domain quality**: AWS/Google/Cloudflare hosting, old stable WHOIS, not blacklisted
