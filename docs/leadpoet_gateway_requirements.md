# LeadPoet SN71 — Gateway & Validator Lead Requirements (from GitHub Source)

## Overview

LeadPoet (Subnet 71) uses a two-stage validation pipeline for lead submissions:

1. **Gateway** — Structural validation that happens instantly at submission time. If a lead fails any gateway check, it is rejected immediately and counts against your daily rejection limit.
2. **Validators** — Deeper verification that happens asynchronously via consensus. Validators run DNS checks, email verification (TrueList), LinkedIn verification (ScrapingDog), and LLM-based role/industry checks.

### Daily Limits

| Limit | Value | Reset |
|---|---|---|
| Submissions per day | 1,000 | 12:00 AM UTC |
| Rejections per day | 200 | 12:00 AM UTC |

Once you hit 200 rejections in a day, all further submissions are blocked until the next UTC midnight. This makes pre-validation on the miner side critical.

---

## Required Fields (15 fields)

Every lead submission must include these fields:

| # | Field | Notes |
|---|---|---|
| 1 | `business` | Company/business name |
| 2 | `full_name` | Full name of the contact |
| 3 | `first` | First name |
| 4 | `last` | Last name |
| 5 | `email` | Business email address |
| 6 | `role` | Job title / role |
| 7 | `website` | Company website URL |
| 8 | `industry` | Must match taxonomy exactly |
| 9 | `sub_industry` | Must match taxonomy exactly |
| 10 | `country` | Country name |
| 11 | `city` | City name |
| 12 | `linkedin` | Personal LinkedIn URL |
| 13 | `company_linkedin` | Company LinkedIn URL |
| 14 | `source_url` | URL where lead was sourced |
| 15 | `description` | Company/person description |
| 16 | `employee_count` | Company size range |

**Special cases:**
- `state` is **REQUIRED** for US leads only
- **Name validation:** The gateway requires `full_name` OR both `first` AND `last`. Best practice is to provide all three.

---

## Field-by-Field Validation Rules

### Email

#### Format Validation
- **RFC-5322 regex:** `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`
- **RFC-6531 (Unicode):** `^[\w._%+-]+@[\w.-]+\.[a-zA-Z]{2,}$`

#### Plus Sign Rejection
- Emails containing `+` in the local part are **REJECTED**
- This is an anti-duplicate gaming measure (e.g., `john+1@example.com` is rejected)

#### 27 General-Purpose Prefixes Blocked
The following email prefixes are blocked (exact match, case-insensitive):

```
info@          hello@         owner@         ceo@           founder@
contact@       support@       team@          admin@         office@
mail@          connect@       help@          hi@            welcome@
inquiries@     general@       feedback@      ask@           outreach@
communications@ crew@        staff@         community@     reachus@
talk@          service@
```

#### 20 Free Email Domains Blocked
The following domains are blocked (exact match):

```
gmail.com         googlemail.com    yahoo.com         yahoo.co.uk
yahoo.fr          outlook.com       hotmail.com       live.com
msn.com           aol.com           mail.com          protonmail.com
proton.me         icloud.com        me.com            mac.com
zoho.com          yandex.com        gmx.com           mail.ru
```

#### Disposable Email Domains
- Blocked via the PyPI `disposable_email_domains` package
- This is a large, maintained list of temporary/throwaway email providers

#### TrueList Verification (Validator Stage 3)
- Only `email_ok` status passes
- **`accept_all` (catch-all domains) = REJECTED** — this is a common gotcha
- All other statuses rejected: `failed_no_mailbox`, `disposable`, `role`, `invalid`, `spam_trap`

---

### Name-Email Matching (Stage 0 — instant reject if no match)

This is one of the most common rejection reasons. The validator checks that the person's name appears in the email address local part.

#### Normalization
Names are normalized before matching:
```python
re.sub(r'[^a-z0-9]', '', name.lower())
```
This strips all non-alphanumeric characters and lowercases.

#### MIN_NAME_MATCH_LENGTH = 3
Name fragments shorter than 3 characters are skipped.

