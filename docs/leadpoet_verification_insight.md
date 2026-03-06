# LeadPoet Lead Verification: Validator vs Miner Pipeline Comparison

## Overview

The LeadPoet system has **two distinct validation layers**:
1. **Miner-side** — Pre-submission checks the miner performs before sending leads to the gateway
2. **Validator-side** — Post-submission verification that validators run to score/approve/reject leads

The **gateway** sits between them as a security boundary enforcing structural validation that miners cannot bypass.

---

## Architecture Flow

```
MINER PIPELINE                    GATEWAY                         VALIDATOR PIPELINE
─────────────────────────────────────────────────────────────────────────────────────
1. Serper Search → Domain Discovery
2. LLM Domain Scoring (Qwen3-80B)
3. Crawl4AI Website Crawling
4. LLM Data Extraction (Qwen3-14B)
5. SMTP Email Verification
6. Data Normalization
7. Source Provenance Check
          │
          ▼
     POST /presign ──────────► Rate Limit Check
     PUT  s3_url   ──────────► Hash Verification
     POST /submit/ ──────────► 14+ Structural Checks
                                      │
                                      ▼
                              Lead stored in DB
                                      │
                                      ▼
                               VALIDATOR FETCHES LEADS
                               ─────────────────────
                               Stage 0: Hardcoded Checks
                               Stage 1: DNS Layer (MX/SPF/DMARC)
                               Stage 2: Domain Reputation (DNSBL/WHOIS)
                               Stage 3: Email Verification (TrueList API)
                               Stage 4: Person & LinkedIn (ScrapingDog + LLM)
                               Stage 5: Company Verification (ScrapingDog + LLM)
                               Rep Score: Wayback + SEC + GDELT + Companies House
                                      │
                                      ▼
                               Consensus (3+ validators agree)
                                      │
                                      ▼
                               APPROVE / REJECT → Weight scoring
```

---

## Side-by-Side Comparison

### Email Verification

| Check | Miner | Validator |
|-------|-------|-----------|
| MX Record | ✅ dns.resolver | ✅ dns.resolver |
| SMTP RCPT (port 25) | ✅ Direct SMTP | ❌ Not used |
| TrueList Batch API | ❌ Not used | ✅ `TRUELIST_API_KEY` |
| SPF/DMARC | ❌ Not checked | ✅ Collected (soft check) |
| Disposable domain | ❌ Not checked | ✅ Blocklist |
| Free email domain | ❌ Not checked | ✅ Blocklist (gmail, yahoo, etc.) |
| Role-based email | ❌ Not checked | ✅ Rejects info@, support@, etc. |
| Name-in-email match | ❌ Not checked | ✅ Fuzzy matching |

**Gap**: Miner uses free SMTP verification which only proves the mailbox exists. Validator uses TrueList (paid API) which also checks deliverability, disposable status, and role-based classification. **Miner should avoid submitting info@, support@, hello@ emails** — they will be rejected by the validator.

### LinkedIn Verification

| Check | Miner | Validator |
|-------|-------|-----------|
| Person LinkedIn URL | ⚠️ Fallback: constructs from name | ✅ ScrapingDog GSE search verifies URL exists |
| Company LinkedIn URL | ⚠️ Fallback: constructs from domain | ✅ ScrapingDog GSE verifies + extracts data |
| Name match on LinkedIn | ❌ Not checked | ✅ Extracts and matches against claimed name |
| Company match on LinkedIn | ❌ Not checked | ✅ Extracts and matches against claimed company |
| Location from LinkedIn | ❌ Not checked | ✅ Multi-query cascade (Q1→Q2→Q3) |
| Role from LinkedIn | ❌ Not checked | ✅ Rule-based + LLM fallback |

**Gap**: This is the **biggest gap**. The miner constructs LinkedIn URLs from names (e.g., `linkedin.com/in/jonathan-lowenhar`) which may not exist. The validator uses ScrapingDog to verify the URL is real and that the name/company/location match. **Leads with fabricated LinkedIn URLs will be rejected.**

### Company Verification

