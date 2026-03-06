#!/usr/bin/env python3
"""Fetch sample leads from LeadPoet test database."""

import json
import urllib.request

SUPABASE_URL = "https://qplwoislplkcegvdmbim.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFwbHdvaXNscGxrY2VndmRtYmltIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ4NDcwMDUsImV4cCI6MjA2MDQyMzAwNX0.5E0WjAthYDXaCWY6qjzXm2k20EhadWfigak9hleKZk8"
TABLE_NAME = "test_leads_for_miners"

url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?select=*&limit=50"
req = urllib.request.Request(url, headers={
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
})
with urllib.request.urlopen(req, timeout=30) as resp:
    leads = json.loads(resp.read())
print(f"Fetched {len(leads)} leads")

if leads and isinstance(leads, list):
    # Show field names from first lead
    print(f"\nFields: {list(leads[0].keys())}")
    # Show first 3 leads summary
    for i, lead in enumerate(leads[:3]):
        print(f"\n--- Lead {i+1} ---")
        for k, v in lead.items():
            val = str(v)[:80] if v else "(empty)"
            print(f"  {k}: {val}")

with open("/tmp/leadpoet_test_leads_50.json", "w") as f:
    json.dump(leads, f, indent=2)
print(f"\nSaved to /tmp/leadpoet_test_leads_50.json")
