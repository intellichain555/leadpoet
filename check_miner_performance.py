#!/usr/bin/env python3
"""
Check miner performance on LeadPoet Subnet 71.

Fetches data from subnet71.com dashboard APIs and the gateway
to display comprehensive miner performance metrics.

Usage:
    python3 check_miner_performance.py [--hotkey <HOTKEY>] [--epochs <N>] [--json]
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

DASHBOARD_BASE = "https://www.subnet71.com"
GATEWAY_BASE = "http://52.91.135.79:8000"
DEFAULT_HOTKEY = "5GHSH1EQAwJ5AbGdWTmSVRwESKecTyM9SyzPiTd8psqqxvYw"
NETUID = 71


def fetch_json(url: str, timeout: int = 30) -> dict | None:
    """Fetch JSON from a URL, return None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeadPoet-MinerCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"  [WARN] Failed to fetch {url}: {e}", file=sys.stderr)
        return None


def fetch_dashboard(hotkey: str) -> dict | None:
    """Fetch per-miner stats from /api/dashboard."""
    data = fetch_json(f"{DASHBOARD_BASE}/api/dashboard")
    if not data:
        return None

    miner = None
    for m in data.get("minerStats", []):
        if m.get("miner_hotkey") == hotkey:
            miner = m
            break

    return {"summary": data.get("summary", {}), "miner": miner}


def fetch_metagraph(hotkey: str) -> dict | None:
    """Fetch metagraph to get UID and on-chain info."""
    data = fetch_json(f"{DASHBOARD_BASE}/api/metagraph")
    if not data:
        return None

    hotkey_to_uid = data.get("hotkeyToUid", {})
    uid = hotkey_to_uid.get(hotkey)
    return {"uid": uid, "total_neurons": len(hotkey_to_uid)}


def fetch_weights(hotkey: str, uid: int | None) -> dict | None:
    """Fetch current weights from gateway."""
    data = fetch_json(f"{GATEWAY_BASE}/weights/current/{NETUID}")
    if not data or uid is None:
        return None

    uids = data.get("uids", [])
    weights = data.get("weights_u16", [])

    my_weight = None
    my_rank = None
    if uid in uids:
        idx = uids.index(uid)
        my_weight = weights[idx] if idx < len(weights) else None

    # Rank by weight descending
    uid_weight_pairs = list(zip(uids, weights))
    uid_weight_pairs.sort(key=lambda x: x[1], reverse=True)
    for rank, (u, w) in enumerate(uid_weight_pairs, 1):
        if u == uid:
            my_rank = rank
            break

    max_weight = max(weights) if weights else 1
    total_miners = len(uids)

    return {
        "uid": uid,
        "weight_u16": my_weight,
        "weight_normalized": round(my_weight / max_weight, 4) if my_weight and max_weight else 0,
        "rank": my_rank,
        "total_miners": total_miners,
        "epoch_id": data.get("epoch_id"),
        "block": data.get("block"),
    }


def fetch_current_epoch() -> dict | None:
    """Fetch current epoch info from gateway."""
    return fetch_json(f"{GATEWAY_BASE}/epoch/current")


def fetch_recent_leads(hotkey: str, limit: int = 50) -> list | None:
    """Fetch recent lead validations for this miner."""
    data = fetch_json(f"{DASHBOARD_BASE}/api/lead-search?hotkeys={hotkey}&limit={limit}")
    if not data:
        return None
    if isinstance(data, dict):
        return data.get("results", [])
    return data


def fetch_model_competition(hotkey: str) -> dict | None:
    """Fetch qualification model competition status."""
    import time
    data = fetch_json(f"{DASHBOARD_BASE}/api/model-competition?t={int(time.time())}")
    if not data or not data.get("success"):
        return None

    comp = data.get("data", {})
    is_qual_miner = hotkey in comp.get("allQualificationMiners", [])

    champion = comp.get("champion")
    is_champion = False
    if champion and champion.get("miner_hotkey") == hotkey:
        is_champion = True

    my_entries = [e for e in comp.get("leaderboard", []) if e.get("miner_hotkey") == hotkey]

    return {
        "is_qualification_miner": is_qual_miner,
        "is_champion": is_champion,
        "champion": champion,
        "my_leaderboard_entries": my_entries,
        "stats": comp.get("stats", {}),
    }


