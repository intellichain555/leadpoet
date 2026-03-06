# Leadpoet Miner Architecture: Comprehensive Analysis

## Table of Contents
1. [Miner Startup Flow](#1-miner-startup-flow)
2. [Sourcing Loop](#2-sourcing-loop)
3. [Gateway Interactions](#3-gateway-interactions)
4. [Lead Data Flow](#4-lead-data-flow)
5. [Qualification Model Flow](#5-qualification-model-flow)
6. [Validator Request Handling](#6-validator-request-handling)
7. [HTTP Server](#7-http-server)
8. [Authentication](#8-authentication)
9. [Rate Limits](#9-rate-limits)
10. [Cloud DB Module](#10-cloud-db-module)
11. [Scoring and Rewards](#11-scoring-and-rewards)

---

## 1. Miner Startup Flow

### Entry Point
**File:** `/home/ubuntu/leadpoet/neurons/miner.py`, function `main()` (line 2013)

### Sequence of Operations

**Step 1: Parse CLI arguments** (line 2014-2047)
```
BaseMinerNeuron.add_args(parser) is called, which defines:
  --netuid (default 71)
  --subtensor_network (default "finney")
  --wallet_name (required)
  --wallet_hotkey (required)
  --wallet_path (default "~/.bittensor/wallets")
  --use_open_source_lead_model (flag)
  --blacklist_force_validator_permit (flag)
  --blacklist_allow_non_registered (flag)
  --neuron_epoch_length (default 1000)
  --logging_trace (flag)
  --axon_ip (optional, public IP for validators)
  --axon_port (optional, public port)
```

**Step 2: Ensure data files** (line 2049)
- Creates `data/` directory, `data/sourcing_logs.json`, `data/miners.json`, `data/leads.json`

**Step 3: Contributor Terms Acceptance** (lines 2051-2138)
- Terms are fetched from GitHub: `https://cdn.jsdelivr.net/gh/leadpoet/leadpoet@main/docs/contributor_terms.md`
- SHA-256 hash of terms text becomes `TERMS_VERSION_HASH`
- First run: displays full terms, requires "Y" input
- Subsequent runs: verifies stored hash matches current hash; if updated, re-prompts
- Attestation stored locally at `data/regulatory/miner_attestation.json`
- Contains: `wallet_ss58`, `timestamp_utc`, `terms_version_hash`, `accepted`, `ip_address`
- **File:** `/home/ubuntu/leadpoet/Leadpoet/utils/contributor_terms.py`

**Step 4: Optional Qualification Model Submission** (lines 2140-2184)
- Interactive prompt: "Submit a qualification model? (Y/N)"
- If Y, runs `run_qualification_submission_flow()` (see Section 5)
- If N, proceeds to normal mining

**Step 5: Create Miner instance** (line 2191)
```python
miner = Miner(config=config)
```

This triggers the full initialization chain:

### Class Hierarchy
```
Miner (neurons/miner.py:58)
  -> BaseMinerNeuron (Leadpoet/base/miner.py:9)
    -> BaseNeuron (Leadpoet/base/neuron.py:5)
```

### BaseNeuron.__init__ (Leadpoet/base/neuron.py:10)
1. Creates `bt.wallet(config=self.config)`
2. Temporarily unsets HTTP proxy env vars (lines 23-29)
3. Creates `bt.subtensor(config=self.config)` -- websocket connection to chain
4. Restores proxy env vars
5. Creates `bt.metagraph(netuid=config.netuid, subtensor=self.subtensor)`
6. Sets `self.step = 0`, `self.block = subtensor.get_current_block()`

### BaseMinerNeuron.__init__ (Leadpoet/base/miner.py:27)
1. Calls `self.config_neuron("./miner_state")` -- sets neuron config defaults
2. Calls `self.config_axon(8091)` -- default axon port 8091
3. Applies `--axon_ip` / `--axon_port` overrides
4. Initializes blacklist/priority config defaults
5. **Registers wallet on network** (lines 53-74): Calls `subtensor.get_uid_for_hotkey_on_subnet()` up to 3 retries
6. Auto-adopts on-chain axon address if no external IP/port specified (lines 83-97)
7. Sets `GRPC_VERBOSITY=ERROR`
8. **Builds the axon** (lines 104-110):
   ```python
   self.axon = bt.axon(wallet=self.wallet, ip="0.0.0.0", port=config.axon.port, ...)
   ```
9. **Attaches forward function** (lines 112-116):
   ```python
   self.axon.attach(forward_fn=self.forward, blacklist_fn=self.blacklist, priority_fn=self.priority)
   ```

### Miner.__init__ (neurons/miner.py:60)
1. Sets `self.use_open_source_lead_model` from config
2. Creates `aiohttp.web.Application` with route `POST /lead_request`
3. Sets `self.sourcing_mode = True`
4. Creates `self.sourcing_lock = threading.Lock()`
5. Initializes `_loop`, `sourcing_task`, `cloud_task`, `_bg_interval=60`, `_miner_hotkey=None`

**Step 6: Start miner in background thread** (lines 2206-2229)
```python
miner_thread = threading.Thread(target=run_miner_safe, daemon=True)
```
This calls `miner.run()` which is `BaseMinerNeuron.run()` (Leadpoet/base/miner.py:122):
1. `self.sync()` -- syncs metagraph
2. `self.axon.serve(netuid=..., subtensor=...)` -- publishes axon endpoint on-chain
3. `self.axon.start()` -- starts gRPC server
4. Enters main loop: every 5 seconds checks `last_update`, resyncs metagraph at epoch boundaries

**Step 7: Start sourcing loop in main thread** (lines 2232-2239)
```python
asyncio.run(run_sourcing())
```
Which calls `run_miner()` (line 1961):
1. Sets `miner._loop = asyncio.get_running_loop()`
2. Creates `asyncio.create_task(miner.sourcing_loop(interval=60, miner_hotkey))`
3. Note: cloud_curation and broadcast loops are **disabled** (commented out, lines 1972-1977)
4. Keeps alive with `while True: await asyncio.sleep(1)`

---

## 2. Sourcing Loop

**File:** `/home/ubuntu/leadpoet/neurons/miner.py`, method `sourcing_loop()` (line 178)

### Loop Flow (every 60 seconds)

```
while True:
  1. Check self.sourcing_mode (can be paused by validator requests)
  2. Acquire self.sourcing_lock
  3. Generate leads via get_leads(1, industry=None, region=None)
  4. Validate source provenance -> process_generated_leads()
  5. Sanitize leads -> sanitize_prospect()
  6. For each sanitized lead:
     a. check_email_duplicate(email)  -- queries transparency_log via Supabase ANON key
     b. check_linkedin_combo_duplicate(linkedin, company_linkedin) -- same
     c. gateway_get_presigned_url(wallet, lead) -> POST {GATEWAY_URL}/presign
     d. gateway_upload_lead(presigned_url, lead) -> PUT to S3 presigned URL
     e. gateway_verify_submission(wallet, lead_id) -> POST {GATEWAY_URL}/submit/
  7. await asyncio.sleep(60)
```

### Step 3: Lead Generation
**File:** `/home/ubuntu/leadpoet/miner_models/lead_sorcerer_main/main_leads.py`

`get_leads()` (line 410) calls the "Lead Sorcerer" pipeline:
- Requires env vars: `SERPER_API_KEY`, `OPENROUTER_KEY`, `FIRECRAWL_KEY`
- Uses `LeadSorcererOrchestrator` from `orchestrator.py` in the `src/` subdirectory
- Loads ICP config from `icp_config.json`
- Runs pipeline in temp directory, reads `leads.jsonl` output
- Converts each record via `convert_lead_record_to_legacy_format()` which maps:
  - `company.name` -> `business`
  - `contacts[0].email` -> `email`
  - `contacts[0].full_name` -> `full_name`
  - `contacts[0].role` -> `role`
  - `contacts[0].linkedin` -> `linkedin` (normalized to full URL)
  - `company.industry` -> `industry`
  - etc.

### Step 4: Source Provenance Validation
**File:** `/home/ubuntu/leadpoet/Leadpoet/utils/source_provenance.py`

`process_generated_leads()` (line 106 in miner.py) calls:
1. `determine_source_type(url, lead)` -- categorizes as: `licensed_resale`, `proprietary_database`, `first_party_form`, `public_registry`, `company_site`
2. `validate_source_url(url, source_type)` -- 3 checks:
   - Domain NOT in denylist (ZoomInfo, Apollo, PeopleDataLabs, RocketReach, Hunter, Snov, Lusha, Clearbit, LeadIQ)
   - Domain age >= 7 days (via `check_domain_age`)
   - URL reachable (HTTP HEAD/GET, status 200/301/302/303/307/308)
3. Enriches lead with `source_url` and `source_type` fields

### Step 5: Sanitization
**Function:** `sanitize_prospect()` (line 1794 in miner.py)

Maps raw lead fields to standardized names, strips HTML, validates URLs, and appends:
- Regulatory attestation: `wallet_ss58`, `submission_timestamp`, `terms_version_hash`
- Boolean attestations: `lawful_collection=True`, `no_restricted_sources=True`, `license_granted=True`
- Source provenance: `source_url`, `source_type`, `license_doc_hash`, `license_doc_url`

---

## 3. Gateway Interactions

### Gateway URL
**Default:** `http://52.91.135.79:8000` (set via `GATEWAY_URL` env var)
**In cloud_db.py:** `GATEWAY_URL = os.getenv("GATEWAY_URL", "http://54.226.209.164:8000")` (line 20)
**In miner.py qualification:** `QUALIFICATION_GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://52.91.135.79:8000")` (line 1032)

Note: There are TWO default IPs in the code -- `54.226.209.164` in cloud_db.py and `52.91.135.79` in miner.py/validator.py. The GATEWAY_URL env var overrides both.

### Endpoint 1: POST /presign
**Function:** `gateway_get_presigned_url()` (cloud_db.py line 1905)
**Purpose:** Get presigned S3 URL for lead upload; logs SUBMISSION_REQUEST with committed hash

**Request body (SubmissionRequestEvent):**
```json
{
  "event_type": "SUBMISSION_REQUEST",
  "actor_hotkey": "<miner SS58 address>",
  "nonce": "<UUID v4>",
  "ts": "<ISO 8601 UTC timestamp>",
  "payload_hash": "<SHA256 of payload JSON>",
  "build_id": "<BUILD_ID env var or 'miner-client'>",
  "signature": "<hex-encoded Ed25519 signature>",
  "payload": {
    "lead_id": "<UUID v4>",
    "lead_blob_hash": "<SHA256 of lead JSON>",
    "email_hash": "<SHA256 of normalized email>"
  }
}
```

**Signature message format:**
```
SUBMISSION_REQUEST:{actor_hotkey}:{nonce}:{ts}:{payload_hash}:{build_id}
```

**Response:**
```json
{
  "lead_id": "...",
  "s3_url": "https://s3.amazonaws.com/...",
  "storage_backends": ["s3", "minio"],
  ...
}
```

**Retry:** Up to 3 attempts with fresh nonce/timestamp each time.

### Endpoint 2: PUT to S3 presigned URL
**Function:** `gateway_upload_lead()` (cloud_db.py line 2024)
**Purpose:** Upload lead JSON blob to S3 storage

**Request:**
```
PUT <presigned_url>
Content-Type: application/json
Body: JSON.dumps(lead_data, sort_keys=True)   # MUST use sort_keys to match hash
```

### Endpoint 3: POST /submit/
**Function:** `gateway_verify_submission()` (cloud_db.py line 2058)
**Purpose:** Trigger gateway to verify uploaded lead, check hashes, store in DB

**Request body (SUBMIT_LEAD event):**
```json
{
  "event_type": "SUBMIT_LEAD",
  "actor_hotkey": "<miner SS58 address>",
  "nonce": "<UUID v4>",
  "ts": "<ISO 8601 UTC timestamp>",
  "payload_hash": "<SHA256 of payload JSON>",
  "build_id": "<BUILD_ID or 'miner-client'>",
  "signature": "<hex-encoded Ed25519 signature>",
  "payload": {
    "lead_id": "<UUID from presign step>"
  }
}
```

**Signature message format:**
```
SUBMIT_LEAD:{actor_hotkey}:{nonce}:{ts}:{payload_hash}:{build_id}
```

**Response (success):**
```json
{
  "lead_id": "...",
  "status": "verified",
  "storage_backends": ["s3", "minio"],
  "submission_timestamp": "...",
  "merkle_proof": "...",
  "rate_limit_stats": {
    "submissions": 5,
    "max_submissions": 1000,
    "rejections": 0,
    "max_rejections": 250
  }
}
```

**Gateway server-side steps (per BRD Section 4.1):**
1. Fetch uploaded blob from S3/MinIO
2. Recompute SHA256, verify matches committed `lead_blob_hash`
3. Log `STORAGE_PROOF` event per mirror
4. Store lead in `leads_private` table
5. Log `SUBMISSION` event

### Endpoint 4: POST /qualification/model/presign
**Function:** `get_presigned_upload_url()` (miner.py line 1261)
**Purpose:** Get presigned URL for qualification model tarball upload

**Request:**
```json
{
  "miner_hotkey": "<SS58>",
  "timestamp": 1234567890,
  "signature": "<hex signature>"
}
```

**Signature message:** `JSON.dumps({"miner_hotkey": ..., "timestamp": ...}, sort_keys=True)`

**Response:**
```json
{
  "upload_url": "https://s3...",
  "s3_key": "qualification-models/...",
  "expires_in_seconds": 3600,
  "daily_submissions_used": 0,
  "daily_submissions_max": 2,
  "submission_credits": 0
}
```

### Endpoint 5: POST /qualification/model/submit
**Function:** `submit_qualification_model()` (miner.py line 1391)
**Purpose:** Finalize qualification model submission after S3 upload and TAO payment

**Request:**
```json
{
  "miner_hotkey": "<SS58>",
  "s3_key": "...",
  "code_hash": "<SHA256 of tarball>",
  "payment_block_hash": "0x...",
  "payment_extrinsic_index": 3,
  "timestamp": 1234567890,
  "model_name": "my-model",
  "signature": "<hex signature>"
}
```

### Endpoint 6: GET /qualification/model/rate-limit/{hotkey}
**Function:** Credit check in `run_qualification_submission_flow()` (miner.py line 1607)
**Purpose:** Check submission credits and daily rate limits for qualification models

**Response:**
```json
{
  "submission_credits": 1,
  "daily_submissions_used": 0,
  "daily_submissions_max": 2
}
```

### Endpoint 7: GET /epoch/{epoch_id}/leads
**Function:** `gateway_get_epoch_leads()` (cloud_db.py line 2208)
**Purpose:** Validators get assigned leads for current epoch

**Auth:** `GET_EPOCH_LEADS:{epoch_id}:{validator_hotkey}` signed message

### Endpoint 8: POST /validate
**Used by validators** to submit validation results

### Endpoint 9: POST /attest
### Endpoint 10: POST /weights
### Endpoint 11: GET /manifest
### Endpoint 12: GET /health

### Legacy API (Cloud Run)
**URL:** `https://leadpoet-api-511161415764.us-central1.run.app`
**Variable:** `API_URL` in cloud_db.py line 21

Used by deprecated/legacy functions:
- `GET /leads` -- get_cloud_leads
- `POST /leads` -- save_leads_to_cloud
- `POST /curate` -- push_curation_request
- `POST /curate/fetch` -- fetch_curation_requests
- `POST /curate/result` -- push_curation_result
- `POST /curate/miner_request` -- push_miner_curation_request
- `POST /curate/miner_request/fetch` -- fetch_miner_curation_request
- `POST /curate/miner_result` -- push_miner_curation_result
- `POST /validator_weights` -- push_validator_weights

---

## 4. Lead Data Flow

### Complete Pipeline

```
[Web/API Scraping]  ->  [Lead Sorcerer Pipeline]
                             |
                     Raw lead record (company, contacts, domain)
                             |
                     convert_lead_record_to_legacy_format()
                             |
                     Legacy lead dict (business, email, full_name, etc.)
                             |
                     process_generated_leads()
                       - validate_source_url()
                       - determine_source_type()
                       - Enrich with source_url, source_type
                             |
                     sanitize_prospect()
                       - Strip HTML, validate URLs
                       - Add regulatory attestation
                       - Add source provenance
                             |
                     Duplicate checks (Supabase transparency_log)
                       - check_email_duplicate() via ANON key
                       - check_linkedin_combo_duplicate() via ANON key
                             |
                     gateway_get_presigned_url()  ->  POST /presign
                       - Sends lead_blob_hash, email_hash
                       - Gets back S3 presigned URL
                             |
                     gateway_upload_lead()  ->  PUT to S3 URL
                       - Uploads JSON blob (sort_keys=True)
                             |
                     gateway_verify_submission()  ->  POST /submit/
                       - Gateway fetches from S3, verifies hash
                       - Stores in leads_private table
                       - Logs STORAGE_PROOF + SUBMISSION events
```

### Exact JSON Fields Submitted (sanitized lead)

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
  "region": "West Coast",
  "description": "SaaS company...",
  "company_linkedin": "https://www.linkedin.com/company/acme",
  "phone_numbers": ["+1-555-0123"],
  "founded_year": "2015",
  "ownership_type": "Private",
  "company_type": "LLC",
  "number_of_locations": "3",
  "employee_count": "50-200",
  "socials": {"twitter": "...", "facebook": "..."},
  "source": "<miner_hotkey_ss58>",

  "wallet_ss58": "<miner_hotkey_ss58>",
  "submission_timestamp": "2026-02-28T12:00:00+00:00",
  "terms_version_hash": "<SHA256 of contributor terms>",
  "lawful_collection": true,
  "no_restricted_sources": true,
  "license_granted": true,
  "source_url": "https://acme.com",
  "source_type": "company_site",
  "license_doc_hash": "",
  "license_doc_url": ""
}
```

---

## 5. Qualification Model Flow

**File:** `/home/ubuntu/leadpoet/neurons/miner.py`, lines 1028-1776

### Overview
This is a SEPARATE pathway from regular lead submission. Miners can submit a "qualification model" -- a custom Python module that scores leads against ICP (Ideal Customer Profile) criteria. The champion model earns 5% of subnet emissions.

### Interactive Flow (`run_qualification_submission_flow`)

1. **Get model directory path** (line 1526): User enters local path containing `qualify.py`
2. **Create tarball** (line 1553): `create_model_tarball()` creates `model_*.tar.gz`, computes SHA256
3. **Get model name** (line 1560): Required user input
4. **Get presigned URL** (line 1569): `POST /qualification/model/presign` -- also checks rate limits (2/day max)
5. **Upload to S3** (line 1590): `upload_to_s3_presigned()` -- PUT to presigned URL with `Content-Type: application/gzip`
6. **Check for existing credits** (line 1604): `GET /qualification/model/rate-limit/{hotkey}` -- if miner has unused credit from failed prior submission, skip payment
7. **Calculate TAO required** (line 1644): Fetches TAO price from CoinGecko, computes `$5.00 / TAO_price`
8. **Confirm payment** (line 1676): Interactive Y/N prompt showing amount
9. **Connect to chain** (line 1686): Creates `bt.subtensor(config=config)` -- deferred to avoid websocket timeout during user input
10. **Execute TAO transfer** (line 1714): `transfer_tao()` sends TAO to LeadPoet coldkey:
    - Mainnet (netuid 71): `5ExoWGyajvzucCqS5GxZSpuzzXEzG1oNFcDqdW3sXeTujoD7`
    - Testnet (netuid 401): `5Gh5kw7rV1x7FDDd5E3Uc7YYMoeQtm4gn93c7VYeL5oUyoAD`
11. **Submit to gateway** (line 1733): `POST /qualification/model/submit` with s3_key, code_hash, payment proof (block_hash + extrinsic_index)

### The $5 Payment
- Cost: `QUALIFICATION_SUBMISSION_COST_USD = $5.00` (line 1033)
- Purpose: Anti-spam for qualification model submissions
- Converted to TAO at current market price (CoinGecko API) + 1% buffer
- Transferred on-chain to LeadPoet coldkey
- Gateway verifies the on-chain transfer exists before accepting submission
- If submission fails AFTER payment, a "submission credit" is preserved for retry
- Rate limit: 2 submissions per day max

### Model Requirements
```
your-model/
  qualify.py      # REQUIRED: must have qualify(lead, icp) function
  requirements.txt  # Optional dependencies
  ...               # Any other files
```

---

## 6. Validator Request Handling

### Axon (gRPC) Forward Path
**File:** `/home/ubuntu/leadpoet/neurons/miner.py`

When a validator sends a `LeadRequest` synapse via Bittensor's axon protocol:

1. **`blacklist()`** (line 905): Called first
   - Immediately calls `self.pause_sourcing()` (stops background lead generation)
   - Checks caller hotkey against metagraph
   - If `force_validator_permit=True`, rejects non-validators
   - If `allow_non_registered=False`, rejects unregistered hotkeys

2. **`priority()`** (line 930): Returns flat 1.0 for all requests

3. **`forward()`** (line 965): Sync wrapper
   - Calls `self.pause_sourcing()`
   - Spawns thread running `asyncio.run(self._forward_async(synapse))`
   - 120-second timeout (returns 504 if exceeded)
   - Calls `self.resume_sourcing()` after completion

4. **`_forward_async()`** (line 606): The actual lead curation logic
   - Acquires `self.sourcing_lock`
   - `classify_industry(synapse.business_desc)` -- LLM-based industry classification
   - `classify_roles(synapse.business_desc)` -- role keyword detection
   - `get_leads_from_pool(1000, industry, region, wallet)` -- tries cloud first, falls back to local JSON
   - Filters by role, random-samples to `num_leads * 3`
   - If pool empty: generates new leads via `get_leads()`
   - Maps to standardized format (email, business, full_name, etc.)
   - Requires `email` + `business` minimum
   - `rank_leads(mapped_leads, description=synapse.business_desc)` -- intent scoring
   - Returns top `synapse.num_leads` leads via `synapse.leads = top_leads`
   - Sets `synapse.dendrite.status_code = 200`

### LeadRequest Synapse
**File:** `/home/ubuntu/leadpoet/Leadpoet/protocol.py`

```python
class LeadRequest(bt.Synapse):
    num_leads: int
    business_desc: str = ""
    industry: Optional[str] = ""
    region: Optional[str] = ""
    leads: Optional[List[dict]] = None  # Response field
```

---

## 7. HTTP Server

**File:** `/home/ubuntu/leadpoet/neurons/miner.py`

### Setup (Miner.__init__, line 66)
```python
self.app = web.Application()
self.app.add_routes([web.post('/lead_request', self.handle_lead_request)])
```

### Start
**`start_http_server()`** (line 953):
- Uses `aiohttp.web`
- Port: `self.config.axon.port + 100` (finds next available port from there)
- Binds to `0.0.0.0`

**IMPORTANT:** The HTTP server `start_http_server()` is **never actually called** in the current `main()` flow. The `run_miner()` async function (line 1961) only starts `sourcing_loop`. The HTTP server code exists but is **unused/dead code** in the current architecture.

### Handler: POST /lead_request
**`handle_lead_request()`** (line 759):
- Nearly identical logic to `_forward_async()` but via HTTP instead of gRPC
- Returns JSON: `{"leads": [...], "status_code": 200, "status_message": "OK", "process_time": "0"}`
- Also pushes leads to Supabase via `push_prospects_to_cloud()`

### Is It Required?
No. The HTTP server is not started in the current codebase. All validator-miner communication uses the Bittensor axon (gRPC). The HTTP handler appears to be legacy/alternative code.

---

## 8. Authentication

### Trustless Gateway Concept

The gateway uses **wallet-based Ed25519 signature verification** instead of JWT tokens or server-issued credentials. This is called the "trustless gateway" model (BRD Section 3.5).

**File:** `/home/ubuntu/leadpoet/gateway/utils/signature.py`

### How It Works

For every gateway call, the miner:
1. Constructs a deterministic message string
2. Signs it with `wallet.hotkey.sign(message.encode())`
3. Sends the signature as hex in the request

The gateway:
1. Reconstructs the expected message from request fields
2. Creates a `Keypair(ss58_address=actor_hotkey)` (public key only)
3. Calls `keypair.verify(message, signature_bytes)`
4. Also verifies the hotkey is registered on-chain via `is_registered_hotkey_async()`

### Message Format (all gateway endpoints)
```
{event_type}:{actor_hotkey}:{nonce}:{ts}:{payload_hash}:{build_id}
```
Where:
- `event_type`: `SUBMISSION_REQUEST`, `SUBMIT_LEAD`, `GET_EPOCH_LEADS`, etc.
- `actor_hotkey`: SS58 address
- `nonce`: UUID v4 (checked for uniqueness to prevent replay attacks)
- `ts`: ISO 8601 timestamp (checked against `TIMESTAMP_TOLERANCE_SECONDS`)
- `payload_hash`: SHA256 of `JSON.dumps(payload, sort_keys=True, separators=(',', ':'))`
- `build_id`: Code version identifier

### Nonce Protection
The gateway stores used nonces and rejects duplicates, preventing replay attacks.

### Legacy Authentication (Supabase)
Some functions still use Supabase JWT tokens:
- `push_prospects_to_cloud()` uses `SUPABASE_JWT` env var with `CustomSupabaseClient`
- JWT contains claims: `role`, `app_role`, `hotkey`
- Public read-only access uses `SUPABASE_ANON_KEY` (hardcoded, for transparency_log queries)

### Legacy API Authentication
`_signed_body()` (cloud_db.py line 1158):
```python
payload = generate_timestamp(json.dumps(extra, sort_keys=True))
sig_b64 = base64.b64encode(wallet.hotkey.sign(payload)).decode()
return {"wallet": wallet.hotkey.ss58_address, "signature": sig_b64, **extra}
```

---

## 9. Rate Limits

### Gateway-Side Enforcement (Primary)
**File:** `/home/ubuntu/leadpoet/gateway/utils/rate_limiter.py`

| Limit | Value | Reset |
|-------|-------|-------|
| Max submissions/day | 1,000 | Midnight UTC |
| Max rejections/day | 250 | Midnight UTC |
| Min seconds between submissions | 20 seconds | Per-submission cooldown |

**Architecture:**
- In-memory cache (`_rate_limit_cache` dict) for O(1) lookups
- Persisted to Supabase `miner_rate_limits` table (survives restarts)
- Loaded from Supabase on first use
- Checked BEFORE signature verification (DoS protection)
- Atomic `reserve_submission_slot()` function prevents race conditions where multiple simultaneous requests bypass limits

**Functions:**
- `check_rate_limit(hotkey)` -> (allowed, reason, stats) -- read-only check
- `reserve_submission_slot(hotkey)` -> (allowed, reason, stats) -- atomic check+increment
- `increment_submission(hotkey, success)` -> stats -- post-processing increment
- `mark_submission_failed(hotkey)` -> stats -- increment rejections only
- `get_rate_limit_stats(hotkey)` -> stats -- read-only query

### Miner-Side Enforcement (Pre-flight)
**File:** `/home/ubuntu/leadpoet/Leadpoet/utils/cloud_db.py`

The miner also has client-side rate limit handling:

1. **Supabase RLS Rate Limits** (lines 632-809): `push_prospects_to_cloud()` catches specific Postgres errors:
   - P0001: 50 rejected leads -> cooldown until midnight ET
   - P0002: 1000 submissions/day limit
   - P0005: Hotkey mismatch

2. **Duplicate pre-checks** (sourcing loop lines 224-240): Before calling `/presign`, the miner checks:
   - `check_email_duplicate(email)` -- queries public `transparency_log` table
   - `check_linkedin_combo_duplicate(linkedin, company_linkedin)` -- same table

### Qualification Model Rate Limits
- 2 submissions per day (checked at `/qualification/model/presign`)
- Returned in presign response: `daily_submissions_used`, `daily_submissions_max`
- Credits preserved for failed submissions

---

## 10. Cloud DB Module

**File:** `/home/ubuntu/leadpoet/Leadpoet/utils/cloud_db.py`

### Module Constants
- `GATEWAY_URL` = env `GATEWAY_URL` or `http://54.226.209.164:8000` (line 20)
- `API_URL` = env `LEAD_API` or `https://leadpoet-api-511161415764.us-central1.run.app` (line 21)
- `SUBNET_ID` = env `NETUID` or `71` (line 24)
- `NETWORK` = env `SUBTENSOR_NETWORK` or `finney` (line 25)
- `SUPABASE_URL` = `https://qplwoislplkcegvdmbim.supabase.co` (hardcoded, line 33)
- `SUPABASE_ANON_KEY` = hardcoded public read-only key (line 34)

### Custom Supabase Client Classes (lines 37-253)
- `RPCResponse` -- wraps RPC results
- `CustomSupabaseClient` -- HTTP client using direct PostgREST API with JWT
- `CustomTableQuery` -- Query builder (select, eq, in_, gte, lt, order, limit, insert, upsert, update)
- `CustomResponse` -- Response wrapper matching supabase-py API
- `NotFilter` -- NOT filter wrapper

### Verifier Singleton (lines 290-459)
- `_Verifier` class with sync and async methods
- `is_miner(ss58)` / `is_miner_async(ss58)` -- checks metagraph registration
- `is_validator(ss58)` / `is_validator_async(ss58)` -- checks validator permit
- `_VERIFY = _Verifier()` -- singleton instance

### Function Catalog

**Client Initialization:**
| Function | Line | Purpose |
|----------|------|---------|
| `get_supabase_client()` | 255 | Create CustomSupabaseClient with `SUPABASE_JWT` env var |

**Read Functions:**
| Function | Line | Endpoint/Table | Auth |
|----------|------|----------------|------|
| `get_cloud_leads(wallet, limit)` | 466 | `GET {API_URL}/leads` | Miner registration check |
| `fetch_prospects_from_cloud(wallet, limit)` | 812 | Supabase `prospect_queue` via RPC `pull_prospects_for_validator` | Validator JWT |
| `get_rejection_feedback(wallet, limit)` | 1014 | Supabase `rejection_feedback` table | Miner JWT + RLS |
| `fetch_curation_requests()` | 1134 | `POST {API_URL}/curate/fetch` | None |
| `fetch_curation_result(request_id)` | 1150 | `GET {API_URL}/curate/result/{id}` | None |
| `fetch_miner_curation_request(wallet)` | 1171 | `POST {API_URL}/curate/miner_request/fetch` | Signed body |
| `fetch_miner_curation_result(wallet)` | 1182 | `POST {API_URL}/curate/miner_result/fetch` | Signed body |
| `fetch_broadcast_requests(wallet, role)` | 1243 | **DEPRECATED** -- returns empty list | N/A |
| `get_broadcast_status(request_id)` | 1324 | Supabase `api_requests` table | Supabase JWT |
| `fetch_validator_rankings(request_id)` | 1396 | Supabase `validator_rankings` table | Supabase JWT |
| `fetch_miner_leads_for_request(request_id)` | 1556 | Supabase `miner_submissions` table | Supabase JWT |
| `check_email_duplicate(email)` | 1639 | Supabase `transparency_log` via ANON key | Public (no auth) |
| `check_linkedin_combo_duplicate(li, co_li)` | 1820 | Supabase `transparency_log` via ANON key | Public (no auth) |
| `gateway_get_epoch_leads(wallet, epoch_id)` | 2208 | `GET {GATEWAY_URL}/epoch/{id}/leads` | Wallet signature |

**Write Functions:**
| Function | Line | Endpoint/Table | Auth |
|----------|------|----------------|------|
| `save_leads_to_cloud(wallet, leads)` | 475 | `POST {API_URL}/leads` | Signed body |
| `push_prospects_to_cloud(wallet, prospects)` | 504 | Supabase `prospect_queue` insert | Miner JWT + RLS |
| `submit_validation_assessment(wallet, ...)` | 876 | Supabase `validation_tracking` insert | Validator JWT + RLS |
| `push_curation_request(payload)` | 1125 | `POST {API_URL}/curate` | None |
| `push_curation_result(result)` | 1143 | `POST {API_URL}/curate/result` | None |
| `push_miner_curation_request(wallet, payload)` | 1165 | `POST {API_URL}/curate/miner_request` | Signed body |
| `push_miner_curation_result(wallet, result)` | 1178 | `POST {API_URL}/curate/miner_result` | Signed body |
| `push_validator_weights(wallet, uid, weights)` | 1188 | `POST {API_URL}/validator_weights` | Signed body |
| `broadcast_api_request(wallet, ...)` | 1196 | Supabase `api_requests` insert | Supabase JWT |
| `mark_broadcast_processing(wallet, request_id)` | 1287 | Supabase `api_requests` update | Supabase JWT |
| `push_validator_ranking(wallet, ...)` | 1349 | Supabase `validator_rankings` insert | Supabase JWT |
| `mark_consensus_complete(request_id, leads)` | 1430 | `POST {API_URL}/api_requests/complete` | None |
| `log_consensus_metrics(...)` | 1457 | `POST {API_URL}/consensus_metrics/log` | None |
| `push_miner_curated_leads(wallet, id, leads)` | 1519 | Supabase `miner_submissions` insert | Supabase JWT |
| `sync_metagraph_to_supabase(metagraph, netuid)` | 1587 | Supabase `metagraph_cache` upsert | Service role key |

**Gateway Functions (Trustless):**
| Function | Line | Endpoint | Auth |
|----------|------|----------|------|
| `gateway_get_presigned_url(wallet, lead)` | 1905 | `POST {GATEWAY_URL}/presign` | Wallet signature |
| `gateway_upload_lead(url, lead)` | 2024 | `PUT <presigned_url>` | S3 presigned URL |
| `gateway_verify_submission(wallet, lead_id)` | 2058 | `POST {GATEWAY_URL}/submit/` | Wallet signature |

**Utility Functions:**
| Function | Line | Purpose |
|----------|------|---------|
| `_signed_body(wallet, extra)` | 1158 | Create signed request body for legacy API |
| `normalize_linkedin_url(url, type)` | 1733 | Normalize LinkedIn URL for dedup hashing |
| `compute_linkedin_combo_hash(li, co_li)` | 1793 | SHA256 of `profile||company` for dedup |

---

## 11. Scoring and Rewards

### Reputation Score (0-48 points)
**File:** `/home/ubuntu/leadpoet/validator_models/automated_checks.py` (lines 964-1018)

The reputation score is computed by validators during lead validation. It is NOT computed by miners, but affects their rewards.

Five soft checks run in parallel:
| Check | Source File | Max Points |
|-------|-----------|------------|
| Wayback Machine | `checks_repscore.py:check_wayback_machine()` | 6 |
| SEC EDGAR | `checks_repscore.py:check_sec_edgar()` | 12 |
| WHOIS/DNSBL | `checks_repscore.py:check_whois_dnsbl_reputation()` | 10 |
| GDELT Press/Media | `checks_repscore.py:check_gdelt_mentions()` | 10 |
| Companies House | `checks_repscore.py:check_companies_house()` | 10 |
| **Total** | | **0-48** |

**Enterprise company modifier:** For companies with 10,001+ employees:
- If ICP match: cap rep_score at 10
- If no ICP match: cap rep_score at 5

### Weight Calculation
**File:** `/home/ubuntu/leadpoet/Leadpoet/base/utils/pool.py`

`calculate_per_query_rewards()` (line 101):

For each unique lead (by email):
- **Sourcing reward (40%)**: Goes to `lead["source"]` (miner hotkey that sourced the lead)
- **Curating reward (60%)**: Goes to `lead["curated_by"]` (miner hotkey that curated/ranked the lead)

If multiple miners curate the same lead, curating reward is split proportionally by `conversion_score`.

**Combined weight:** `W = sourcing_score + curating_score`

**Emissions:** `200 Alpha * (W_miner / W_total)` per emission interval

### Epoch System
**File:** `/home/ubuntu/leadpoet/Leadpoet/validator/reward.py`

- Epoch duration: 72 minutes = 360 blocks (12 seconds/block)
- Epoch number: `block_number // 360`
- Background monitor checks every 30 seconds for epoch transitions
- On transition: clears tracking data for new epoch

### On-Chain Weight Setting
Validators set weights on-chain based on:
1. Lead quality scores from validation pipeline
2. Reputation scores (0-48)
3. ICP match multiplier (1.5x for matching leads)
4. Sourcing/curating split (40%/60%)

### Qualification Model Champion
- 5% of subnet emissions allocated to the champion qualification model
- Evaluated against 100 ICPs
- Must beat current champion by >5% to take over
- Status checkable at: `{GATEWAY_URL}/qualification/model/{model_id}/status`

---

## Summary: Key Architecture Decisions

1. **Dual submission path**: Leads go through trustless gateway (wallet signatures) for storage, with Supabase as secondary persistence for prospect queue
2. **Three authentication methods coexist**: Wallet signatures (gateway), JWT tokens (Supabase), and signed body (legacy Cloud Run API)
3. **Sourcing pauses during curation**: When a validator query arrives, `sourcing_mode` is set to False and the sourcing task is cancelled
4. **Rate limits are gateway-enforced**: The miner does pre-flight duplicate checks but the authoritative rate limits are on the gateway side
5. **Two gateway IPs in code**: `54.226.209.164` (cloud_db.py default) and `52.91.135.79` (miner.py/validator.py default) -- unified by `GATEWAY_URL` env var
6. **HTTP server is dead code**: The aiohttp web server is initialized but never started
7. **Curation loops disabled**: `cloud_curation_loop` and `broadcast_curation_loop` are commented out -- only `sourcing_loop` runs