#### Strategy 1 — Pattern Matching in Local Part
Checks if any of these patterns exist in the email local part:
- `first_name` appears in local part (min 3 chars) — e.g., `john` in `john.doe@company.com`
- `last_name` appears in local part (min 3 chars) — e.g., `doe` in `john.doe@company.com`
- `{first}{last}` combined — e.g., `johndoe@company.com`
- `{first[0]}{last}` (first initial + last) — e.g., `jdoe@company.com`
- `{last}{first[0]}` (last + first initial) — e.g., `doej@company.com`

#### Strategy 2 — Prefix Matching
- `local_part` is a prefix of `first_name` — e.g., `greg@...` matches `gregory`
- `local_part` is a prefix of `last_name`
- First-name prefixes of length 3-6 checked against local part
- Last-name prefixes of length 3-6 checked against local part

**Key takeaway:** If the email is something like `sales@company.com` or `info@company.com`, it will fail this check AND the general-purpose prefix check. The email MUST contain some form of the person's name.

---

### Name Fields (first, last, full_name)

#### Forbidden Characters
No commas, periods, parentheses, brackets, braces, or digits:
```
regex: [,.\(\)\[\]\{\}0-9]
```

#### No All-Caps Words (3+ characters)
```
regex: \b[A-Z]{3,}\b
```
This blocks credentials and suffixes like: MBA, PhD, CPA, SPHR, III, CEO, CFO

#### Blocklist (case-insensitive)
The following strings in name fields cause rejection:
```
ii, iv, jr, sr, dr, mr, mrs, ms, prof, phd, mba, rn, cpa, esq,
dds, np, lcsw, pmp, cfa, cfp, cissp, sphr, scp
```

#### Additional Rules
- `first` and `last` must **NOT** be identical (case-insensitive)
- `first` and `last` must **NOT** both be all lowercase
- `full_name` must **start with** `first` AND **end with** `last` (case-sensitive)

**Key principle:** "Miner must submit the exact name from LinkedIn." Don't apply `.title()` or other transformations that change the case. Use the name exactly as it appears on the LinkedIn profile.

---

### LinkedIn URLs

#### Personal LinkedIn (`linkedin` field)
- Must contain `"linkedin.com"`
- Must contain `"/in/"`
- Must **NOT** contain `"/company/"`

**Valid:** `https://www.linkedin.com/in/johndoe`
**Invalid:** `https://www.linkedin.com/company/acme`

#### Company LinkedIn (`company_linkedin` field)
- **REQUIRED** field
- Must contain `"linkedin.com/company/"`
- Must **NOT** contain `"/in/"`

**Valid:** `https://www.linkedin.com/company/acme-corp`
**Invalid:** `https://www.linkedin.com/in/johndoe`

---

### Role (48 Validation Checks)

The role field undergoes extensive validation grouped into categories:

#### Basic Checks
- Minimum 3 characters
- Maximum 80 characters
- Must contain at least one letter
- Digit ratio must be below threshold

#### Spam Detection
- No URLs in role
- No email addresses in role
- No phone numbers in role
- Scam phrases blocked

#### Character Restrictions
- No non-Latin scripts (Cyrillic, CJK, Arabic, etc.)
- No accented characters
- No emoji
- No special characters: `% @ # $ ^ * [ ] { } | ; \ ~ < > ? +`
- No website domain patterns

#### Format Rules
- No achievement statements (e.g., "grew revenue by 300%")
- No incomplete titles ending with "of" (e.g., "Director of")
- No company name patterns in the role

#### Anti-Gaming Detection
- No repeated characters (4+ consecutive, e.g., "aaaa")
- No words repeated 3+ times
- No gibberish — must have minimum 15% vowel ratio
- No typos — dictionary check applied

