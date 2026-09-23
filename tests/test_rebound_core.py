import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "rebound_core.py"
SPEC = importlib.util.spec_from_file_location("rebound_core", MODULE_PATH)
rebound_core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rebound_core)


def series(closes):
    return [{"date": f"2026-01-{i + 1:02d}", "close": close} for i, close in enumerate(closes)]


class ReboundRuleTests(unittest.TestCase):
    def test_sub_eight_percent_pullback_is_ignored(self):
        prices = series([95, 98, 100, 99, 98, 96, 94, 96, 99, 100, 101])
        self.assertIsNone(rebound_core.find_rebound_event(prices))

    def test_eight_percent_correction_and_confirmed_recovery(self):
        prices = series([95, 98, 100, 99, 96, 92, 94, 98, 100, 101, 102])
        event = rebound_core.find_rebound_event(prices)
        self.assertIsNotNone(event)
        self.assertEqual(event["high_price"], 100)
        self.assertEqual(event["low_price"], 92)
        self.assertEqual(event["recovery_date"], "2026-01-10")
        self.assertEqual(event["recovery_status"], "Pass")

    def test_unrecovered_recent_event_is_unknown(self):
        prices = series([95, 98, 100, 99, 96, 91, 92, 93, 94, 95, 96])
        event = rebound_core.find_rebound_event(prices)
        self.assertEqual(event["recovery_status"], "Unknown")

    def test_core_is_top_ten_or_three_percent(self):
        holdings = [{"code": str(i), "weight_pct": 10 - i * 0.7} for i in range(12)]
        holdings.append({"code": "EXTRA", "weight_pct": 3.1})
        core = rebound_core.core_codes(holdings)
        self.assertIn("0", core)
        self.assertIn("EXTRA", core)
        self.assertNotIn("11", core)


if __name__ == "__main__":
    unittest.main()
