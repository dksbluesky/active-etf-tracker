import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

from fetch_ranking import roc_date_to_date


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "rebound")
UNIVERSE_PATH = os.path.join(DATA_DIR, "universe.json")
PRICE_PATH = os.path.join(DATA_DIR, "etf_prices.json")
TAIEX_PATH = os.path.join(DATA_DIR, "taiex_prices.json")
LOOKBACK_CALENDAR_DAYS = 420

_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.verify_flags &= ~ssl.VERIFY_X509_STRICT


def get_json(url, retries=3):
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=45, context=_SSL_CONTEXT) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as error:
            last_error = error
            print(f"Attempt {attempt + 1}/{retries} failed for {url}: {error}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    raise last_error


def roc_compact_to_iso(value):
    return roc_date_to_date(value).isoformat()


def fetch_universe():
    rows = get_json("https://openapi.twse.com.tw/v1/opendata/t187ap47_L")
    funds = []
    for row in rows:
        code = row.get("基金代號", "")
        if not code.endswith("A"):
            continue
        if not row.get("基金類型", "").startswith("國內成分證券主動式交易所交易基金"):
            continue
        if row.get("是否包含國外成分股") != "否":
            continue
        funds.append({
            "stock_id": code,
            "stock_name": row.get("基金簡稱", ""),
            "listing_date": roc_compact_to_iso(row["上市日期"]),
            "classification": row.get("基金類型", ""),
        })
    funds.sort(key=lambda row: row["stock_id"])
    return funds


def month_keys(start_date, end_date):
    current = date(start_date.year, start_date.month, 1)
    end = date(end_date.year, end_date.month, 1)
    while current <= end:
        yield f"{current.year:04d}{current.month:02d}"
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)


def parse_etf_month(report):
    if report.get("stat") != "OK":
        return []
    parsed = []
    for row in report.get("data", []):
        try:
            parsed.append({"date": roc_date_to_date(row[0]).isoformat(), "close": float(row[6].replace(",", ""))})
        except (IndexError, TypeError, ValueError):
            continue
    return parsed


def parse_taiex_month(report):
    if report.get("stat") != "OK":
        return []
    parsed = []
    for row in report.get("data", []):
        try:
            parsed.append({"date": roc_date_to_date(row[0]).isoformat(), "close": float(row[4].replace(",", ""))})
        except (IndexError, TypeError, ValueError):
            continue
    return parsed


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def fetch_etf_month(stock_id, month):
    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?" + urllib.parse.urlencode({
        "response": "json", "date": month + "01", "stockNo": stock_id,
    })
    return parse_etf_month(get_json(url))


def fetch_taiex_month(month):
    url = "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?" + urllib.parse.urlencode({
        "response": "json", "date": month + "01",
    })
    return parse_taiex_month(get_json(url))


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    funds = fetch_universe()
    today = date.today()
    cutoff = today - timedelta(days=LOOKBACK_CALENDAR_DAYS)
    price_cache = load(PRICE_PATH, {})
    taiex_cache = load(TAIEX_PATH, {"months": {}})

    for fund in funds:
        stock_id = fund["stock_id"]
        listing_date = date.fromisoformat(fund["listing_date"])
        start = max(cutoff, listing_date)
        cached = price_cache.setdefault(stock_id, {"months": {}})
        for month in month_keys(start, today):
            if month in cached["months"] and month != f"{today.year:04d}{today.month:02d}":
                continue
            cached["months"][month] = fetch_etf_month(stock_id, month)
            time.sleep(0.25)
        print(f"{stock_id}: {sum(len(v) for v in cached['months'].values())} cached prices", file=sys.stderr)

    for month in month_keys(cutoff, today):
        if month in taiex_cache["months"] and month != f"{today.year:04d}{today.month:02d}":
            continue
        taiex_cache["months"][month] = fetch_taiex_month(month)
        time.sleep(0.25)

    save(UNIVERSE_PATH, {"generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "funds": funds})
    save(PRICE_PATH, price_cache)
    save(TAIEX_PATH, taiex_cache)
    print(f"Wrote rebound caches for {len(funds)} Taiwan-equity active ETFs", file=sys.stderr)


if __name__ == "__main__":
    main()
