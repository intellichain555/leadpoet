# Gateway Validation Gap Analysis
**Date:** 2026-03-02
**Context:** LeadPoet miner on SN71, csv_refine mode

---

## Summary

During the csv_refine pipeline development, we focused exclusively on pre-filtering leads against the **validator scoring stages (Stage 0–5)**. We missed the fact that the **gateway has its own independent validation layer** that runs before any validator ever sees a lead. This caused a high rejection rate (~22% of submissions).

---

## The Two-Layer Architecture (What We Missed)

```
Miner submits lead
       │
       ▼
┌─────────────────────────────────┐
│         GATEWAY LAYER           │  ← We missed this entire layer
│  check_role_sanity()            │
│  check_description_sanity()     │
│  check_linkedin_url_format()    │
│  validate_location()            │
│  check_industry_taxonomy()      │
│  HQ location validation         │
│  Name validation                │
│  50+ role checks                │
│  13 description checks          │
└──────────────┬──────────────────┘
               │  Only leads that pass ALL gateway checks
               ▼
┌─────────────────────────────────┐
│       VALIDATOR LAYER           │  ← What we were optimizing for
│  Stage 0: MX record             │
│  Stage 1: LinkedIn existence    │
│  Stage 2: Role verification     │
│  Stage 3: Domain age            │
│  Stage 4: Website reachability  │
│  Stage 5: Description quality   │
└─────────────────────────────────┘
```

A lead rejected by the gateway **never reaches validators** and **counts against the daily rejection limit** (max 250/day). So gateway rejections are doubly harmful.

---

## Gap: Miner-Side Checks vs Gateway Checks

### ROLE field — miner covered ~7 of 50 gateway checks

| Gateway check | Error code | Miner pre-filter |
|---------------|-----------|-----------------|
| > 80 chars | `role_too_long_gaming` | ✅ |
| URL/domain in role | `role_contains_url` | ✅ |
| Non-Latin Unicode (CJK, Arabic) | `role_non_english` | ✅ |
| Bad chars `\|%@#$^*[]{}` | `role_invalid_format` | ✅ |
| Ends with special char | `role_ends_special_char` | ✅ |
| Company name in role | `role_contains_company_name` | ✅ |
| **Accented Latin (`é à ö ß`)** | `role_invalid_format` | ❌ |
| **`"at CompanyName"` pattern** | `role_invalid_format` | ❌ |
| **`"in CompanyName"` at end** | `role_invalid_format` | ❌ |
| Tagline (`. ` in role, len > 40) | `role_marketing_tagline` | ❌ |
| Multiple `.` or `!` | `role_excessive_punctuation` | ❌ |
| Bio language ("I help", "passionate") | `role_bio_description` | ❌ |
| Geo at end (APAC, EMEA, countries) | `role_geo_at_end` | ❌ |
| 100+ known typo pairs | `role_typo` | ❌ |
| No job keywords (len > 60) | `role_no_job_keywords` | ❌ |
| Achievement stat (`$5M`, `10x`) | `role_achievement_statement` | ❌ |
| Person's own name in role | `role_contains_name` | ❌ |
| Pronouns, aspiring, status | various | ❌ |

### DESCRIPTION field — miner covered 2 of 13 gateway checks

| Gateway check | Error code | Miner pre-filter |
|---------------|-----------|-----------------|
| < 70 chars | `desc_too_short` | ✅ |
| Ends with `"..."` | `desc_truncated` | ✅ |
| > 2000 chars | `desc_too_long` | ❌ |
| < 50 letters | `desc_too_few_letters` | ❌ |
| LinkedIn follower count text | `desc_linkedin_followers` | ❌ |
| Navigation/UI text | `desc_navigation_text` | ❌ |
| Gibberish (vowel ratio < 15%) | `desc_gibberish` | ❌ |
| Placeholder text | `desc_placeholder` | ❌ |

### NAME fields — miner covered 0 of 6 gateway checks

| Gateway check | Error code | Miner pre-filter |
|---------------|-----------|-----------------|
| Digits or parens in name | `name_invalid_chars` | ❌ |
| All-caps credential (MBA, PhD) | `name_credential` | ❌ |
| Title suffix (Jr, Dr, Esq, CPA) | `name_title_suffix` | ❌ |
| First name == Last name | `name_duplicate` | ❌ |
| All lowercase | `name_lowercase` | ❌ |
| full_name doesn't match first/last | `name_mismatch` | ❌ |

