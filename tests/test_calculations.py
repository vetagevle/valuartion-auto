import unittest
from app import validate_non_negative, calculate_metrics, compute_valuation_range


class CalculationLogicAdditionalTests(unittest.TestCase):
    def test_validate_non_negative_raises(self):
        with self.assertRaises(ValueError):
            validate_non_negative("売上高", -1.0)

    def test_calculate_metrics_handles_zero_and_none(self):
        c = {
            "market_cap": 1000.0,
            "net_income": 0.0,
            "net_assets": 0.0,
            "operating_income": 0.0,
            "depreciation": 0.0,
            "sub_debt": 0.0,
            "cash": 0.0,
            "sales": 0.0,
        }
        m = calculate_metrics(c)
        self.assertIsNone(m["per"]) 
        self.assertIsNone(m["pbr"]) 
        self.assertIsNone(m["ev_sales"]) 
        self.assertIsNone(m["ev_ebitda"]) 
        self.assertIsNone(m["ev_ebit"]) 

    def test_compute_with_partial_multiples_uses_available(self):
        target = {
            "net_income": 100.0,
            "net_assets": 500.0,
            "operating_income": 200.0,
            "depreciation": 50.0,
            "sub_debt": 100.0,
            "cash": 20.0,
            "sales": 1000.0,
        }
        peers = []
        # 3社は有効なPERを持ち、2社はPERが算出できない
        for _ in range(3):
            peers.append({
                "market_cap": 1000.0,
                "net_income": 100.0,
                "net_assets": 1000.0,
                "operating_income": 100.0,
                "depreciation": 50.0,
                "sub_debt": 0.0,
                "cash": 0.0,
                "sales": 100.0,
            })
        for _ in range(2):
            peers.append({
                "market_cap": 500.0,
                "net_income": 0.0,
                "net_assets": 0.0,
                "operating_income": 0.0,
                "depreciation": 0.0,
                "sub_debt": 0.0,
                "cash": 0.0,
                "sales": 0.0,
            })

        ranges = compute_valuation_range(target, peers)
        # PER は有効な 3 社分で計算される
        self.assertIn("per", ranges)
        self.assertEqual(ranges["per"]["min"], 1000.0)
        self.assertEqual(ranges["per"]["max"], 1000.0)
        self.assertEqual(ranges["per"]["avg"], 1000.0)

    def test_ev_ebitda_applies_net_debt(self):
        peers = []
        for _ in range(5):
            peers.append({
                "market_cap": 5000.0,
                "net_income": 500.0,
                "net_assets": 1000.0,
                "operating_income": 800.0,
                "depreciation": 200.0,
                "sub_debt": 0.0,
                "cash": 0.0,
                "sales": 1000.0,
            })
        target = {
            "operating_income": 100.0,
            "depreciation": 50.0,
            "sub_debt": 300.0,
            "cash": 100.0,
            "net_income": 10.0,
            "net_assets": 100.0,
            "sales": 100.0,
        }
        ranges = compute_valuation_range(target, peers)
        # EV/EBITDA の計算: multiplier=5, target_ebitda=150 -> EV=750, net_debt=200 -> equity=550
        self.assertAlmostEqual(ranges["ev_ebitda"]["avg"], 550.0)

    def test_values_non_negative(self):
        peers = []
        for _ in range(5):
            peers.append({
                "market_cap": 100.0,
                "net_income": 10.0,
                "net_assets": 100.0,
                "operating_income": 1.0,
                "depreciation": 0.0,
                "sub_debt": 0.0,
                "cash": 0.0,
                "sales": 10.0,
            })
        target = {
            "operating_income": 0.1,
            "depreciation": 0.0,
            "sub_debt": 10000.0,
            "cash": 0.0,
            "net_income": 1.0,
            "net_assets": 100.0,
            "sales": 1.0,
        }
        ranges = compute_valuation_range(target, peers)
        for stats in ranges.values():
            for v in stats["values"]:
                self.assertGreaterEqual(v, 0.0)


if __name__ == "__main__":
    unittest.main()
