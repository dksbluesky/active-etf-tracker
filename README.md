# active-etf-tracker
Taiwan active (主動式) ETF YTD performance ranking + holdings tracker

## Views

- **YTD ranking:** ranks active equity ETFs using the first trading day of the current calendar year. Funds listed later are measured from their first available trading day and labeled `Since listing`.
- **Rebound filter:** separately evaluates Taiwan-equity active ETFs for recovery speed, TAIEX outperformance over identical dates, and continuity of rebound-leading core holdings.

## Rebound methodology

- Previous high: five-day pivot high that is also the highest close in the preceding 60 trading sessions.
- Meaningful correction: at least an 8% close-to-close drawdown, with the low at least three trading days after the high.
- Recovery: two consecutive closes at or above the previous high.
- Recovery pass: no more than 30 trading days from the low to confirmed recovery.
- Market pass: rebound beats the TAIEX price index by at least 2 percentage points over identical dates.
- Core holding: top 10 by portfolio weight or weight of at least 3%.
- Missing appropriately dated holdings snapshots produces `Unknown`, never `Pass`.

Price and benchmark history comes from TWSE. Holdings snapshots are retained prospectively under `data/holdings_history/`; no unsupported historical holdings are backfilled.