### LOCATION — miner covered partial

| Gateway check | Miner pre-filter |
|---------------|-----------------|
| Keywords: "region/township/county" in city | ✅ |
| City not in `geo_lookup_fast.json` | ❌ |
| State not a valid US state | ❌ |
| City/state geographic mismatch (Erie in NY) | ❌ |

---

## Root Cause of Rejections in csv_refine Mode

The 65 gateway rejections broke down as:

| Rejection reason | Count | Cause |
|-----------------|-------|-------|
| `role_invalid_format` / `role_bad_chars` | 12 | Pipe `\|` char in CSV roles |
| `invalid_hq_location` | 5 | Blank hq_city for US leads; pre-fix foreign countries |
| `role_contains_company_name` | 4 | CSV roles embed company name (e.g. "CEO & Founder, Acme Corp") |
| `invalid_region_format` | 4 | Person's city not in gateway geo_lookup DB |
| `invalid_sub_industry` | 2 | "Nonprofit" and "Investment Management" not in taxonomy |
| `desc_truncated` | 2 | Scraped meta descriptions ending with `"..."` |
| `missing_hq_country` | 3 | All HQ fields blank |
| `role_ends_special_char` | 1 | Role ending with `/` |
| Unknown / deeper role checks | ~31 | Gateway role checks not yet replicated in miner |

---

## Recommended Fix: Import Gateway Validation Directly

Since the gateway code is in the same repository, the miner can call the **exact same functions** instead of reimplementing them:

```python
# In miner_models/lead_sorcerer_main/main_leads.py
import sys
sys.path.insert(0, "/home/ubuntu/leadpoet")

from gateway.api.submit import (
    check_role_sanity,
    check_description_sanity,
    check_linkedin_url_format,
    check_industry_taxonomy,
)
from gateway.utils.geo_normalize import validate_location
```

Then in `_validate_refine_fields()`:

```python
# Role — run the exact same 50-check function the gateway runs
role_err, role_msg = check_role_sanity(
    lead["role"],
    full_name=lead.get("full_name", ""),
    company=lead.get("business", ""),
    city=lead.get("city", ""),
    state=lead.get("state", ""),
    country=lead.get("country", ""),
    industry=lead.get("industry", ""),
)
if role_err:
    issues.append(("role", role_err))

# Description
desc_err, desc_msg = check_description_sanity(lead.get("description", ""))
if desc_err:
    issues.append(("description", desc_err))

# Location
loc_valid, loc_reason = validate_location(
    lead.get("city", ""), lead.get("state", ""), lead.get("country", "")
)
if not loc_valid:
    issues.append(("city", loc_reason))
```

This replaces the entire hand-rolled `_validate_refine_fields()` role/desc/location logic with the authoritative gateway version — **zero chance of disagreement**.

---

## Original Strategy vs csv_refine: Why Fewer Errors Before

The **original miner mode** (Serper domain discovery → lead generation) produced significantly fewer gateway rejections for these reasons:

### 1. Role quality
- **Original:** Roles extracted from the **real company website** — "About", "Team", and "Leadership" pages crawled via Playwright. These pages display formal, structured job titles written by the company itself (e.g. "Chief Executive Officer", "Co-Founder & CEO"). The extraction pipeline then runs `validate_lead()` → `_check_role_sanity()` during generation, so bad formats are caught before a lead is even created.
- **csv_refine:** Roles come verbatim from a raw CSV export of **LinkedIn headline fields**. LinkedIn headlines are written by the individuals themselves and regularly contain company names, pipe characters, taglines, and marketing language (e.g. `"CEO & Founder, Projected Growth Consulting"`, `"Ceo | Owner"`, `"Fractional COO/CPO/CHRO Services. Reduce Cost"`). These never passed through any role validation before landing in the CSV.

### 2. Description quality
- **Original:** Descriptions freshly scraped from the **real company website** via Playwright (full browser render). Full-page rendering captures complete, well-formed company descriptions from About pages and structured data — not truncated meta tags.
- **csv_refine:** Descriptions fetched via a lightweight HTTP GET + HTML meta tag parser. Many sites return short, truncated, or missing `<meta name="description">` values. Navigation text and LinkedIn snippets slip through.