def format_timestamp(ts_str: str) -> str:
    """Format an ISO timestamp to a readable string."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, AttributeError):
        return str(ts_str)


def print_section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_row(label: str, value, width: int = 30):
    print(f"  {label:<{width}} {value}")


def main():
    parser = argparse.ArgumentParser(description="Check LeadPoet miner performance")
    parser.add_argument("--hotkey", default=DEFAULT_HOTKEY, help="Miner hotkey SS58 address")
    parser.add_argument("--epochs", type=int, default=20, help="Number of recent epochs to show (default: 20)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of formatted text")
    args = parser.parse_args()

    hotkey = args.hotkey
    all_data = {}

    print(f"\n  Checking performance for miner:")
    print(f"  Hotkey: {hotkey}")
    print(f"  Time:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # ── Metagraph ──
    print("\n  Fetching metagraph...", end="", flush=True)
    meta = fetch_metagraph(hotkey)
    all_data["metagraph"] = meta
    registered = meta is not None and meta["uid"] is not None
    if registered:
        print(f" UID {meta['uid']}")
    else:
        print(" NOT FOUND in metagraph (deregistered?)")

    uid = meta["uid"] if meta else None

    # ── Current Epoch ──
    print("  Fetching epoch...", end="", flush=True)
    epoch = fetch_current_epoch()
    all_data["epoch"] = epoch
    if epoch:
        ei = epoch.get("epoch_info", epoch)
        print(f" Epoch {ei.get('current_epoch_id', ei.get('epoch_id', '?'))}")
    else:
        print(" failed")

    # ── Weights / Rank ──
    print("  Fetching weights...", end="", flush=True)
    weights = fetch_weights(hotkey, uid)
    all_data["weights"] = weights
    if weights:
        print(f" rank #{weights['rank']}/{weights['total_miners']}")
    else:
        print(" failed")

    # ── Dashboard Stats ──
    print("  Fetching dashboard stats...", end="", flush=True)
    dash = fetch_dashboard(hotkey)
    all_data["dashboard"] = dash
    if dash and dash.get("miner"):
        print(f" {dash['miner']['total_submissions']} total submissions")
    else:
        print(" no data found")

    # ── Recent Leads ──
    print("  Fetching recent leads...", end="", flush=True)
    leads = fetch_recent_leads(hotkey)
    all_data["recent_leads"] = leads
    if leads:
        print(f" {len(leads)} leads")
    else:
        print(" none")

    # ── Model Competition ──
    print("  Fetching model competition...", end="", flush=True)
    comp = fetch_model_competition(hotkey)
    all_data["model_competition"] = comp
    if comp:
        print(" done")
    else:
        print(" failed")

    # ── JSON output ──
    if args.json:
        print(json.dumps(all_data, indent=2, default=str))
        return 0

    # ══════════════════════════════════════════════════════════
    # Formatted output
    # ══════════════════════════════════════════════════════════

    # ── Identity ──
    print_section("MINER IDENTITY")
    print_row("Hotkey:", hotkey)
    print_row("UID:", uid if uid is not None else "N/A (deregistered)")
    print_row("Registered:", "Yes" if registered else "NO — miner is not in the metagraph!")
    if dash and dash.get("miner"):
        print_row("Coldkey:", dash["miner"].get("coldkey", "N/A"))
    print_row("Subnet:", f"{NETUID} (LeadPoet)")
    if epoch:
        ei = epoch.get("epoch_info", epoch)
        print_row("Current Epoch:", ei.get("current_epoch_id", ei.get("epoch_id", "?")))
        phase = ei.get("phase", "?")
        print_row("Epoch Phase:", phase)

    # ── Weight / Rank ──
    if weights:
        print_section("ON-CHAIN WEIGHT & RANK")
        print_row("Rank:", f"#{weights['rank']} / {weights['total_miners']}")
        print_row("Weight (u16):", f"{weights['weight_u16']:,}")
        print_row("Weight (normalized):", f"{weights['weight_normalized']:.4f}")
        print_row("Weights Epoch:", weights["epoch_id"])
        print_row("Chain Block:", f"{weights['block']:,}")

        # Tier classification
        norm = weights["weight_normalized"]
        if norm >= 0.9:
            tier = "TOP TIER (validator-level weight)"
        elif norm >= 0.03:
            tier = "HIGH"
        elif norm >= 0.015:
            tier = "ABOVE AVERAGE"
        elif norm >= 0.008:
            tier = "AVERAGE"
        else:
            tier = "BELOW AVERAGE"
        print_row("Tier:", tier)

    # ── Lead Performance ──
    if dash and dash.get("miner"):
        m = dash["miner"]
        print_section("LEAD SUBMISSION PERFORMANCE")
        print_row("Total Submissions:", f"{m['total_submissions']:,}")
        print_row("Accepted:", f"{m['accepted']:,}")
        print_row("Rejected:", f"{m['rejected']:,}")
        print_row("Pending:", f"{m['pending']:,}")
        print_row("Acceptance Rate:", f"{m['acceptance_rate']}%")
        print_row("Avg Rep Score:", f"{m['avg_rep_score']:.2f}")
        print_row("Last 20 Epochs Accepted:", m.get("last20_accepted", "N/A"))
        print_row("Last 20 Epochs Rejected:", m.get("last20_rejected", "N/A"))
        print_row("Current Epoch Accepted:", m.get("current_accepted", "N/A"))
        print_row("Current Epoch Rejected:", m.get("current_rejected", "N/A"))

        # Subnet-wide comparison
        summary = dash.get("summary", {})
        if summary:
            print_section("SUBNET COMPARISON")
            subnet_avg_rate = summary.get("acceptance_rate", 0)
            subnet_avg_rep = summary.get("avg_rep_score", 0)
            my_rate = m["acceptance_rate"]
            my_rep = m["avg_rep_score"]

            print_row("Your Acceptance Rate:", f"{my_rate}%")
            print_row("Subnet Avg Rate:", f"{subnet_avg_rate}%")
            diff_rate = my_rate - subnet_avg_rate
            print_row("Diff:", f"{diff_rate:+.1f}%  {'ABOVE' if diff_rate > 0 else 'BELOW'} average")
            print()
            print_row("Your Avg Rep Score:", f"{my_rep:.2f}")
            print_row("Subnet Avg Rep Score:", f"{subnet_avg_rep:.3f}")
            diff_rep = my_rep - subnet_avg_rep
            print_row("Diff:", f"{diff_rep:+.2f}  {'ABOVE' if diff_rep > 0 else 'BELOW'} average")
            print()
            print_row("Subnet Total Miners:", summary.get("unique_miners", "?"))
            print_row("Subnet Total Submissions:", f"{summary.get('total_submissions', 0):,}")

        # Epoch-by-epoch performance
        ep_perf = m.get("epoch_performance", [])
        if ep_perf:
            show_n = min(args.epochs, len(ep_perf))
            print_section(f"EPOCH PERFORMANCE (last {show_n})")
            print(f"  {'Epoch':<10} {'Accepted':>10} {'Rejected':>10} {'Rate':>10}")
            print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
            for ep in ep_perf[:show_n]:
                eid = ep["epoch_id"]
                acc = ep["accepted"]
                rej = ep["rejected"]
                rate = ep["acceptance_rate"]
                marker = " *" if rate < 70 else ""
                print(f"  {eid:<10} {acc:>10} {rej:>10} {rate:>9.1f}%{marker}")
            if any(ep["acceptance_rate"] < 70 for ep in ep_perf[:show_n]):
                print(f"\n  * = below 70% acceptance rate (investigate)")

    # ── Recent Leads Detail ──
    if leads and isinstance(leads, list) and len(leads) > 0:
        print_section("RECENT LEAD VALIDATIONS (last 10)")
        print(f"  {'Lead ID (short)':<14} {'Decision':<12} {'Rep Score':>10} {'Time'}")
        print(f"  {'-'*14} {'-'*12} {'-'*10} {'-'*20}")
        for lead in leads[:10]:
            lid = lead.get("leadId", "?")[:12] + ".."
            dec = lead.get("decision", "?")
            rep = lead.get("repScore")
            rep_str = str(rep) if rep is not None else "-"
            ts = format_timestamp(lead.get("timestamp", ""))
            rej = lead.get("rejectionReason", "")
            extra = f"  ({rej})" if dec == "REJECTED" and rej else ""
            print(f"  {lid:<14} {dec:<12} {rep_str:>10} {ts}{extra}")

        # Stats from recent leads
        accepted = sum(1 for l in leads if l.get("decision") == "ACCEPTED")
        rejected = sum(1 for l in leads if l.get("decision") == "REJECTED")
        rep_scores = [l.get("repScore", 0) for l in leads if l.get("decision") == "ACCEPTED"]
        if rep_scores:
            avg_rep = sum(rep_scores) / len(rep_scores)
            max_rep = max(rep_scores)
            min_rep = min(rep_scores)
            print(f"\n  Recent batch: {accepted} accepted, {rejected} rejected")
            print(f"  Rep scores (accepted): avg={avg_rep:.1f}, min={min_rep}, max={max_rep}")

    # ── Model Competition ──
    if comp:
        print_section("QUALIFICATION MODEL COMPETITION")
        print_row("Participating:", "Yes" if comp["is_qualification_miner"] else "No")
        print_row("Is Champion:", "Yes" if comp["is_champion"] else "No")

        if comp.get("champion"):
            ch = comp["champion"]
            print_row("Current Champion:", ch.get("miner_hotkey", "N/A")[:20] + "...")
            print_row("Champion Score:", ch.get("score", "N/A"))

        if comp.get("my_leaderboard_entries"):
            print(f"\n  Your leaderboard entries:")
            for entry in comp["my_leaderboard_entries"]:
                print(f"    Rank #{entry.get('rank', '?')}: "
                      f"score={entry.get('total_score', entry.get('final_benchmark_score', '?'))} "
                      f"status={entry.get('status', '?')}")

        stats = comp.get("stats", {})
        if stats:
            print(f"\n  Competition stats:")
            print_row("Total Submissions:", stats.get("totalSubmissions", 0))
            print_row("Unique Miners:", stats.get("uniqueMiners", 0))
            sc = stats.get("statusCounts", {})
            if sc:
                print_row("Evaluating:", sc.get("evaluating", 0))
                print_row("Evaluated:", sc.get("evaluated", 0))

    # ── Summary ──
    print_section("HEALTH SUMMARY")
    issues = []
    goods = []

    if not registered:
        issues.append("DEREGISTERED — miner hotkey is not in the subnet 71 metagraph. Re-register to earn rewards.")

    if weights:
        if weights["weight_normalized"] < 0.008:
            issues.append("Low weight — your miner may be underperforming")
        else:
            goods.append(f"Weight rank #{weights['rank']}/{weights['total_miners']}")

    if dash and dash.get("miner"):
        m = dash["miner"]
        if m["acceptance_rate"] < 70:
            issues.append(f"Low acceptance rate: {m['acceptance_rate']}% (target >80%)")
        else:
            goods.append(f"Acceptance rate: {m['acceptance_rate']}%")

        if m["avg_rep_score"] < 10:
            issues.append(f"Low avg rep score: {m['avg_rep_score']:.1f} (target >15)")
        else:
            goods.append(f"Avg rep score: {m['avg_rep_score']:.1f}")

        if m.get("current_accepted", 0) == 0 and m.get("current_rejected", 0) == 0:
            issues.append("No submissions in current epoch — miner may be offline")
        else:
            goods.append(f"Active this epoch: {m.get('current_accepted', 0)} accepted")

    if not issues:
        print("  All checks passed!")
    else:
        for issue in issues:
            print(f"  [!] {issue}")

    if goods:
        for g in goods:
            print(f"  [OK] {g}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
