import json
import os
import re
import ssl
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "holdings")

# Funds that have a wired-up issuer/source for holdings tracking.
# Both are issued by 統一投信; source is etfinfo.tw. Its rendered HTML table is
# paginated (15 rows/page) and its own day-over-day "持股變化" column is login-gated,
# so instead we pull the full holdings list straight from the page's embedded
# __NUXT_DATA__ payload (Nuxt's devalue-style index-referenced JSON) and compute
# the add/cut/weight-change diff ourselves against the previously committed snapshot.
FUNDS = ["00981A", "00988A"]

_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.verify_flags &= ~ssl.VERIFY_X509_STRICT

_WRAP_TYPES = {"ShallowReactive", "Reactive", "Ref", "ShallowRef"}


def fetch_html(fund_id):
    url = f"https://www.etfinfo.tw/etf/{fund_id}/holdings"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        return resp.read().decode("utf-8")


def _resolve(data, idx, seen):
    if idx in seen:
        return None
    seen = seen | {idx}
    val = data[idx]
    if isinstance(val, list):
        if len(val) == 2 and isinstance(val[0], str) and val[0] in _WRAP_TYPES:
            return _resolve(data, val[1], seen)
        return [_resolve(data, v, seen) if isinstance(v, int) else v for v in val]
    if isinstance(val, dict):
        return {k: (_resolve(data, v, seen) if isinstance(v, int) else v) for k, v in val.items()}
    return val


def parse_holdings(html):
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None, []
    data = json.loads(m.group(1))

    detail_idx = None
    for entry in data:
        if isinstance(entry, dict) and "holdings" in entry and "snapshotDate" in entry:
            detail_idx = entry
            break
    if detail_idx is None:
        return None, []

    snapshot_date = _resolve(data, detail_idx["snapshotDate"], set())
    raw_holdings = _resolve(data, detail_idx["holdings"], set())

    holdings = []
    for h in raw_holdings:
        try:
            holdings.append({
                "code": str(h["code"]),
                "name": str(h["name"]).strip(),
                "weight_pct": float(h["weight"]),
                "shares": int(h["shares"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return snapshot_date, holdings


def diff_holdings(prev_holdings, curr_holdings):
    prev_map = {h["code"]: h for h in prev_holdings}
    curr_map = {h["code"]: h for h in curr_holdings}

    added = [h for c, h in curr_map.items() if c not in prev_map]
    removed = [h for c, h in prev_map.items() if c not in curr_map]
    changed = []
    for c, h in curr_map.items():
        if c in prev_map:
            old_w = prev_map[c]["weight_pct"]
            new_w = h["weight_pct"]
            if abs(old_w - new_w) >= 0.01:
                changed.append({**h, "prev_weight_pct": old_w, "delta_pct": round(new_w - old_w, 2)})

    added.sort(key=lambda h: -h["weight_pct"])
    removed.sort(key=lambda h: -h["weight_pct"])
    changed.sort(key=lambda h: -abs(h["delta_pct"]))
    return {"added": added, "removed": removed, "changed": changed}


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for fund_id in FUNDS:
        path = os.path.join(DATA_DIR, f"{fund_id}.json")
        prev = None
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                prev = json.load(f)

        try:
            html = fetch_html(fund_id)
        except Exception as e:
            print(f"{fund_id}: fetch failed: {e}", file=sys.stderr)
            continue

        snapshot_date, holdings = parse_holdings(html)
        if not holdings:
            print(f"{fund_id}: no holdings parsed, skipping", file=sys.stderr)
            continue

        if prev and prev.get("snapshot_date") == snapshot_date:
            print(f"{fund_id}: snapshot date unchanged ({snapshot_date}), skipping", file=sys.stderr)
            continue

        changes = diff_holdings(prev["holdings"], holdings) if prev else {"added": [], "removed": [], "changed": []}
        holdings.sort(key=lambda h: -h["weight_pct"])

        output = {
            "fund_id": fund_id,
            "snapshot_date": snapshot_date,
            "previous_snapshot_date": prev.get("snapshot_date") if prev else None,
            "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "holdings": holdings,
            "changes": changes,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(
            f"{fund_id}: wrote {len(holdings)} holdings "
            f"({len(changes['added'])} added, {len(changes['removed'])} removed, {len(changes['changed'])} changed)",
            file=sys.stderr,
        )
        time.sleep(1)


if __name__ == "__main__":
    main()