#### Non-Job-Title Blocking
The following are NOT valid job titles and will be rejected:
- **Status words:** student, intern, retired, volunteer, hobbyist
- **Pronouns:** he/him, she/her, they/them
- **Job-seeking status:** "looking for opportunities", "open to work"
- **Aspirational:** "aspiring CEO", "future engineer"
- **Taglines:** "helping companies scale...", "passionate about..."
- **Standalone generic terms:** professional, expert, freelancer, entrepreneur (alone, without a specific domain)
- **Certifications alone:** CPA, PMP, CISSP (without an actual title)
- **Skills as roles:** Python, SQL, JavaScript, Excel
- **Languages:** English, Spanish, French (as a role)
- **Experience statements:** "10+ years in sales"
- **Hashtags:** #OpenToWork, #Hiring

#### Cross-Field Checks
- Person's name appearing in the role → rejected
- Company name appearing in the role → rejected
- Geographic location at end of role → rejected (e.g., "Sales Manager, New York")

---

### Description

#### Length Requirements
- Minimum 70 characters
- Maximum 2,000 characters
- Minimum 50 letters (not just spaces/punctuation)
- Minimum 15% vowel ratio (catches gibberish)

#### Rejection Patterns
| Pattern | Example |
|---|---|
| Truncated text | Ends with `"..."` |
| LinkedIn follower counts | "500+ connections" |
| Navigation text | "Home About Contact" |
| Non-Latin / garbled Unicode | Mixed encoding artifacts |
| Arabic/Thai mixed with English | Script mixing |
| Repeated characters (5+) | "aaaaaa" |
| Just a URL | Only a link, no text |
| Email addresses >30% of content | Mostly email addresses |
| Placeholders | "company description", "N/A", "lorem ipsum", "test description" |
| Formatting artifacts | Starts with `\|` (pipe character) |

---

### Industry & Sub-Industry

Must be an **exact match** from the 725-entry taxonomy in `gateway/utils/industry_taxonomy.py`. Case-insensitive matching is allowed.

#### 50 Parent Industries

```
Administrative Services          Advertising
Agriculture and Farming          Apps
Artificial Intelligence          Biotechnology
Blockchain and Cryptocurrency    Clothing and Apparel
Collaboration                    Commerce and Shopping
Community and Lifestyle          Consumer Electronics
Consumer Goods                   Content and Publishing
Data and Analytics               Design
Education                        Energy
Events                           Financial Services
Food and Beverage                Gaming
Government and Military          Hardware
Health Care                      Information Technology
Internet Services                Lending and Investments
Manufacturing                    Media and Entertainment
Messaging and Telecommunications Mobile
Music and Audio                  Natural Resources
Navigation and Mapping           Payments
Physical Infrastructure          Platforms
Privacy and Security             Professional Services
Real Estate                      Sales and Marketing
Science and Engineering          Social Impact
Software                         Sports
Sustainability                   Transportation
Travel and Tourism               Video
```

Each parent industry has multiple sub-industries. Both the industry AND sub_industry must match a valid parent-child pair in the taxonomy.

---

### Employee Count

Required field. Must be one of these exact string values:

```
"0-1"
"2-10"
"11-50"
"51-200"
"201-500"
"501-1,000"
"1,001-5,000"
"5,001-10,000"
"10,001+"
```

Note the comma formatting in `"501-1,000"`, `"1,001-5,000"`, and `"5,001-10,000"`.

---

### Location

| Field | Required | Notes |
|---|---|---|
| `country` | Always | All leads must have a country |
| `city` | Always | All leads must have a city |
| `state` | US only | Required when country is US |

#### US Detection Aliases
The following values (case-insensitive) are treated as United States:
```
"united states", "usa", "us", "u.s.", "u.s.a.", "america", "united states of america"
```

#### Normalization Examples
The gateway normalizes common abbreviations:
- `SF` → `San Francisco`
- `CA` → `California`
- `USA` → `United States`
- `Bombay` → `Mumbai`

199 countries are supported in the geo normalization module.

---

### Source URL

- **Required** field
- The gateway performs an HTTP HEAD check to verify the URL is reachable
- **Denylist:** URLs from data providers are blocked, including:
  - ZoomInfo
  - Apollo
  - Other data aggregator/scraping platforms

---

## Validation Pipeline Order

