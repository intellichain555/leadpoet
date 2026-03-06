# CSV Refine Pipeline — Lead Refinement Rules
**Date:** 2026-03-03
**Mode:** `csv_refine` (default miner mode)
**Source:** `data/csv_leads.json` (968 leads from LinkedIn CSV export)

---

## Implementation Status

**Implemented** as of 2026-03-03.

`get_leads_csv_refine()` in `miner_models/lead_sorcerer_main/main_leads.py` runs the full 7-step pipeline described below. The original 10-step spec was consolidated: Steps 7–9 from the spec (HQ location, source provenance, gateway pre-check) are combined into a single Step 7 gateway pre-check; Step 10 (validator pre-check) is handled downstream by `process_generated_leads`.

---

## Core Principle

**Distrust all CSV fields.** The CSV is a LinkedIn export — roles are self-written headlines, locations are profile locations (not company HQ), industries are LinkedIn-declared, descriptions are absent. The **company website is the only source of truth.** Every field must be re-derived or verified from the website crawl before submission.

---

## Pipeline Overview

The spec described 10 steps; the implementation consolidated to 7. Steps 7–9 from the original spec (HQ location, source provenance, full gateway pre-check) are merged into a single Step 7. Step 10 (validator pre-check) runs downstream in `process_generated_leads` and is not part of `get_leads_csv_refine()`.

```
CSV lead (email + personal LinkedIn as anchors)
    │
    ▼ STEP 1: Website reachability (crawl4ai)
    │   _csv_deep_crawl() → combined markdown
    │   REJECT if unreachable
    │
    ▼ STEP 2: Company data extraction (LLM)
    │   _csv_llm_extract() using _CSV_REFINE_SCHEMA / _CSV_REFINE_PROMPT
    │   Injects: description, hq_country, hq_state, hq_city,
    │            company_linkedin, employee_count, sub_industry
    │
    ▼ STEP 3: Email MX check + Serper personal LinkedIn verification
    │   DNS MX lookup → REJECT if no MX records
    │   Serper search → replace LinkedIn URL if better match found
    │
    ▼ STEP 4: Name refinement
    │   _refine_name(): strip credentials (MBA, PhD, etc.),
    │   strip parenthetical parts, strip digits,
    │   normalize all-lowercase → title case
    │
    ▼ STEP 5: Role refinement (ICP matching)
    │   _refine_role_icp(): clean role tokens → substring-match
    │   against _ICP_ROLES_BY_PRIORITY (priority 1→2→3)
    │   Replace with canonical ICP name
    │   REJECT if no ICP match (non-decision-maker)
    │
    ▼ STEP 6: Industry re-derivation
    │   map_sub_industry() applied to LLM-extracted sub_industry
    │   Never trust CSV industry field
    │
    ▼ STEP 7: Full gateway pre-check
        Calls exact gateway functions:
          check_role_sanity()
          check_description_sanity()
          check_linkedin_url_format()
          check_industry_taxonomy()
          validate_location() — for person location
          validate_location() — for HQ location
        REJECT if any check fails
        _source_url_validated = True → skips redundant re-check downstream
```

---

## Step 1 — Website Reachability (crawl4ai)

**Input:** `lead["website"]`

**Action:**
- Use `crawl4ai.AsyncWebCrawler` (already in btcli_venv) to fetch the website
- Use `_deep_crawl_to_markdown(domain, max_pages=8)` from `src/crawl.py`
  - Prioritizes pages: `/team`, `/about`, `/leadership`, `/contact`, `/founders`
- **REJECT** the lead if no pages are reachable (all return HTTP ≥ 400 or timeout)

**Output:** `combined_markdown` — all pages concatenated

**Reuse:** `_extract_with_crawl4ai()` and `_deep_crawl_to_markdown()` in
`miner_models/lead_sorcerer_main/src/crawl.py`

---

## Step 2 — Company Data Extraction (LLM)

**Input:** `combined_markdown` from Step 1

**Action:**
- Call `_llm_extract_structured_data(markdown, prompt, FIRECRAWL_EXTRACT_SCHEMA)`
  from `src/crawl.py` (uses Chutes API, model: `chutesai/Mistral-Small-3.2-24B-Instruct-2506`)
