"""
Re-submit leads from denied_email_verification_unavailable.json directly to the gateway,
skipping the full pipeline (no crawl, no LLM).  The lead data is already complete.
"""
import sys, os, json, time
sys.path.insert(0, "/home/ubuntu/leadpoet")

import bittensor as bt
from Leadpoet.utils.cloud_db import (
    check_email_duplicate,
    check_linkedin_combo_duplicate,
    gateway_get_presigned_url,
    gateway_upload_lead,
    gateway_verify_submission,
)

DENIED_FILE = "/home/ubuntu/leadpoet/data/curated/validator_denied_by_reason/denied_email_verification_unavailable.json"
WALLET_NAME = "lifestream"
WALLET_HOTKEY = "default"
WALLET_PATH = "/home/ubuntu/wallets"

def main():
    wallet = bt.wallet(name=WALLET_NAME, hotkey=WALLET_HOTKEY, path=WALLET_PATH)
    print(f"Wallet: {wallet.hotkey.ss58_address}\n")

    # Load attestation fields (required by gateway since trustless model update)
    attestation_path = "/home/ubuntu/leadpoet/data/regulatory/miner_attestation.json"
    if os.path.exists(attestation_path):
        with open(attestation_path) as f:
            attestation = json.load(f)
        terms_hash = attestation.get("terms_version_hash", "NOT_ATTESTED")
        wallet_ss58 = attestation.get("wallet_ss58", wallet.hotkey.ss58_address)
    else:
        print("⚠️  No attestation file — using wallet address directly")
        terms_hash = "NOT_ATTESTED"
        wallet_ss58 = wallet.hotkey.ss58_address

    attestation_fields = {
        "wallet_ss58": wallet_ss58,
        "terms_version_hash": terms_hash,
        "lawful_collection": True,
        "no_restricted_sources": True,
        "license_granted": True,
    }
    print(f"Attestation: wallet={wallet_ss58[:20]}... terms={terms_hash[:16]}...\n")

    with open(DENIED_FILE) as f:
        denied = json.load(f)

    print(f"Leads to re-submit: {len(denied)}\n")

    ok = skip_dup = gateway_fail = 0
    results = []

    for i, d in enumerate(denied, 1):
        lead = d["lead"]
        email = lead.get("email", "?")
        business = lead.get("business", "?")
        print(f"[{i:02d}/{len(denied)}] {business} / {email}")

        # Duplicate check
        if check_email_duplicate(email):
            print(f"  ⏭️  Duplicate email — skip")
            skip_dup += 1
            results.append({"email": email, "result": "duplicate"})
            continue

        li = lead.get("linkedin", "")
        co_li = lead.get("company_linkedin", "")
        if li and co_li and check_linkedin_combo_duplicate(li, co_li):
            print(f"  ⏭️  Duplicate LinkedIn combo — skip")
            skip_dup += 1
            results.append({"email": email, "result": "duplicate"})
            continue

        # Add attestation fields (gateway requires these in lead blob)
        lead = {**lead, **attestation_fields}

        # Get presigned URL
        presign = gateway_get_presigned_url(wallet, lead)
        if not presign:
            print(f"  ❌ Presign failed — cooling down 20s...")
            gateway_fail += 1
            results.append({"email": email, "result": "presign_failed"})
            time.sleep(20)
            continue

        # Upload lead
        uploaded = gateway_upload_lead(presign["s3_url"], lead)
        if not uploaded:
            print(f"  ❌ S3 upload failed")
            gateway_fail += 1
            results.append({"email": email, "result": "upload_failed"})
            continue

        print(f"  ✅ Uploaded to S3")

        # Verify
        verified = gateway_verify_submission(wallet, presign["lead_id"])
        if verified:
            print(f"  ✅ Gateway accepted")
            ok += 1
            results.append({"email": email, "result": "submitted", "lead_id": presign["lead_id"]})
        else:
            print(f"  ⚠️  Gateway rejected")
            gateway_fail += 1
            results.append({"email": email, "result": "gateway_rejected"})

        print(f"  ⏳ Cooling down 20s...")
        time.sleep(20)

    print(f"\n{'='*50}")
    print(f"Submitted OK : {ok}")
    print(f"Duplicates   : {skip_dup}")
    print(f"Gateway fail : {gateway_fail}")
    print(f"Total        : {len(denied)}")

if __name__ == "__main__":
    main()