### Gateway (Instant — structural)

All checks happen synchronously at submission time. Failure = immediate rejection.

| # | Check | Details |
|---|---|---|
| 1 | Rate limit | 1000/day submissions, 200/day rejections |
| 2 | Payload hash | SHA-256 integrity verification |
| 3 | Signature | Ed25519 cryptographic signature from miner hotkey |
| 4 | Miner registration | Hotkey must be registered on SN71 |
| 5 | Nonce validation | Must be UUID v4, prevents replay attacks |
| 6 | Timestamp verification | Must be recent (prevents stale submissions) |
| 7 | Email hash integrity | Prevents blob substitution attacks |
| 8 | LinkedIn combo hash | Duplicate detection across all miners |
| 9 | Field validation | All the field-level checks described above |

### Validator Stage 0 (Hardcoded — instant)

These are hard checks — failure = lead rejected with no recourse.

| # | Check | Type |
|---|---|---|
| 1 | `check_required_fields` | HARD |
| 2 | `check_email_regex` | HARD |
| 3 | `check_name_email_match` | HARD |
| 4 | `check_general_purpose_email` | HARD |
| 5 | `check_free_email_domain` | HARD |
| 6 | `check_disposable` | HARD |

### Validator Stage 1 (DNS)

| # | Check | Type | Details |
|---|---|---|---|
| 7 | `check_domain_age` | HARD | Domain must be at least 7 days old |
| 8 | `check_mx_record` | HARD | Domain must have MX records |
| 9 | `check_spf_dmarc` | SOFT | Never rejects — informational only |

### Validator Stage 2 (DNSBL)

| # | Check | Type | Details |
|---|---|---|---|
| 10 | `check_dnsbl` | HARD | Cloudflare Domain Block List check |

### Validator Stage 3 (External Email Verification)

| # | Check | Type | Details |
|---|---|---|---|
| 11 | TrueList batch verification | HARD | Only `email_ok` passes. `accept_all` (catch-all) = rejected |

### Validator Stage 4 (LinkedIn Verification)

| # | Check | Type | Details |
|---|---|---|---|
| 12 | `check_linkedin_gse` | HARD | ScrapingDog Google search verification — validates the person exists on LinkedIn |

### Validator Stage 5 (Company Verification)

| # | Check | Type | Details |
|---|---|---|---|
| 13 | `check_stage5_unified` | HARD | Role/Region/Industry verification via ScrapingDog + LLM |

### Rep Score (SOFT — never rejects, adds 0-48 points)

These checks only add bonus points to the lead's reputation score. They never cause rejection.

| # | Check | Points | Details |
|---|---|---|---|
| 14 | Wayback Machine | 0-6 pts | Company website archive history |
| 15 | SEC Edgar | 0-12 pts | Public company filings |
| 16 | WHOIS/DNSBL Reputation | 0-10 pts | Domain registration quality |
| 17 | GDELT mentions | 0-10 pts | Global news/media mentions |
| 18 | Companies House | 0-10 pts | UK company registry |

---

## Reward Formula

```
miner_reward ∝ Σ(rep_score for all approved leads from that miner)
```

- Uses a **rolling 30-epoch history**
- **Enterprise companies (10,001+ employees):** rep score capped at:
  - 10 points with ICP match
  - 5 points without ICP match
- Higher rep scores come from verified, established companies with public records

---

## Our Miner Compliance Status