- Schema already covers all needed fields: `company.description`, `company.industry`,
  `company.sub_industry`, `company.hq_city`, `company.hq_state`, `company.hq_country`,
  `company.linkedin_url`, `company.employee_count`

**Fields injected from LLM result (overwrite CSV values):**

| Lead field | LLM source | Notes |
|-----------|-----------|-------|
| `description` | `company.description` | Must be ≥ 70 chars after injection |
| `industry` | Derived in Step 6 | Re-derived, not from LLM directly |
| `sub_industry` | Derived in Step 6 | Re-derived, not from LLM directly |
| `hq_country` | `company.hq_country` | Normalized via `normalize_country()` |
| `hq_state` | `company.hq_state` | Required for US |
| `hq_city` | `company.hq_city` | Required for US |
| `employee_count` | `company.employee_count` | Normalized via `normalize_employee_count()` |
| `source_url` | Website URL that was crawled | The actual page URL |

**Company LinkedIn URL — compare and replace logic:**

1. Extract `company.linkedin_url` from LLM result
2. Normalize both the LLM result and the CSV original:
   - Strip `www.` prefix
   - Ensure scheme: `https://`
   - Remove subpaths after slug: `/company/{slug}` → keep only this, strip `/about`, `/posts`, `/jobs`, query strings, `...`
   - Strip trailing slashes
   - Canonical form: `https://www.linkedin.com/company/{slug}/`
3. Compare slugs (case-insensitive)
4. **If LLM found a URL and slugs differ** → replace with LLM-found URL (website is more authoritative than LinkedIn export)
5. **If LLM found no URL** → keep CSV original, verify it's reachable via HEAD request
6. **If neither has a valid URL** → REJECT (company LinkedIn is required)

**Company LinkedIn URL normalization regex:**
```python
# Extract slug from any LinkedIn company URL variant
re.search(r'linkedin\.com/company/([^/?#\s\.]+)', url)
# Canonical form
f"https://www.linkedin.com/company/{slug}/"
```

---

## Step 3 — Email + Personal LinkedIn Verification (Serper)

**Priority:** These are checked FIRST. Email is the deduplication key. Personal LinkedIn is the validator's primary verification target. If either is broken, all other work is wasted.

### 3a — Email check (MX record)

- DNS MX lookup on email domain
- **REJECT** if: no MX records, domain does not exist (NXDOMAIN)
- Also apply existing `validate_lead()` P0 checks:
  - No `+` in local part
  - Not a generic prefix (`info@`, `hello@`, `ceo@`, `contact@`, etc.)
  - Not a free domain (`gmail.com`, `yahoo.com`, etc.)

### 3b — Personal LinkedIn verification (Serper)

- Search: `"{full_name}" "{business}" site:linkedin.com/in/`
- Normalize the Serper result URL (same slug extraction as company LinkedIn)
- Compare slugs with CSV `lead["linkedin"]`
- **If match** → confirmed, continue
- **If different slug** → replace `lead["linkedin"]` with Serper-found URL (fallback)
- **If Serper finds nothing** → keep CSV original, do not reject (Serper may miss some profiles)
- **If CSV linkedin is clearly wrong** (no `/in/`, points to company page, wrong person) → REJECT

*Note: Email and personal LinkedIn **discovery** (finding new ones) is NOT performed in csv_refine mode. We only verify/replace the existing CSV values.*

### 3c — Name cross-check

