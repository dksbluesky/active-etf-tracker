import json
import os
import sys
import time
from datetime import date

from fetch_rebound_data import fetch_etf_month, month_keys
from rebound_core import (
    MIN_OUTPERFORMANCE_PP,
    core_codes,
    determine_leaders,
    find_rebound_event,
    nearest_snapshot,
)


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
REBOUND_DIR = os.path.join(DATA_DIR, "rebound")
HISTORY_DIR = os.path.join(DATA_DIR, "holdings_history")
UNIVERSE_PATH = os.path.join(REBOUND_DIR, "universe.json")
ETF_PRICE_PATH = os.path.join(REBOUND_DIR, "etf_prices.json")
TAIEX_PATH = os.path.join(REBOUND_DIR, "taiex_prices.json")
STOCK_PRICE_PATH = os.path.join(REBOUND_DIR, "stock_prices.json")
OUTPUT_PATH = os.path.join(REBOUND_DIR, "results.json")


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default


def save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def flatten_months(entry):
    by_date = {}
    for rows in entry.get("months", {}).values():
        for row in rows:
            by_date[row["date"]] = row
    return [by_date[key] for key in sorted(by_date)]


def snapshot_files(fund_id):
    folder = os.path.join(HISTORY_DIR, fund_id)
    if not os.path.isdir(folder):
        return {}
    snapshots = {}
    for name in os.listdir(folder):
        if not name.endswith(".json"):
            continue
        snapshot = load(os.path.join(folder, name), {})
        if snapshot.get("snapshot_date"):
            snapshots[snapshot["snapshot_date"]] = snapshot
    return snapshots


def return_between(series, start_date, end_date):
    by_date = {row["date"]: row["close"] for row in series}
    if start_date not in by_date or end_date not in by_date or not by_date[start_date]:
        return None
    return round((by_date[end_date] / by_date[start_date] - 1) * 100, 2)


def ensure_stock_series(stock_id, start_date, end_date, cache):
    entry = cache.setdefault(stock_id, {"months": {}})
    for month in month_keys(date.fromisoformat(start_date), date.fromisoformat(end_date)):
        if month not in entry["months"]:
            entry["months"][month] = fetch_etf_month(stock_id, month)
            time.sleep(0.25)
    return flatten_months(entry)


def continuity_result(fund_id, event, prices, stock_cache):
    snapshots = snapshot_files(fund_id)
    latest = snapshots[max(snapshots)] if snapshots else None
    current_core = []
    if latest:
        current_codes = core_codes(latest["holdings"])
        current_core = [h for h in latest["holdings"] if h["code"] in current_codes]

    trading_dates = [row["date"] for row in prices]
    dates = sorted(snapshots)
    low_snapshot_date = nearest_snapshot(dates, event["low_date"], trading_dates)
    end_snapshot_date = nearest_snapshot(dates, event["endpoint_date"], trading_dates)
    if not low_snapshot_date or not end_snapshot_date:
        return {
            "status": "Unknown",
            "reason": "Insufficient historical holdings data",
            "low_snapshot_date": low_snapshot_date,
            "end_snapshot_date": end_snapshot_date,
            "core_holdings_near_low": [],
            "current_core_holdings": current_core,
            "rebound_leaders": [],
        }

    low_snapshot = snapshots[low_snapshot_date]
    end_snapshot = snapshots[end_snapshot_date]
    stock_returns = {}
    for holding in low_snapshot["holdings"]:
        series = ensure_stock_series(holding["code"], event["low_date"], event["endpoint_date"], stock_cache)
        stock_returns[holding["code"]] = return_between(series, event["low_date"], event["endpoint_date"])

    leaders = determine_leaders(low_snapshot["holdings"], stock_returns)
    if not leaders:
        return {
            "status": "Unknown",
            "reason": "Insufficient underlying-stock price data",
            "low_snapshot_date": low_snapshot_date,
            "end_snapshot_date": end_snapshot_date,
            "core_holdings_near_low": [],
            "current_core_holdings": current_core,
            "rebound_leaders": [],
        }

    low_core_codes = core_codes(low_snapshot["holdings"])
    end_core_codes = core_codes(end_snapshot["holdings"])
    leader_codes = {leader["code"] for leader in leaders}
    continuity_pass = leader_codes <= low_core_codes and leader_codes <= end_core_codes
    low_core = [h for h in low_snapshot["holdings"] if h["code"] in low_core_codes]
    return {
        "status": "Pass" if continuity_pass else "Fail",
        "reason": "All rebound leaders remained core holdings" if continuity_pass else "One or more rebound leaders were not continuously core",
        "low_snapshot_date": low_snapshot_date,
        "end_snapshot_date": end_snapshot_date,
        "core_holdings_near_low": low_core,
        "current_core_holdings": current_core,
        "rebound_leaders": leaders,
        "source_authority": low_snapshot.get("source_authority", "unknown"),
    }