| Check | Miner | Validator |
|-------|-------|-----------|
| Company name | ✅ LLM extraction from website | ✅ LinkedIn profile verification |
| Employee count | ⚠️ LLM extraction (often missing) | ✅ LinkedIn exact range match |
| Industry/Sub-industry | ⚠️ LLM extraction + taxonomy mapping | ✅ Embedding similarity + LLM top-3 ranking |
| HQ Location | ⚠️ LLM extraction (often wrong) | ✅ LinkedIn + multi-query verification |
| Website verification | ✅ Crawled directly | ✅ LinkedIn website field match |
| Description | ⚠️ LLM extraction | ✅ LLM validation against website content |
| Company LinkedIn slug | ❌ Not verified | ✅ Cache lookup + full verification cascade |

**Gap**: Miner relies entirely on LLM extraction from website content, which is often incomplete or incorrect. Validator cross-references everything against LinkedIn company profiles.

### Domain & Reputation

| Check | Miner | Validator |
|-------|-------|-----------|
| Domain age (WHOIS) | ✅ ≥7 days | ✅ ≥7 days + registrar data |
| DNSBL blacklist | ❌ Not checked | ✅ DNS reputation lookup |
| Wayback Machine | ❌ Not checked | ✅ Historical website verification |
| SEC Edgar | ❌ Not checked | ✅ Public company filing verification |
| GDELT mentions | ❌ Not checked | ✅ Global news/event mentions |
| Companies House (UK) | ❌ Not checked | ✅ UK company registration |
| Source provenance denylist | ✅ Blocks ZoomInfo, Apollo, etc. | ❌ Gateway-level (not validator) |
| URL reachability | ✅ HTTP HEAD check | ❌ (already verified at gateway) |

### Role Verification

| Check | Miner | Validator |
|-------|-------|-----------|
| Role format | ❌ Not checked | ✅ 48 checks at gateway |
| Role exists on LinkedIn | ❌ Not checked | ✅ ScrapingDog + extraction |
| Role matches claimed | ❌ Not checked | ✅ Rule-based + LLM fallback |
| Spam/placeholder detection | ❌ Not checked | ✅ Gateway: typos, taglines, padding |

---

## External API Keys Required

### Miner APIs (Currently Used)

| API | Env Var | Purpose | Cost |
|-----|---------|---------|------|
| Serper.dev | `SERPER_API_KEY` | Google search for domain discovery | ~$0.01/search |
| NVIDIA NIM / OpenRouter | `OPENROUTER_KEY` | LLM scoring + extraction | ~$0.001-0.01/call |
| Firecrawl | `FIRECRAWL_KEY` | Website scraping (backup) | ~$0.01-0.10/page |
| SMTP (port 25) | None | Email verification | Free |

### Validator APIs (NOT used by miner)

| API | Env Var | Purpose | Cost | Impact |
|-----|---------|---------|------|--------|
| **TrueList** | `TRUELIST_API_KEY` | Email verification (batch) | ~$0.01/email | HIGH - catches invalid/disposable emails |
| **ScrapingDog** | `SCRAPINGDOG_API_KEY` | Google search for LinkedIn verification | ~$0.02/search | CRITICAL - verifies person + company on LinkedIn |
| **Companies House** | `COMPANIES_HOUSE_API_KEY` | UK company registration check | Free | LOW - reputation score component |
| **OpenRouter LLM** | `OPENROUTER_KEY` | Role validation + industry classification | ~$0.01/call | MEDIUM - industry taxonomy matching |

---

## Validator Scoring Formula

### Stage Pass/Fail (Hard Requirements)

| Stage | Pass Criteria | Fail = Auto-Reject |
|-------|--------------|---------------------|
| Stage 0 | All required fields present, valid email format | Yes |
| Stage 1 | MX record exists | Yes |
| Stage 3 | TrueList: email is "valid" | Yes (invalid/disposable/role-based) |
| Stage 4 | LinkedIn URL found + name + company + location match | Yes |
| Stage 5 | Company name + employee count + HQ + industry verified | Yes |

### Reputation Score (Soft, 0-48 pts)

| Component | Max Points | Source |
|-----------|-----------|--------|
| Wayback Machine | 6 | Internet Archive API |
| SEC Edgar | 12 | SEC EDGAR API |
| WHOIS/DNSBL | 10 | Domain reputation |
| GDELT | 10 | Global news mentions |
| Companies House | 10 | UK company registry |

