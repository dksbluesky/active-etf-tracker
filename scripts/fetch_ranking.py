import json
import os
import ssl
import sys
import time
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
BASELINE_CACHE_PATH = os.path.join(DATA_DIR, "jan_baseline_cache.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "active_etf_ranking.json")
BASELINE_YYYYMM = "20260105"  # any date in January 2026; TWSE returns the whole month

# TWSE's certificate lacks a Subject Key Identifier extension. Newer OpenSSL (e.g. on
# GitHub Actions ubuntu runners) enforces X509_STRICT by default and rejects it, even
# though the cert is otherwise valid. Drop that one flag rather than disabling verification.
_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.verify_flags &= ~ssl.VERIFY_X509_STRICT


def http_get_json(url, retries=3):
    last_err = None
    for attempt in range(retries):
        if attempt:
            time.sleep(3 * attempt)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
        except json.JSONDecodeError as e:
            print(
                f"Attempt {attempt + 1}/{retries}: non-JSON response from {url}: "
                f"HTTP {status}, body[:300]={body[:300]!r}",
                file=sys.stderr,
            )
            last_err = e
        except Exception as e:
            print(f"Attempt {attempt + 1}/{retries}: request to {url} failed: {e}", file=sys.stderr)
            last_err = e
    raise last_err


def fetch_january_baseline(stock_no):
    j = http_get_json(
        f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={BASELINE_YYYYMM}&stockNo={stock_no}"
    )
    if j.get("stat") != "OK" or not j.get("data"):
        return None
    first_row = j["data"][0]
    try:
        return {"date": first_row[0], "close": float(first_row[6].replace(",", ""))}
    except ValueError:
        return None


def load_cache():
    if os.path.exists(BASELINE_CACHE_PATH):
        with open(BASELINE_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(BASELINE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def main():
    print("Fetching today's TWSE market snapshot...", file=sys.stderr)
    today_data = http_get_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    active_etfs = {
        d["Code"]: d for d in today_data
        if d["Code"].startswith("00") and 4 <= len(d["Code"]) <= 6 and d["Code"].endswith("A")
    }
    print(f"{len(active_etfs)} active (主動式) ETF codes found", file=sys.stderr)

    cache = load_cache()
    for sid in active_etfs:
        if sid in cache:
            continue
        try:
            cache[sid] = fetch_january_baseline(sid)
        except Exception as e:
            print(f"  {sid}: baseline fetch error {e}", file=sys.stderr)
            cache[sid] = None
        time.sleep(0.3)
    save_cache(cache)

    rows = []
    for sid, etf in active_etfs.items():
        baseline = cache.get(sid)
        if not baseline or baseline.get("close", 0) <= 0:
            continue
        try:
            end_close = float(etf["ClosingPrice"])
            end_volume = int(etf["TradeVolume"])
        except (ValueError, TypeError):
            continue
        if end_volume <= 0:
            continue
        rows.append({
            "stock_id": sid,
            "stock_name": etf["Name"],
            "baseline_date": baseline["date"],
            "baseline_close": baseline["close"],
            "latest_close": end_close,
            "latest_volume": end_volume,
            "ytd_return_pct": round((end_close - baseline["close"]) / baseline["close"] * 100, 2),
        })

    rows.sort(key=lambda r: r["ytd_return_pct"], reverse=True)
    latest_date = next(iter(active_etfs.values()))["Date"] if active_etfs else None

    output = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "latest_trading_date_roc": latest_date,
        "total_active_etfs_found": len(active_etfs),
        "ranked_count": len(rows),
        "top10": rows[:10],
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUTPUT_PATH}: {len(rows)} ranked, top10 saved", file=sys.stderr)


if __name__ == "__main__":
    main()
