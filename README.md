# active-etf-tracker
Taiwan active (主動式) ETF YTD performance ranking + holdings tracker

## Views

- **YTD ranking:** ranks active equity ETFs using the first trading day of the current calendar year. Funds listed later are measured from their first available trading day and labeled `Since listing`.
- **Resilience assessment:** separately compares Taiwan-equity active ETFs by recovery speed, TAIEX outperformance over identical dates, and continuity of rebound-leading core holdings.

## Rebound methodology

- Previous high: five-day pivot high that is also the highest close in the preceding 60 trading sessions.
- Meaningful correction: at least an 8% close-to-close drawdown, with the low at least three trading days after the high.
- Recovery: two consecutive closes at or above the previous high.
- Recovery speed is reported and ranked; there is no arbitrary recovery deadline.
- Market performance shows whether, and by how many percentage points, the rebound beat the TAIEX over identical dates.
- Core holding: top 10 by portfolio weight or weight of at least 3%.
- Missing appropriately dated holdings snapshots is reported as `Insufficient data`, never inferred as continuity.

The three indicators are an objective implementation inspired by the cited article's qualitative framework. They are comparative evidence, not author-defined qualification thresholds or investment advice.

Price and benchmark history comes from TWSE. Holdings snapshots are retained prospectively under `data/holdings_history/`; no unsupported historical holdings are backfilled.
