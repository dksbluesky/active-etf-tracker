from bisect import bisect_left


MIN_DRAWDOWN_PCT = 8.0
MAX_RECOVERY_DAYS = 30
MIN_OUTPERFORMANCE_PP = 2.0
PIVOT_WING = 2
PRIOR_HIGH_LOOKBACK = 60


def find_rebound_event(prices):
    """Return the latest qualifying correction/rebound event.

    A previous high must be a five-day pivot, also the highest close in the
    preceding 60 sessions.  A correction must draw down at least 8%, with its
    low at least three sessions after the high. Recovery requires two
    consecutive closes at or above the previous high.
    """
    if len(prices) < PIVOT_WING * 2 + 4:
        return None

    candidates = []
    for high_i in range(PIVOT_WING, len(prices) - PIVOT_WING):
        high = prices[high_i]["close"]
        local = prices[high_i - PIVOT_WING: high_i + PIVOT_WING + 1]
        if high < max(row["close"] for row in local):
            continue
        prior = prices[max(0, high_i - PRIOR_HIGH_LOOKBACK + 1): high_i + 1]
        if high < max(row["close"] for row in prior):
            continue

        recovery_i = None
        for i in range(high_i + 2, len(prices)):
            if prices[i - 1]["close"] >= high and prices[i]["close"] >= high:
                recovery_i = i
                break
        endpoint_i = recovery_i if recovery_i is not None else len(prices) - 1
        if endpoint_i <= high_i:
            continue
        low_i = min(range(high_i + 1, endpoint_i + 1), key=lambda i: prices[i]["close"])
        if low_i - high_i < 3:
            continue
        low = prices[low_i]["close"]
        drawdown = (low / high - 1) * 100
        if low > high * (1 - MIN_DRAWDOWN_PCT / 100):
            continue

        elapsed = endpoint_i - low_i
        if recovery_i is not None:
            recovery_status = "Pass" if elapsed <= MAX_RECOVERY_DAYS else "Fail"
        else:
            recovery_status = "Unknown" if elapsed <= MAX_RECOVERY_DAYS else "Fail"

        candidates.append({
            "high_index": high_i,
            "high_date": prices[high_i]["date"],
            "high_price": high,
            "low_index": low_i,
            "low_date": prices[low_i]["date"],
            "low_price": low,
            "max_drawdown_pct": round(drawdown, 2),
            "recovery_index": recovery_i,
            "recovery_date": prices[recovery_i]["date"] if recovery_i is not None else None,
            "trading_days_to_recover": elapsed if recovery_i is not None else None,
            "elapsed_trading_days": elapsed,
            "endpoint_index": endpoint_i,
            "endpoint_date": prices[endpoint_i]["date"],
            "endpoint_price": prices[endpoint_i]["close"],
            "recovery_status": recovery_status,
        })

    return candidates[-1] if candidates else None


def nearest_snapshot(snapshot_dates, target_date, trading_dates, tolerance=3):
    if not snapshot_dates or target_date not in trading_dates:
        return None
    target_i = trading_dates.index(target_date)
    best = None
    for snapshot_date in snapshot_dates:
        pos = bisect_left(trading_dates, snapshot_date)
        possible = [p for p in (pos - 1, pos) if 0 <= p < len(trading_dates)]
        if not possible:
            continue
        distance = min(abs(p - target_i) for p in possible)
        if best is None or distance < best[0]:
            best = (distance, snapshot_date)
    return best[1] if best and best[0] <= tolerance else None


def core_codes(holdings):
    ordered = sorted(holdings, key=lambda h: h["weight_pct"], reverse=True)
    top_ten = {h["code"] for h in ordered[:10]}
    return top_ten | {h["code"] for h in ordered if h["weight_pct"] >= 3.0}


def determine_leaders(low_holdings, stock_returns):
    contributions = []
    for holding in low_holdings:
        stock_return = stock_returns.get(holding["code"])
        if stock_return is None:
            continue
        contribution = holding["weight_pct"] * stock_return / 100
        if contribution > 0:
            contributions.append({**holding, "stock_return_pct": stock_return, "estimated_contribution": contribution})
    contributions.sort(key=lambda row: row["estimated_contribution"], reverse=True)
    total = sum(row["estimated_contribution"] for row in contributions)
    leaders = []
    accumulated = 0.0
    for row in contributions[:5]:
        leaders.append(row)
        accumulated += row["estimated_contribution"]
        if total and accumulated / total >= 0.5:
            break
    return leaders
