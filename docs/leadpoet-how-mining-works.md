# How Leadpoet (SN71) Mining Actually Works

**Date:** 2026-02-28
**Codebase:** `/home/ubuntu/leadpoet`

---

## TL;DR

Leadpoet mining does **NOT** use Bittensor's standard axon/dendrite protocol for lead submission. Instead, miners push leads to a **centralized Leadpoet gateway server** (`52.91.135.79:8000`) via HTTP. The gateway stores leads in S3/MinIO, validators pull them from there to validate, and then set weights on-chain. Your miner is a **client**, not a server.

---

## 1. Architecture Overview

```
                         Bittensor Chain (finney)
                              │
                    ┌─────────┴─────────┐
                    │                   │
               set weights         read metagraph
                    │                   │
              ┌─────┴─────┐       ┌─────┴─────┐
              │ Validators │       │   Miner   │
              │  (7 total) │       │  (you)    │
              └─────┬─────┘       └─────┬─────┘
                    │                   │
              pull leads          push leads
              from gateway        to gateway
                    │                   │
                    └────────┬──────────┘
                             │
                    ┌────────┴────────┐
                    │  Leadpoet       │
                    │  Gateway        │
                    │  52.91.135.79   │
                    │  :8000          │
                    └────────┬────────┘
                             │
                    ┌────────┴────────┐
                    │  AWS S3 / MinIO │
                    │  (lead storage) │
                    └─────────────────┘
```

**Key insight:** All 121 miners have NO IP/port on the metagraph. Miners don't serve anything — they only make outbound HTTP calls.

---

## 2. What the Miner Does Every 60 Seconds

The miner runs a continuous **sourcing loop** (`neurons/miner.py` line 178). Every 60 seconds:

### Step 1: Generate Leads
- Runs the Lead Sorcerer pipeline (`miner_models/lead_sorcerer_main/`)
- Uses Serper.dev to search for companies matching the ICP (Ideal Customer Profile)
- Uses Firecrawl to scrape company websites for contact info
- Produces structured lead records with 15+ fields

### Step 2: Validate Source Provenance
- Checks source URL is not from a denied provider (ZoomInfo, Apollo, RocketReach, Hunter, etc.)
- Verifies domain age >= 7 days
- Confirms URL is reachable (HTTP 200/301/302)

### Step 3: Sanitize & Add Attestation
- Strips HTML, validates URLs, normalizes fields
- Appends regulatory attestation (wallet address, terms acceptance hash, timestamps)
- Adds `lawful_collection=true`, `no_restricted_sources=true`, `license_granted=true`

### Step 4: Check Duplicates (Pre-flight)
- Queries Supabase `transparency_log` table (public, read-only, uses hardcoded ANON key)
- Checks if email already exists (approved or processing = skip, rejected = allow retry)
- Checks if linkedin + company_linkedin combo already exists
- This saves rate limit quota by avoiding known duplicates before hitting the gateway

### Step 5: Get Presigned S3 URL
- `POST http://52.91.135.79:8000/presign`
- Sends: lead_id, lead_blob_hash (SHA256 of lead JSON), email_hash
- Authenticated with Ed25519 wallet signature
- Gateway logs `SUBMISSION_REQUEST` event, returns presigned S3 upload URL

### Step 6: Upload Lead to S3
- `PUT <presigned_s3_url>`
- Uploads lead JSON (serialized with `sort_keys=True` to match hash)
- Gateway automatically mirrors to MinIO

### Step 7: Trigger Verification
- `POST http://52.91.135.79:8000/submit/`
- Gateway fetches the uploaded blob from S3
- Recomputes SHA256, verifies it matches the committed hash
- Stores lead in `leads_private` table
- Logs `STORAGE_PROOF` and `SUBMISSION` events
- Returns rate limit stats (submissions used, rejections count)

### Step 8: Wait 60 Seconds, Repeat

---

## 3. What Validators Do With Your Leads

After you submit:

1. **Validators pull leads** from gateway via `GET /epoch/{epoch_id}/leads`
2. **3 independent validators** each run a multi-stage validation pipeline:

   | Stage | Check | Tool |
   |-------|-------|------|
   | 1 | Email verification | Truelist API |
   | 2 | Domain validation | WHOIS, age >= 7 days, blacklist check |
   | 3 | Website accessibility | HTTP check |
   | 4 | LinkedIn verification | ScrapingDog API |
   | 5 | Unified deep verification | LLM + multiple data sources |