- After verifying LinkedIn URL, check if name appears in website content (`combined_markdown`)
- If name appears → good signal, continue
- If name does NOT appear → not a reject (many sites don't list team members by name)
- Apply gateway name rules (Step 9 will catch anyway, but autofix here):
  - Strip credential suffixes: `Jr`, `Sr`, `Dr`, `MBA`, `PhD`, `CPA`, `Esq`, `CFA`, `PMP`, `SPHR`
  - Strip parenthetical parts: `John Smith (CEO)` → `John Smith`
  - Strip digits
  - Normalize case: if all-lowercase, title-case it
  - Verify `full_name` starts with `first` and ends with `last`

---

## Step 4 — Role Refinement

### 4a — Clean the raw role string

Apply in order:
1. Strip company name from role (start or end): `"CEO & Founder, Acme Corp"` → `"CEO & Founder"`
2. Strip person name from role: remove first/last name tokens
3. Strip geographic tokens: city, state, country, region names (APAC, EMEA, US, etc.)
4. Replace ` | ` with ` / `
5. Remove bad gateway chars: `% @ # $ ^ * [ ] { } \ `` ~ < > ? +`
6. Strip trailing special chars: `. , ; : - /`
7. Strip accented Latin characters: `[àâäéèêëïîôùûüÿçñáíóúÀÂÄÉÈÊËÏÎÔÙÛÜŸÇÑÁÍÓÚßöÖ]`
8. Truncate to 80 chars at natural separator (` / `, `, `, `: `)

### 4b — ICP role matching and replacement

**ICP role priority list** (from `icp_crunchbase_us.json` and `icp_config.json`):

| Priority | Canonical role names |
|----------|---------------------|
| 1 (top) | `CEO`, `CTO`, `Co-Founder`, `Founder`, `Owner`, `President`, `Managing Partner` |
| 2 | `COO`, `CFO`, `CMO`, `Partner`, `Chief Revenue Officer`, `Chief Growth Officer`, `Chief Strategy Officer`, `Chief Technology Officer`, `Chief Product Officer`, `VP of Engineering`, `VP of Sales`, `VP of Marketing`, `VP of Operations`, `General Manager` |
| 3 | `Director of Engineering`, `Director of Marketing`, `Director of Sales`, `Director of Operations`, `Head of Growth`, `Head of Sales` |

**Matching logic:**
```
cleaned_role_lower = clean_role.lower()
for priority in [1, 2, 3]:
    for icp_name in icp_roles[priority]:
        if icp_name.lower() in cleaned_role_lower:
            → replace lead["role"] with canonical ICP name (title-cased)
            → break
if no ICP match found:
    → lead fails ICP fuzzy match → REJECT
    (We only submit decision-maker leads)
```

**Example replacements:**
- `"Ceo | Owner"` → `"CEO"` (first ICP match at priority 1)
- `"Founder and CEO, AchieveUnite"` → `"Founder"` (after stripping company name)
- `"Co-Founder & CEO"` → `"Co-Founder"` (first priority-1 match)
- `"Senior VP of Sales and Marketing"` → `"VP of Sales"` (priority-2 match)

### 4c — Gateway role check

After replacement, call `check_role_sanity()` from `gateway/api/submit.py`:
```python
from gateway.api.submit import check_role_sanity
err, msg = check_role_sanity(
    lead["role"],
    full_name=lead["full_name"],
    company=lead["business"],
    city=lead["city"],
    state=lead["state"],
    country=lead["country"],
    industry=lead["industry"],
)
if err:
    → REJECT (role did not pass even after cleaning)
```

---

## Step 5 — Industry + Sub-Industry

**Rule:** Never trust the CSV `industry` field. Always re-derive from website content.

**Action:**
- Use `map_sub_industry()` from `main_leads.py` applied to LLM-extracted `company.industry` + `company.specialties`
- Cross-check with `check_industry_taxonomy(industry, sub_industry)` from `gateway/api/submit.py`
- **REJECT** if no valid taxonomy mapping can be found

**Fallback:** If LLM extracted no industry signal → use `"Consulting"` / `"Professional Services"` as default (appropriate for our CSV's management consulting dataset)

---

## Step 6 — HQ Location

**Same as current implementation.** No changes needed.

**Accepted cases:**
1. `hq_city="Remote"`, `hq_state=""`, `hq_country=""` — fully remote company
2. `hq_country="United States"`, `hq_state` required, `hq_city` required
3. `hq_country="United Arab Emirates"`, `hq_city` in `{"Dubai", "Abu Dhabi"}`, `hq_state=""`

**Source:** LLM-extracted `company.hq_country/state/city` from Step 2, normalized via `normalize_country()` from `gateway/utils/geo_normalize.py`

**REJECT** if HQ does not match any accepted case.

---

## Step 7 — Source Provenance

**Same as current implementation.**

- `source_url` = the company website URL that was crawled
- `source_type` = `"company_site"` (default for website crawl)
- `license_doc_hash`, `license_doc_url` = empty (not a licensed resale)
- `_source_url_validated = True` flag set → skip redundant re-check in `process_generated_leads`

---

## Step 8 — Full Gateway Pre-Check

Call gateway validation functions directly. Any failure → **REJECT** (log reason, mark state as `"failed"`).

```python
from gateway.api.submit import (
    check_role_sanity,
    check_description_sanity,
    check_linkedin_url_format,
    check_industry_taxonomy,
)
from gateway.utils.geo_normalize import validate_location

# Role (already done in Step 4c, but re-run after all changes)
err, _ = check_role_sanity(role, full_name, business, city, state, country, industry)

# Description
err, _ = check_description_sanity(description)

# LinkedIn URLs
err, _ = check_linkedin_url_format(linkedin, company_linkedin)

# Industry
err, _ = check_industry_taxonomy(industry, sub_industry)

# Person location
ok, reason = validate_location(city, state, country)

# HQ location
ok, reason = validate_location(hq_city, hq_state, hq_country)
```

---

## Step 9 — Validator Pre-Check

Same as current flow. Run after gateway pre-check passes.

```
validate_lead()          → email P0, name-email match, LinkedIn format, role sanity
_check_mx_record()       → email domain MX records
_check_icp_fuzzy_match() → role fuzzy ≥ 60% + geographic focus
validate_source_url()    → source URL reachability (skip if _source_url_validated=True)
```

---

## State Tracking

Each lead's processing state is saved in `data/curated/csv_refine_state.jsonl`:

```json
{"email": "...", "status": "done", "ts": "...", "role_replaced": "CEO", "company_linkedin_replaced": true}
{"email": "...", "status": "failed", "reason": "role: no ICP match", "ts": "..."}
{"email": "...", "status": "failed", "reason": "website: HTTP 404", "ts": "..."}
```

Leads marked `"done"` or `"failed"` are skipped on subsequent runs.

---

## Implementation Notes

**crawl4ai** is installed in `btcli_venv` (v0.8.0). The implementation uses `_csv_deep_crawl()` and `_csv_llm_extract()` defined directly in `main_leads.py` rather than reusing `src/crawl.py`. These are purpose-built for the csv_refine schema and prompt (`_CSV_REFINE_SCHEMA`, `_CSV_REFINE_PROMPT`).

**LLM:** NVIDIA NIM API (`https://integrate.api.nvidia.com/v1`), model `qwen/qwen3-next-80b-a3b-instruct` (OpenAI-compatible). Not the Chutes API as originally specified.

**Gateway function imports** are at module level (not inside the function), using sentinel flags to handle import failures gracefully:
```python
# Module-level in main_leads.py
_GW_FUNCS_AVAILABLE = False
try:
    from gateway.api.submit import check_role_sanity as _gw_check_role_sanity
    from gateway.api.submit import check_description_sanity as _gw_check_description_sanity
    from gateway.api.submit import check_linkedin_url_format as _gw_check_linkedin_url_format
    from gateway.api.submit import check_industry_taxonomy as _gw_check_industry_taxonomy
    from gateway.utils.geo_normalize import validate_location as _gw_validate_location
    _GW_FUNCS_AVAILABLE = True
except ImportError:
    pass
```

**ICP role constants** (`_ICP_CANONICAL_ROLES`, `_ICP_ROLES_BY_PRIORITY`) are defined at module level. `_refine_role_icp()` uses these directly.

**Processing is sequential** (not concurrent batch_size=3 as originally specced) to avoid hammering crawl4ai and the LLM API. One lead at a time.

**Removed functions:** `_validate_refine_fields`, `_autofix_refine_fields`, and `_fetch_and_validate` were replaced entirely by the 7-step pipeline and are no longer present.

**New functions added:** `_extract_company_li_slug`, `_resolve_company_linkedin`, `_refine_name`, `_refine_role_icp`, `_csv_deep_crawl`, `_csv_llm_extract`.

**`_source_url_validated = True`** is set on each lead before yielding, so `process_generated_leads` skips the redundant source URL reachability re-check.
