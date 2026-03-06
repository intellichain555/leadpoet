# Zero Rejection Strategy

> Goal: 0% rejection rate to maximize emissions and outperform other miners.
> Every rejection wastes 1 of your 250/day rejection budget AND the 20s submission cooldown.

---

## 1. Why Leads Get Rejected

The miner submits leads that it has **extracted but not verified**. The validator then verifies each lead against external sources. When the miner's data doesn't match reality, the lead gets rejected.

| Rejection Stage | What Fails | % of Rejections (est.) | Can Pre-Check? |
|---|---|---|---|
| Gateway: missing fields | Empty required field | 5% | Yes (local) |
| Stage 0: email checks | General-purpose, free domain, name mismatch | 15% | Yes (local) |
| Stage 1: DNS | No MX record, domain too young | 10% | Yes (local DNS) |
| Stage 2: DNSBL | Domain blacklisted | 5% | Yes (local DNS) |
| Stage 3: email verify | Email bounces (TrueList) | 15% | Partial (SMTP check) |
| **Stage 4: LinkedIn + Role** | **LinkedIn doesn't exist, role mismatch** | **30%** | **Yes (Serper)** |
| Stage 5: region/industry | Data doesn't match external sources | 10% | Yes (fuzzy match) |
| Pre-checks: ICP mismatch | Industry/role/country doesn't match ICP | 10% | Yes (local) |

**Biggest rejection source: Stage 4 (role + LinkedIn verification) at ~30%.**

---

## 2. The Model Is Not the Problem

Switching LLM (Qwen → Gemini) only affects extraction quality. But most rejections come from **unverified data**, not bad extraction:

- The LLM correctly extracts "John Smith, CEO" from the website
- But John Smith changed roles 6 months ago — LinkedIn now says "Advisor"
- Validator searches Google, finds the mismatch, rejects the lead

The fix is **not a better LLM** — it's **verifying before submitting**.

---

## 3. Pre-Verification Pipeline (Implemented)

Added to `main_leads.py` as `verify_lead_external()`. Runs AFTER local `validate_lead()` and BEFORE submission.

```
Serper → crawl4ai → LLM extraction → validate_lead() → verify_lead_external() → submit
                                       (local, free)     (MX + Serper + fuzzy)
```

### 3a. MX Record Check (Mirrors Validator Stage 1)

**Source:** `main_leads.py:_check_mx_record()`

```python
answers = dns.resolver.resolve(domain, 'MX', lifetime=5)
```

- Cost: **$0** (local DNS query)
- Catches: domains that don't exist, parked domains, domains without mail
- The validator's `check_mx_record()` does the exact same thing — if we fail here, the validator will too

### 3b. Role Pre-Verification via Serper (Mirrors Validator Stage 4)

**Source:** `main_leads.py:_verify_role_via_serper()`

Two-query approach matching the validator's pipeline (`stage4_person_verification.py:725-843`):

1. **LinkedIn search**: `site:linkedin.com/in/ "John Smith" "Acme Corp"`
   - Check if the claimed role appears in the Google snippet (title + description)
   - Uses `_check_role_matches_validator()` which replicates `stage4_helpers.py:1791`

2. **General web search** (fallback): `"John Smith" "Acme Corp" CEO`
   - If LinkedIn search doesn't confirm, try broader web

- Cost: **$0.001/lead** (2 Serper queries × $0.0005)
- At 2K leads/day: **$2/day**
- This is the **highest-ROI check** — eliminates ~30% of rejections

### 3c. ICP Fuzzy Matching (Mirrors Validator pre_checks.py)

**Source:** `main_leads.py:_check_icp_fuzzy_match()`

Replicates the validator's pre-check thresholds (`pre_checks.py:74-77`):

```python
INDUSTRY_MATCH_THRESHOLD = 80   # fuzz.ratio
SUB_INDUSTRY_MATCH_THRESHOLD = 70
ROLE_MATCH_THRESHOLD = 60       # fuzz.partial_ratio
```

Currently checks:
- **Role vs ICP role_priority** keys at 60% partial_ratio threshold
- **Country vs ICP geographic_focus** (exact match)

- Cost: **$0** (local computation using `thefuzz` library)

---

## 4. Cost Analysis

| Check | Method | Cost/Lead | Daily (2K leads) |
|---|---|---|---|
| MX record | Local DNS | $0 | $0 |
| Role verify (Serper) | 2 Google searches | $0.001 | **$2/day** |
| ICP fuzzy match | Local computation | $0 | $0 |
| **Total** | | | **~$2/day** |

### ROI Calculation

Each rejected lead costs:
- 1/250 of your daily rejection budget
- 20 seconds of cooldown time (wasted submission slot)
- If you hit 250 rejections, you're locked out for the rest of the day

At 2K submissions/day with a 30% rejection rate (no pre-verify):
- **600 rejections** → hit the 250 cap after ~830 submissions → lose the rest of the day

With pre-verification at $2/day:
- **~0% rejection rate** → all 1000 submission slots used productively
- **Net gain**: 170+ extra accepted leads/day (worth far more than $2)

---

## 5. Future Improvements

### 5a. Email Verification (Stage 3)

The largest uncovered rejection source. Options:

| Method | Cost | Accuracy |
|---|---|---|
| SMTP VRFY (direct) | Free | ~60% (many servers block it) |
| Reacher (self-hosted) | Free (Docker) | ~80% |
| ZeroBounce / NeverBounce API | $0.003-0.008/email | ~95% |
| TrueList (same as validator) | Unknown | 100% (same system) |