### 3. Location data
- **Original:** Locations extracted from the **real company website** — footer addresses, contact pages, structured data. These reflect the company's actual published address, which is clean and geocoded to a real city.
- **csv_refine:** CSV location data is the person's **LinkedIn profile location**, not necessarily the company address. These fields have quality issues — some entries use planning regions as city names ("Western Connecticut Planning Region"), others have city/state mismatches from stale or incorrectly entered LinkedIn data ("Erie" listed under state "New York").

### 4. Lead source
- **Original:** Leads generated from verified company domains returned by Serper. Every company website was already confirmed reachable and indexed before lead extraction began. The pipeline discovers the company first, then finds the person — so the company data is always primary and verified.
- **csv_refine:** 968 leads from a single CSV export. The pipeline starts with the person (LinkedIn export) and tries to use their company website as a secondary source. Some websites are stale (HTTP 403/404), some location data reflects where the person lives rather than the company HQ, and roles are LinkedIn self-descriptions rather than formal titles.

### Summary table

| Dimension | Original (Serper) | csv_refine |
|-----------|-------------------|------------|
| Role source | Real company website ("Team" page) | LinkedIn headline (self-written) |
| Role format issues | Rare — formal, structured titles | Common — pipe chars, company names, taglines |
| Description source | Playwright full-page render of company site | Lightweight GET meta tag extraction |
| Description quality | High — complete About page content | Variable — short, truncated, nav text |
| Location source | Company website footer/contact page | Person's LinkedIn profile location |
| Location accuracy | High — real published company address | Variable — planning regions, stale data |
| Website freshness | Verified reachable at crawl time | Snapshot from CSV export date |
| Gateway rejection rate | Low (~2–5%) | High (~22%) |

### Why csv_refine is still worth using
Despite higher rejection rates, csv_refine has a large advantage: **968 pre-identified leads with name, email, LinkedIn, and company data already assembled**. The fix is not to abandon the mode, but to pre-filter with the gateway's own validation functions before submitting.

---

## Action Items

1. **Replace `_validate_refine_fields()`** with direct calls to `check_role_sanity()`, `check_description_sanity()`, `validate_location()`, `check_industry_taxonomy()` from the gateway module.
2. **Add name validation** using the gateway's name rules (no credentials, no lowercase, no mismatch).
3. **Use `geo_lookup_fast.json`** to pre-validate city/state combos and skip leads with unrecognized cities.
4. **For long-term:** If using csv_refine as primary mode, consider running a pre-validation pass over the full `csv_leads.json` once and generating a clean `csv_leads_validated.json` with only gateway-safe leads, to avoid wasting the fetch+validate cycle on known-bad leads each iteration.

---

## Resolution

**Date resolved:** 2026-03-03

All 4 action items are now implemented in `get_leads_csv_refine()` in `miner_models/lead_sorcerer_main/main_leads.py`:

1. **Gateway functions imported directly** — `check_role_sanity`, `check_description_sanity`, `check_linkedin_url_format`, `check_industry_taxonomy`, and `validate_location` are imported at module level (aliased as `_gw_check_role_sanity` etc., guarded by `_GW_FUNCS_AVAILABLE`). All are called in Step 7 as the final pre-submission gate.

2. **Name validation implemented** — `_refine_name()` strips credential suffixes (MBA, PhD, CPA, Esq, etc.), strips parenthetical parts (`John Smith (CEO)` → `John Smith`), removes digits, and normalizes all-lowercase strings to title case. Applied in Step 4.

3. **`geo_lookup_fast.json` validation** — `_gw_validate_location()` (i.e. `validate_location` from `gateway/utils/geo_normalize.py`) is called in Step 7 for both person location and HQ location. This uses the same `geo_lookup_fast.json` the gateway uses, so city/state mismatches and unrecognized cities are caught before submission.

4. **Role handling** — `_refine_role_icp()` (Step 5) cleans the raw CSV role string (strips company name, person name, geo tokens, bad chars), then does ICP substring matching against `_ICP_ROLES_BY_PRIORITY` (priority 1→2→3). Leads with no ICP match are rejected before any crawl work is wasted. `check_role_sanity()` is then re-run in Step 7 on the already-cleaned canonical role.

**Note on action item 4 (pre-validation pass):** A separate pre-validation pass was not implemented as a standalone filter step. Instead, the full pipeline handles rejection per-lead with state tracking in `data/curated/csv_refine_state.jsonl`. Failed leads are recorded with their rejection reason and are never re-processed on subsequent runs, achieving the same goal of not wasting crawl work on known-bad leads.
