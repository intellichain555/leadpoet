#!/usr/bin/env python3
"""
Query local lead tracking database.

Usage:
    python3 lead_report.py                              # Summary stats
    python3 lead_report.py --rejected                   # Show rejected leads with reasons
    python3 lead_report.py --status verified             # Filter by status
    python3 lead_report.py --industry "Cyber Security"   # Filter by industry
    python3 lead_report.py --date-from 2026-03-01        # Date range
    python3 lead_report.py --reason "Invalid Role"       # Search rejection reasons
    python3 lead_report.py --reasons                     # Top rejection reasons
    python3 lead_report.py --limit 100                   # Limit results
    python3 lead_report.py --csv                         # CSV export
"""

import argparse
import csv
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neurons.lead_tracker import LeadTracker


def truncate(s, maxlen):
    if not s:
        return ""
    s = str(s)
    return s[:maxlen - 2] + ".." if len(s) > maxlen else s


def print_stats(tracker):
    stats = tracker.get_stats()
    print()
    print("=" * 70)
    print("  LEAD TRACKING SUMMARY")
    print("=" * 70)
    print(f"  Total leads tracked:  {stats['total']}")
    print(f"  Today:                {stats['today_total']}")
    print(f"    Verified:           {stats['today_verified']}")
    print(f"    Rejected:           {stats['today_rejected']}")
    print()
    print("  STATUS BREAKDOWN")
    print("  " + "-" * 40)
    for status, count in stats["by_status"].items():
        pct = (count / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"  {status:<25s} {count:>6d}  ({pct:5.1f}%)")
    print()
    if stats["top_rejection_reasons"]:
        print("  TOP REJECTION REASONS")
        print("  " + "-" * 60)
        for entry in stats["top_rejection_reasons"]:
            reason = truncate(entry["reason"], 55)
            print(f"  {reason:<55s} {entry['count']:>5d}")
    else:
        print("  No rejection feedback received yet.")
    print()
    print("=" * 70)
    print()


def print_leads_table(leads):
    if not leads:
        print("\n  No leads found.\n")
        return

    # Header
    print()
    fmt = "  {:<5s} {:<12s} {:<20s} {:<20s} {:<28s} {:<15s} {:<19s}"
    header = fmt.format("ID", "Lead ID", "Status", "Business", "Email", "Industry", "Submitted")
    print(header)
    print("  " + "-" * (len(header) - 2))

    for lead in leads:
        lead_id_short = truncate(lead.get("lead_id", ""), 12)
        submitted = (lead.get("submitted_at") or "")[:19]
        print(fmt.format(
            str(lead["id"]),
            lead_id_short,
            truncate(lead["status"], 20),
            truncate(lead.get("business", ""), 20),
            truncate(lead.get("email", ""), 28),
            truncate(lead.get("industry", ""), 15),
            submitted,
        ))
        # Show rejection reason as indented second line
        reason = lead.get("rejection_reason")
        if reason:
            validators = ""
            if lead.get("rejected_by") is not None:
                validators = f" [{lead['rejected_by']}/{lead.get('total_validators', '?')} validators]"
            print(f"        Reason: {reason}{validators}")
            epoch = lead.get("epoch_number")
            if epoch is not None:
                print(f"        Epoch: {epoch}")

        # Show role + full_name for context
        role = lead.get("role", "")
        name = lead.get("full_name", "")
        if role or name:
            print(f"        {name} | {role}")

    print(f"\n  Showing {len(leads)} lead(s)\n")


def print_rejection_reasons(tracker):
    stats = tracker.get_stats()
    reasons = stats["top_rejection_reasons"]
    if not reasons:
        print("\n  No rejection feedback received yet.\n")
        return

    print()
    print("=" * 70)
    print("  TOP REJECTION REASONS")
    print("=" * 70)
    print(f"  {'Reason':<55s} {'Count':>6s}")
    print("  " + "-" * 62)
    for entry in reasons:
        reason = truncate(entry["reason"], 55)
        print(f"  {reason:<55s} {entry['count']:>6d}")
    print()
    print("=" * 70)
    print()


def export_csv(leads, output=sys.stdout):
    if not leads:
        print("No leads to export.", file=sys.stderr)
        return
    fieldnames = list(leads[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for lead in leads:
        writer.writerow(lead)


def main():
    parser = argparse.ArgumentParser(
        description="Query LeadPoet miner lead tracking database"
    )
    parser.add_argument(
        "--db", default="data/leads.db", help="Path to SQLite database"
    )
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument(
        "--rejected", action="store_true",
        help="Show rejected leads (gateway_rejected + rejected_consensus)"
    )
    parser.add_argument("--industry", help="Filter by industry (partial match)")
    parser.add_argument("--date-from", help="Leads submitted on/after (YYYY-MM-DD)")
    parser.add_argument("--date-to", help="Leads submitted on/before (YYYY-MM-DD)")
    parser.add_argument("--email", help="Search by email (partial match)")
    parser.add_argument("--reason", help="Search rejection reason (partial match)")
    parser.add_argument(
        "--reasons", action="store_true", help="Show top rejection reasons only"
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Max results (default: 50)"
    )
    parser.add_argument(
        "--csv", action="store_true", help="Export as CSV"
    )
    parser.add_argument(
        "--stats", action="store_true", help="Show summary statistics only"
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"\n  Database not found: {args.db}")
        print("  The miner creates this automatically when it starts submitting leads.")
        print("  Run the miner first, then use this tool to inspect results.\n")
        sys.exit(1)

    tracker = LeadTracker(db_path=args.db)

    # Summary stats (default if no filters)
    if args.stats or (
        not args.status
        and not args.rejected
        and not args.industry
        and not args.date_from
        and not args.date_to
        and not args.email
        and not args.reason
        and not args.reasons
    ):
        print_stats(tracker)
        if args.stats:
            return

    # Top rejection reasons
    if args.reasons:
        print_rejection_reasons(tracker)
        return

    # Build query
    status = args.status
    if args.rejected and not status:
        # Query both rejection types
        leads_gw = tracker.query_leads(
            status="gateway_rejected", industry=args.industry,
            date_from=args.date_from, date_to=args.date_to,
            email=args.email, rejection_reason_contains=args.reason,
            limit=args.limit,
        )
        leads_cons = tracker.query_leads(
            status="rejected_consensus", industry=args.industry,
            date_from=args.date_from, date_to=args.date_to,
            email=args.email, rejection_reason_contains=args.reason,
            limit=args.limit,
        )
        leads = leads_gw + leads_cons
        # Sort combined by submitted_at descending
        leads.sort(key=lambda x: x.get("submitted_at", ""), reverse=True)
        leads = leads[:args.limit]
    else:
        leads = tracker.query_leads(
            status=status, industry=args.industry,
            date_from=args.date_from, date_to=args.date_to,
            email=args.email, rejection_reason_contains=args.reason,
            limit=args.limit,
        )

    if args.csv:
        export_csv(leads)
    else:
        print_leads_table(leads)


if __name__ == "__main__":
    main()