def overall_result(recovery_status, market_status, continuity_status):
    statuses = [recovery_status, market_status, continuity_status]
    if "Fail" in statuses:
        return "Not qualified"
    if statuses == ["Pass", "Pass", "Pass"]:
        return "Qualified"
    if recovery_status == "Pass" and market_status == "Pass" and continuity_status == "Unknown":
        return "Candidate"
    return "Not qualified"


def analyze_fund(fund, prices, taiex, stock_cache):
    event = find_rebound_event(prices)
    if not event:
        return {
            "stock_id": fund["stock_id"],
            "stock_name": fund["stock_name"],
            "recovery_status": "Fail",
            "market_status": "Unknown",
            "continuity_status": "Unknown",
            "overall_result": "Not qualified",
            "data_confidence": "Low" if len(prices) < 20 else "Medium",
            "reason": "No qualifying 8% correction found in the analysis window",
        }

    etf_return = return_between(prices, event["low_date"], event["endpoint_date"])
    market_return = return_between(taiex, event["low_date"], event["endpoint_date"])
    outperformance = None if etf_return is None or market_return is None else round(etf_return - market_return, 2)
    market_status = "Unknown" if outperformance is None else ("Pass" if outperformance >= MIN_OUTPERFORMANCE_PP else "Fail")
    continuity = continuity_result(fund["stock_id"], event, prices, stock_cache)
    overall = overall_result(event["recovery_status"], market_status, continuity["status"])
    confidence = "High" if continuity["status"] != "Unknown" and continuity.get("source_authority") == "official" else "Medium"
    return {
        "stock_id": fund["stock_id"],
        "stock_name": fund["stock_name"],
        "previous_high_date": event["high_date"],
        "previous_high_price": event["high_price"],
        "correction_low_date": event["low_date"],
        "correction_low_price": event["low_price"],
        "maximum_drawdown_pct": event["max_drawdown_pct"],
        "recovery_date": event["recovery_date"],
        "trading_days_to_recover": event["trading_days_to_recover"],
        "elapsed_trading_days": event["elapsed_trading_days"],
        "etf_rebound_return_pct": etf_return,
        "market_return_pct": market_return,
        "outperformance_pp": outperformance,
        "recovery_status": event["recovery_status"],
        "market_status": market_status,
        "continuity_status": continuity["status"],
        "core_holdings_near_low": continuity["core_holdings_near_low"],
        "current_core_holdings": continuity["current_core_holdings"],
        "rebound_leaders": continuity["rebound_leaders"],
        "continuity_reason": continuity["reason"],
        "overall_result": overall,
        "data_confidence": confidence,
    }


def main():
    universe = load(UNIVERSE_PATH, {"funds": []})
    prices = load(ETF_PRICE_PATH, {})
    taiex_cache = load(TAIEX_PATH, {"months": {}})
    stock_cache = load(STOCK_PRICE_PATH, {})
    taiex = flatten_months(taiex_cache)[-252:]
    results = []
    for fund in universe["funds"]:
        series = flatten_months(prices.get(fund["stock_id"], {"months": {}}))[-252:]
        results.append(analyze_fund(fund, series, taiex, stock_cache))
    result_order = {"Qualified": 0, "Candidate": 1, "Not qualified": 2}
    results.sort(key=lambda row: (result_order[row["overall_result"]], row.get("trading_days_to_recover") or 9999, row["stock_id"]))
    save(STOCK_PRICE_PATH, stock_cache)
    save(OUTPUT_PATH, {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "methodology": {
            "analysis_window_trading_days": 252,
            "minimum_drawdown_pct": 8.0,
            "maximum_recovery_days": 30,
            "minimum_outperformance_pp": 2.0,
            "recovery_confirmation_days": 2,
            "core_holding": "Top 10 by weight or weight >= 3%",
        },
        "results": results,
    })
    print(f"Wrote rebound analysis for {len(results)} funds", file=sys.stderr)


if __name__ == "__main__":
    main()