### Consensus
- **3+ validators** must agree on approve/reject
- Each validator scores leads 0.0-0.5
- Scores aggregated across validators for final weight

---

## Critical Gaps: What Miners Should Fix

### 1. **Generic/Role-Based Emails** (HIGH PRIORITY)
**Current**: Miner accepts `info@`, `contact@`, `hello@` emails
**Validator**: Auto-rejects these at Stage 0
**Fix**: Add blocklist check before submission

### 2. **LinkedIn URL Validity** (CRITICAL)
**Current**: Miner constructs fake URLs like `linkedin.com/in/firstname-lastname`
**Validator**: Verifies URL actually exists via Google search
**Fix**: Either scrape LinkedIn to verify, or only submit leads where LinkedIn was found on the website

### 3. **Employee Count Accuracy** (MEDIUM)
**Current**: Miner defaults to "2-10" when unknown
**Validator**: Checks exact range against LinkedIn company profile
**Fix**: Try to extract from LinkedIn company page or estimate from website signals

### 4. **Industry Classification** (MEDIUM)
**Current**: Miner maps LLM-extracted text to closest taxonomy entry
**Validator**: Uses embedding similarity + LLM ranking against 725-entry taxonomy
**Fix**: Use the same embedding approach or at least validate against top-3 most likely

### 5. **Location Accuracy** (MEDIUM)
**Current**: Miner defaults non-US to "San Francisco, California, United States"
**Validator**: Cross-references against LinkedIn HQ location
**Fix**: Only submit leads where location was found on website or LinkedIn

### 6. **Description Quality** (LOW-MEDIUM)
**Current**: Miner pads short descriptions with generic text
**Validator**: LLM validates description matches actual website content
**Fix**: Generate quality descriptions from crawled website content

---

## Recommendations for Improving Acceptance Rate

### Quick Wins (No new API keys needed)
1. **Filter out generic emails** — reject info@, support@, hello@, sales@, contact@, etc.
2. **Only submit leads with real LinkedIn URLs** found on the website (not constructed)
3. **Only submit leads with location data** found on the website (not defaults)
4. **Generate better descriptions** from website content (not padding)

### Medium-Term (Requires ScrapingDog API key)
5. **Pre-verify LinkedIn URLs** using ScrapingDog before submission
6. **Extract employee count** from LinkedIn company profile
7. **Verify person-company match** before submission

### Long-Term (Requires TrueList API key)
8. **Pre-verify emails** via TrueList before submission (matches validator exactly)
9. **Build company cache** similar to validator's cache (skip re-verification)

---

## File References

### Miner Pipeline
- `miner_models/lead_sorcerer_main/main_leads.py` — Pipeline wrapper + legacy conversion
- `miner_models/lead_sorcerer_main/src/orchestrator.py` — Pipeline orchestrator
- `miner_models/lead_sorcerer_main/src/domain.py` — Domain discovery + LLM scoring
- `miner_models/lead_sorcerer_main/src/crawl.py` — Website crawling + LLM extraction
- `neurons/miner.py` — Miner neuron (submission loop, provenance)
- `Leadpoet/utils/source_provenance.py` — Denylist + URL validation
- `Leadpoet/utils/cloud_db.py` — Gateway API client

### Validator Pipeline
- `validator_models/automated_checks.py` — Stage 0 hardcoded checks
- `validator_models/checks_email.py` — Stages 1-3 (DNS + TrueList email)
- `validator_models/stage4_person_verification.py` — Stage 4 (LinkedIn person)
- `validator_models/stage5_verification.py` — Stage 5 (Company verification)
- `validator_models/checks_repscore.py` — Reputation score (Wayback/SEC/GDELT)
- `validator_models/checks_icp.py` — ICP fit checks
- `validator_models/industry_taxonomy.py` — Sub-industry taxonomy (725 entries)
- `neurons/validator.py` — Validator neuron

### Gateway Validation
- `gateway/api/submit.py` — Gateway-side structural validation
- `gateway/utils/rate_limiter.py` — Rate limiting
- `gateway/utils/industry_taxonomy.py` — Industry taxonomy (723 entries)
- `gateway/utils/geo_normalize.py` — Location normalization

---

*Generated: 2026-03-01*