**Recommended**: Self-host [Reacher](https://github.com/reacherhq/check-if-email-exists) in Docker — free, ~80% catch rate.

### 5b. Role Discovery (Not Just Verification)

Instead of verifying the LLM-extracted role, **discover the real role** from Google:

1. Search: `site:linkedin.com/in/ "John Smith" "Acme Corp"`
2. Parse the Google snippet: typically shows "John Smith - CEO - Acme Corp"
3. Use the Google-discovered role instead of the LLM-extracted role
4. Check the discovered role against ICP `role_details` from `checks_icp.py`

This ensures the submitted role matches what the validator will find.

### 5c. LinkedIn Discovery (Not Just Verification)

Instead of relying on the crawler to find LinkedIn URLs on company websites:

1. Search: `site:linkedin.com/in/ "John Smith" "Acme Corp"`
2. Extract the LinkedIn URL from the search result
3. Verify slug matches name (already implemented)

This replaces the unreliable "find LinkedIn on company website" approach with a direct Google search.

### 5d. Gemini Flash-Lite for LLM Role Fallback

For leads where Serper rule-based matching is inconclusive, use the **Gemini 2.5 Flash-Lite free tier** (1,000 RPD) as an LLM role verifier — same model family the validator uses.

Cost: $0 (within free tier). Only ~500-1000 leads/day need LLM fallback.

---

## 6. Implementation Status

| Component | Status | File |
|---|---|---|
| P0 local filters (email, name, LinkedIn format) | Done | `main_leads.py:validate_lead()` |
| MX record pre-check | Done | `main_leads.py:_check_mx_record()` |
| Role pre-verify via Serper | Done | `main_leads.py:_verify_role_via_serper()` |
| ICP fuzzy matching | Done | `main_leads.py:_check_icp_fuzzy_match()` |
| LinkedIn slug-name matching | Done | `main_leads.py:_check_linkedin_slug_name_match()` |
| LinkedIn search + discovery via Serper | Done | `main_leads.py:_search_linkedin_via_serper()` |
| Deep crawl for team pages | Done | `crawl.py:_deep_crawl_to_markdown()` |
| Email SMTP/Reacher verification | Not started | — |
| Role discovery from Google snippet | Not started | — |
| Gemini LLM role fallback | Not started | — |

---

## 7. Subnet-Wide Rejection Data (subnet71.com, 2026-03-02)

Proven data from the subnet71.com dashboard API.

### Actual Rejection Breakdown (240,536 total rejections)

| Reason | Count | % |
|--------|------:|--:|
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
| Invalid Company Name | 4,732 | 2.0% |
| Invalid Employee Count | 4,569 | 1.9% |
| Unknown Error | 4,403 | 1.8% |

### Operator Comparison: Role Rejection is the Differentiator

9 operators run 108 active miners. The highest-rep operator has half the Invalid Role rejection rate of the lowest-rep operator.

| Metric | Operator #1 (`5HgV..`) | Operator #8 (`5DwF..`) |
|--------|------------------------|------------------------|
| Miners | 28 | 12 |
| Avg rep score | 31.6 | 18.7 |
| Acceptance rate | 75.4% | 79.1% |
| Subs per miner | 10,566 | 26,445 |
| Invalid Role % | **18.3%** | **37.8%** |
| Invalid Website % | 10.7% | 12.9% |
| Invalid Description % | — | 8.4% |
| Invalid Industry % | 9.7% | 7.9% |

Key observations (proven):
- Invalid Role rejection rate is **2x higher** for the low-rep operator
- The low-rep operator compensates with **2.5x more volume** per miner
- The high-rep operator has a **lower acceptance rate** (75.4% vs 79.1%) but accepted leads score 1.7x higher on average
- Rejection reason patterns are **consistent within each operator** — all miners under the same coldkey show the same distribution

### Acceptance Rate Distribution

| Bracket | Miners |
|---------|-------:|
| Below 70% | 3 |
| 70-80% | 35 |
| Above 80% | 70 |

### What Cannot Be Determined from Public API

The lead-search API does not expose lead content (role, industry, company, employee count, region, source type). Therefore:
- Which specific roles, industries, or company sizes each operator targets is unknown
- ICP match rates per operator are unknown
- Source type distribution per operator is unknown

---

## 8. Key Source Code References

| Validator Check | File:Line | Our Pre-Check |
|---|---|---|
| MX record | `automated_checks.py:650` (check_mx_record) | `_check_mx_record()` |
| Role rule-based | `stage4_helpers.py:1791-1808` (check_role_matches) | `_check_role_matches_validator()` |
| Role LLM fallback | `stage4_helpers.py:1845-1920` (validate_role_with_llm) | Future: Gemini Flash-Lite |
| Role enforcement | `stage5_verification.py:3255-3272` (role_verified check) | `_verify_role_via_serper()` |
| Industry fuzzy 80% | `pre_checks.py:251-270` (check_industry_match) | `_check_icp_fuzzy_match()` |
| Role fuzzy 60% | `pre_checks.py:307-351` (check_role_match) | `_check_icp_fuzzy_match()` |
| Country match | `pre_checks.py:354-375` (check_country_match) | `_check_icp_fuzzy_match()` |
| Email general-purpose | `automated_checks.py:345-351` (27 prefixes) | `validate_lead()` |
| Email free domain | `automated_checks.py:411-417` (20 domains) | `validate_lead()` |
| Name-email match | `automated_checks.py:193-319` (two-strategy) | `_check_name_email_match()` |
| Rate limits | `rate_limiter.py:48-51` (1000/250/20s) | N/A (gateway enforced) |
