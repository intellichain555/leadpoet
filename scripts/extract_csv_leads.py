"""
Extract leads from leads-YYYY-MM-DD.csv into the miner's lead dict structure.

Maps CSV columns → miner lead fields, normalizes employee_count to gateway
ranges, and writes output to data/csv_leads.json.

Usage:
    python scripts/extract_csv_leads.py
    python scripts/extract_csv_leads.py --csv docs/leads-2026-03-02.csv --out data/csv_leads.json
"""

import argparse
import csv
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Valid gateway employee-count ranges (must match submit.py exactly)
# ---------------------------------------------------------------------------
VALID_EMPLOYEE_COUNTS = [
    "0-1", "2-10", "11-50", "51-200", "201-500",
    "501-1,000", "1,001-5,000", "5,001-10,000", "10,001+"
]


def normalize_employee_count(raw: str) -> str:
    """Convert a raw number or existing range string to a valid gateway range."""
    if not raw:
        return "2-10"
    raw = raw.strip()
    if raw in VALID_EMPLOYEE_COUNTS:
        return raw
    numbers = re.findall(r"\d+", raw.replace(",", ""))
    if numbers:
        n = int(numbers[0])
        if n <= 1:
            return "0-1"
        elif n <= 10:
            return "2-10"
        elif n <= 50:
            return "11-50"
        elif n <= 200:
            return "51-200"
        elif n <= 500:
            return "201-500"
        elif n <= 1000:
            return "501-1,000"
        elif n <= 5000:
            return "1,001-5,000"
        elif n <= 10000:
            return "5,001-10,000"
        else:
            return "10,001+"
    return "2-10"


# ---------------------------------------------------------------------------
# Industry mapping: CSV "Industry" column → (sub_industry, industry)
# ---------------------------------------------------------------------------
INDUSTRY_MAP = {
    "management consulting":        ("Consulting", "Professional Services"),
    "consulting":                   ("Consulting", "Professional Services"),
    "professional services":        ("Consulting", "Professional Services"),
    "nonprofit organization management": ("Consulting", "Professional Services"),
    "investment management":        ("Asset Management", "Financial Services"),
    "education management":         ("EdTech", "Education"),
}

DEFAULT_INDUSTRY = ("Consulting", "Professional Services")


def map_industry(raw: str):
    """Return (sub_industry, industry) for a raw CSV industry string."""
    return INDUSTRY_MAP.get(raw.strip().lower(), DEFAULT_INDUSTRY)


def determine_source_type(source_url: str) -> str:
    """Mirror the logic in source_provenance.determine_source_type for CSV leads."""
    if not source_url:
        return "company_site"
    url_lower = source_url.lower()
    if "linkedin.com" in url_lower:
        return "public_registry"
    if "crunchbase.com" in url_lower:
        return "public_registry"
    if "contact" in url_lower or "form" in url_lower:
        return "first_party_form"
    return "company_site"


# Domain-like pattern that might appear in role strings (e.g. "Ceen.ai")
_DOMAIN_IN_ROLE = re.compile(
    r"\b\w+\.(ai|io|co|com|net|org|de|uk|us|ca|fr|eu)\b", re.IGNORECASE
)


def clean_role(raw: str, max_len: int = 80) -> str:
    """
    Sanitize a role string for the gateway:
      - Strip domain-like substrings (e.g. "Ceen.ai")
      - Truncate at the last natural separator (, | :) before max_len
    """
    role = raw.strip()

    # Remove domain-like tokens (e.g. "Founder Ceen.ai" → "Founder")
    role = _DOMAIN_IN_ROLE.sub("", role).strip().strip(",|: ").strip()

    if len(role) <= max_len:
        return role

    # Truncate at the last separator before max_len
    truncated = role[:max_len]
    for sep in (" | ", ", ", ": ", " "):
        idx = truncated.rfind(sep)
        if idx > 10:               # leave at least 10 chars
            return truncated[:idx].strip().strip(",|: ").strip()

    return truncated.strip()


# ---------------------------------------------------------------------------
# CSV column → miner field mapping
# ---------------------------------------------------------------------------
def row_to_lead(row: dict) -> dict:
    """
    Convert a single CSV row to the miner's sanitized lead dict.

    CSV columns used:
        First Name, Last Name, Full Name
        Email
        Title, Headline
        Company Name, Company Website, Company Domain
        Industry
        Employees Count
        City, State, Country          (person's location)
        LinkedIn
        Company LinkedIn
        Company City, Company State, Company Country   (HQ)
    """
    sub_industry, industry = map_industry(row.get("Industry", ""))

    website = row.get("Company Website", "").strip()
    source_url = website  # company website is the evidence source
    source_type = determine_source_type(source_url)

    linkedin = row.get("LinkedIn", "").strip()
    # Gateway rejects LinkedIn URLs in source_url; keep linkedin only in its own field
    if "linkedin.com" in source_url.lower():
        source_url = website  # fall back to company site

    return {
        # Person
        "full_name":       row.get("Full Name", "").strip(),
        "first":           row.get("First Name", "").strip(),
        "last":            row.get("Last Name", "").strip(),
        "email":           row.get("Email", "").strip(),
        "role":            clean_role(row.get("Title", "")),
        "linkedin":        linkedin,
        "description":     row.get("Headline", "").strip(),

        # Company
        "business":        row.get("Company Name", "").strip(),
        "website":         website,
        "company_linkedin": row.get("Company LinkedIn", "").strip(),
        "employee_count":  normalize_employee_count(row.get("Employees Count", "")),

        # Industry taxonomy
        "industry":        industry,
        "sub_industry":    sub_industry,

        # Person's location (used for lead city/state/country)
        "country":         row.get("Country", "").strip(),
        "state":           row.get("State", "").strip(),
        "city":            row.get("City", "").strip(),

        # HQ location (company headquarters)
        "hq_country":      row.get("Company Country", "").strip(),
        "hq_state":        row.get("Company State", "").strip(),
        "hq_city":         row.get("Company City", "").strip(),

        # Source provenance
        "source_url":      source_url,
        "source_type":     source_type,
        "license_doc_hash": "",
        "license_doc_url":  "",
    }


def is_valid_lead(lead: dict) -> bool:
    """Return True only if the minimum required fields are present."""
    return bool(
        lead.get("email")
        and lead.get("business")
        and lead.get("source_url")   # gateway source provenance requires a reachable URL
        and lead.get("role")         # gateway rejects empty roles
    )


def main():
    parser = argparse.ArgumentParser(description="Convert leads CSV to miner lead JSON")
    parser.add_argument(
        "--csv",
        default="docs/leads-2026-03-02.csv",
        help="Path to input CSV (relative to leadpoet root or absolute)",
    )
    parser.add_argument(
        "--out",
        default="data/csv_leads.json",
        help="Path to output JSON (relative to leadpoet root or absolute)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    csv_path = Path(args.csv) if Path(args.csv).is_absolute() else root / args.csv
    out_path = Path(args.out) if Path(args.out).is_absolute() else root / args.out

    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    leads = []
    skipped = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lead = row_to_lead(row)
            if is_valid_lead(lead):
                leads.append(lead)
            else:
                skipped += 1

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)

    print(f"✅ Extracted {len(leads)} leads → {out_path}")
    if skipped:
        print(f"⚠️  Skipped {skipped} rows (missing email, company name, website, or role)")

    # Print a quick sample
    if leads:
        print("\nSample lead (first row):")
        print(json.dumps(leads[0], indent=2))


if __name__ == "__main__":
    main()