| Requirement | Status | Notes |
|---|---|---|
| Required fields (15+) | Done | All fields populated including `hq_country` (REQUIRED) |
| Email regex | Done | Basic `@` check |
| General-purpose email filter | **Done** | 27-prefix blocklist in `validate_lead()` |
| Free email domain filter | **Done** | 20-domain blocklist in `validate_lead()` |
| Email `+` rejection | **Done** | Plus sign check in `validate_lead()` |
| Name-in-email match | **Done** | Two-strategy matching in `_check_name_email_match()` |
| Disposable email filter | Missing | Need `disposable_email_domains` package |
| Name case validation | Partial | We do `.title()` but gateway wants exact LinkedIn case, no credentials |
| LinkedIn personal format | Done | Contains `/in/` |
| LinkedIn company format | **Done** | `_fix_company_linkedin()` ensures `/company/` format |
| Role sanity (basic) | **Done** | Min 3 / max 80 chars, must have letter, no non-Latin in `_check_role_sanity()` |
| Role sanity (full 48 checks) | Partial | Only basic checks implemented |
| Description sanity | Partial | Length padding done, but no content quality checks |
| Sub-industry taxonomy | Done | Cascading match implemented |
| Employee count format | Done | `normalize_employee_count()` |
| Location normalization | Done | `normalize_location()` |
| Source URL | Done | From website crawl |
| Domain age (7+ days) | N/A | Validator check, not miner |
| MX record | N/A | Validator check |
| TrueList email | N/A | Validator uses paid API |
| LinkedIn ScrapingDog | N/A | Validator uses paid API — biggest gap |

---

## Priority Fixes (ordered by impact)

### P0 — Will cause instant Stage 0 rejection (ALL DONE)

These are the most critical. Every lead that fails Stage 0 is immediately rejected and counts against the 200/day rejection limit.

1. ~~**Add general-purpose email prefix blocklist (27 prefixes)**~~ — DONE (`validate_lead()`)
2. ~~**Add free email domain blocklist (20 domains)**~~ — DONE (`validate_lead()`)
3. ~~**Add name-in-email matching check**~~ — DONE (`_check_name_email_match()`)
4. ~~**Reject emails with `+` in local part**~~ — DONE (`validate_lead()`)
5. ~~**Fix `company_linkedin` to always use `/company/` format**~~ — DONE (`_fix_company_linkedin()`)

### P1 — Will cause gateway rejection (PARTIAL)

6. ~~**Add basic role sanity checks**~~ — DONE (basic: min/max length, letter check, non-Latin rejection)
7. **Improve description quality checks** — TODO: Minimum 50 letters, 15% vowel ratio, no placeholder text

### P2 — Will improve validator approval rate

8. **Add disposable email domain check** — Install `disposable_email_domains` package and check against it
9. **Improve name validation** — No credentials/suffixes, no digits, preserve exact LinkedIn case instead of `.title()`
10. **Pre-verify LinkedIn URLs exist** — Requires ScrapingDog API key, but would prevent Stage 4 rejections

---

## Official Lead Template (Required Fields)

The following fields are required by the gateway for lead submission. Note: `hq_country` is REQUIRED (our miner already populates it via `normalize_location()`).

```json
{
  "business": "Company Name",
  "full_name": "First Last",
  "first": "First",
  "last": "Last",
  "email": "first.last@company.com",
  "role": "Job Title",
  "website": "https://company.com",
  "industry": "Must match taxonomy",
  "sub_industry": "Must match taxonomy",
  "country": "United States",
  "state": "California",
  "city": "San Francisco",
  "hq_country": "United States",
  "hq_state": "California",
  "hq_city": "San Francisco",
  "linkedin": "https://www.linkedin.com/in/first-last",
  "company_linkedin": "https://www.linkedin.com/company/company-name",
  "source_url": "https://company.com",
  "description": "Minimum 70 chars, minimum 50 letters, 15% vowel ratio...",
  "employee_count": "11-50",
  "phone_numbers": [],
  "founded_year": "2020",
  "ownership_type": "Private",
  "company_type": "",
  "number_of_locations": "1",
  "socials": {}
}
```

---

## Reference

| Resource | Location |
|---|---|
| GitHub Repository | https://github.com/leadpoet/leadpoet |
| Gateway submission validation | `gateway/api/submit.py` |
| Validator automated checks | `validator_models/automated_checks.py` |
| Email-specific checks | `validator_models/checks_email.py` |
| Industry taxonomy (725 entries) | `gateway/utils/industry_taxonomy.py` |
| Geo normalization | `gateway/utils/geo_normalize.py` |

---

*Generated: 2026-03-01, updated: 2026-03-01 (P0 filters implemented)*