3. **Reputation scoring** (0-48 points) across 5 dimensions:

   | Check | Source | Max Points |
   |-------|--------|------------|
   | Wayback Machine (web archive) | web.archive.org | 6 |
   | SEC EDGAR (regulatory filings) | sec.gov | 12 |
   | WHOIS/DNSBL (domain reputation) | WHOIS + blacklists | 10 |
   | GDELT (press/media coverage) | gdeltproject.org | 10 |
   | Companies House (UK registry) | companieshouse.gov.uk | 10 |

4. **Consensus** — lead approved only when 3 validators agree
5. **Weights set on-chain** based on your leads' reputation scores

---

## 4. How You Get Paid (Reward Formula)

### Weight Calculation

For each approved lead:
- **40% sourcing reward** → goes to the miner who submitted the lead
- **60% curating reward** → goes to the miner who ranked the lead for a buyer

Your combined weight: `W = sourcing_score + curating_score`

Your emission: `~200 Alpha × (W_you / W_total)` per epoch (72 minutes)

### Rolling History
- Rewards use a **30-epoch rolling window** (~36 hours)
- Consistent quality over time beats burst submissions
- New miners need time to build up reward weight

---

## 5. The Lead JSON You Submit

Every lead submission must contain these fields:

```json
{
  "business": "Acme Corp",
  "full_name": "John Doe",
  "first": "John",
  "last": "Doe",
  "email": "john@acme.com",
  "linkedin": "https://www.linkedin.com/in/johndoe",
  "website": "https://acme.com",
  "industry": "Technology",
  "sub_industry": "SaaS",
  "role": "CEO",
  "country": "US",
  "state": "California",
  "city": "San Francisco",
  "description": "SaaS platform for...",
  "company_linkedin": "https://www.linkedin.com/company/acme",
  "employee_count": "50-200",
  "source_url": "https://acme.com/about",
  "source_type": "company_site",

  "source": "<your_hotkey_ss58>",
  "wallet_ss58": "<your_hotkey_ss58>",
  "submission_timestamp": "2026-02-28T12:00:00+00:00",
  "terms_version_hash": "<SHA256>",
  "lawful_collection": true,
  "no_restricted_sources": true,
  "license_granted": true
}
```

### Quality Rules
- Email must be valid (Truelist returns "Valid") — no catch-all, disposable, or generic
- Contact's first or last name must appear in the email address
- Source URL cannot be LinkedIn
- US leads require country + state + city; non-US require country + city
- Industry must match `industry_taxonomy.py` exactly

---

## 6. Gateway Authentication

All gateway calls use **Ed25519 wallet signatures** (no JWTs, no API keys):

```
Message format:
{event_type}:{actor_hotkey}:{nonce}:{ts}:{payload_hash}:{build_id}

Example:
SUBMISSION_REQUEST:5GHSH1EQAw...:550e8400-...:2026-02-28T12:00:00Z:a1b2c3d4...:miner-client
```

- `nonce` = UUID v4 (prevents replay attacks)
- `ts` = ISO 8601 timestamp (checked for freshness)
- `payload_hash` = SHA256 of JSON payload
- Signed with `wallet.hotkey.sign(message.encode())`

The gateway verifies the signature using your public key (from on-chain registration).

---

## 7. Rate Limits

### Gateway-Enforced (authoritative)

| Limit | Value | Reset |
|-------|-------|-------|
| Max submissions/day | 1,000 | Midnight UTC |
| Max rejections/day | 250 | Midnight UTC |
| Min time between submissions | 20 seconds | Per-submission |

Exceeding the rejection limit **blocks ALL submissions** until midnight UTC.

### Miner-Side (pre-flight)
- Duplicate email check (queries public Supabase table)
- Duplicate linkedin combo check (same table)
- These save your rate limit quota by avoiding known duplicates

---

## 8. Validator Requests (Axon/gRPC)

Separately from the sourcing loop, validators can also query your miner directly via Bittensor's axon protocol for **lead curation** (ranking leads for a specific buyer ICP):

