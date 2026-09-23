import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "fetch_ranking.py"
SPEC = importlib.util.spec_from_file_location("fetch_ranking", MODULE_PATH)
fetch_ranking = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch_ranking)


class RankingBaselineTests(unittest.TestCase):
    def test_cache_rolls_forward_to_current_year(self):
        cache = {
            "OLD": {"date": "114/01/02", "close": 10.0},
            "CURRENT": {"date": "115/01/02", "close": 12.0},
            "MISSING": None,
        }
        self.assertEqual(
            fetch_ranking.cache_for_year(cache, 2026),
            {"CURRENT": {"date": "115/01/02", "close": 12.0}},
        )

    def test_first_year_trading_day_is_ytd(self):
        self.assertEqual(fetch_ranking.return_period_label("115/01/02", "115/01/02"), "YTD")

    def test_later_first_trading_day_is_since_listing(self):
        self.assertEqual(fetch_ranking.return_period_label("115/06/24", "115/01/02"), "Since listing")

    def test_first_valid_month_becomes_baseline(self):
        reports = {
            1: {"stat": "No data"},
            2: {"stat": "No data"},
            3: {"stat": "OK", "data": [["115/03/12", "1", "1", "10", "10", "10", "10.25"]]},
        }
        original_fetch = fetch_ranking.fetch_month
        original_sleep = fetch_ranking.time.sleep
        try:
            fetch_ranking.fetch_month = lambda _sid, _year, month: reports[month]
            fetch_ranking.time.sleep = lambda _seconds: None
            self.assertEqual(
                fetch_ranking.fetch_first_available_baseline("TEST", 2026, 3),
                {"date": "115/03/12", "close": 10.25},
            )
        finally:
            fetch_ranking.fetch_month = original_fetch
            fetch_ranking.time.sleep = original_sleep


if __name__ == "__main__":
    unittest.main()