1. Validator sends `LeadRequest` synapse with `business_desc`, `num_leads`, `industry`, `region`
2. Your miner **pauses the sourcing loop**
3. Runs LLM classification: `classify_industry()` + `classify_roles()` (OpenRouter)
4. Pulls leads from pool (cloud or local)
5. Ranks them with `rank_leads()` using LLM (OpenRouter `o3-mini:online`)
6. Returns top N leads via synapse response
7. **Resumes sourcing loop**

This is why the miner still publishes an axon on-chain (port 8091 by default) — even though lead **submission** goes through the gateway, lead **curation** requests come through the axon.

**However:** Looking at the metagraph, most miners have NO IP/port set, suggesting this curation path may not be actively used by validators, or miners can skip it without penalty.

---

## 9. Qualification Models (Advanced, Optional)

A separate pathway where you submit a custom Python model to compete for **5% of subnet emissions**:

1. Create a `qualify.py` with a `qualify(lead, icp)` function
2. Package as tarball
3. Upload to S3 via gateway presigned URL
4. **Pay $5 worth of TAO** to Leadpoet coldkey (`5ExoWGyajvzucCqS5GxZSpuzzXEzG1oNFcDqdW3sXeTujoD7`)
5. Submit to gateway with payment proof
6. Model is evaluated against 100 ICPs
7. Must beat current champion by >5% to take over

Rate limit: 2 model submissions per day.

---

## 10. Network Connections Required

Your miner needs **outbound** access to:

| Destination | Port | Purpose |
|-------------|------|---------|
| `52.91.135.79` | 8000 | Leadpoet gateway (presign, upload, verify) |
| `54.226.209.164` | 8000 | Gateway (alternate IP in cloud_db.py) |
| `qplwoislplkcegvdmbim.supabase.co` | 443 | Duplicate checks (transparency_log) |
| `google.serper.dev` | 443 | Search API (domain discovery) |
| `api.firecrawl.dev` | 443 | Web scraping |
| `openrouter.ai` | 443 | LLM calls |
| Bittensor finney RPC | various | Chain queries, weight reading |
| AWS S3 | 443 | Lead upload (presigned URLs) |

Your miner does **NOT** need any inbound ports open for lead submission. The axon port (8091) is only needed if validators send curation requests, which appears optional based on current metagraph data.

---

## 11. Two Gateway IPs in the Code

There's a discrepancy in the codebase:

| File | Default Gateway IP |
|------|--------------------|
| `neurons/miner.py` (line 1032) | `http://52.91.135.79:8000` |
| `neurons/validator.py` | `http://52.91.135.79:8000` |
| `Leadpoet/utils/cloud_db.py` (line 20) | `http://54.226.209.164:8000` |

Both are overridden by the `GATEWAY_URL` environment variable. If not set, the sourcing loop uses cloud_db.py's default (`54.226.209.164`), while qualification model submission uses miner.py's default (`52.91.135.79`). These may be the same server behind different IPs, or a primary/backup pair.

---

## 12. Denied Data Sources

The miner auto-rejects leads sourced from these providers:

- ZoomInfo
- Apollo.io
- PeopleDataLabs
- RocketReach
- Hunter.io
- Snov.io
- Lusha
- Clearbit
- LeadIQ

If a lead's `source_url` domain matches any of these, it is rejected before submission.

---

## Summary: Your Miner's Lifecycle

```
[Startup]
  → Accept contributor terms (first run only)
  → Register wallet on-chain
  → Publish axon endpoint (port 8091)
  → Start background metagraph sync

[Every 60 seconds — Sourcing Loop]
  → Search for companies (Serper.dev)
  → Scrape company websites (Firecrawl)
  → Build structured lead JSON (15+ fields)
  → Validate source provenance (denylist, domain age, reachability)
  → Add regulatory attestation
  → Check duplicates (Supabase public table)
  → Sign & get presigned S3 URL (gateway /presign)
  → Upload lead to S3
  → Trigger verification (gateway /submit/)
  → Log results
  → Sleep 60 seconds

[On-Demand — Validator Curation Request via Axon]
  → Pause sourcing loop
  → Classify industry + roles (OpenRouter LLM)
  → Pull leads from pool
  → Rank leads against buyer ICP (OpenRouter LLM)
  → Return top leads
  → Resume sourcing loop

[Every 72 minutes — Epoch]
  → Validators calculate weights from lead quality + reputation scores
  → Weights set on-chain
  → Your emission = your weight share × ~200 Alpha/epoch
```
