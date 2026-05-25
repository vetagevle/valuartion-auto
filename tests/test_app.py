import unittest

from app import (
    compute_ev,
    compute_multiples_for_company,
    aggregate_peer_stats,
    apply_multiples_to_target,
)


class CompsTemplateTests(unittest.TestCase):
    def setUp(self):
        # Construct TargetCo and 3 CompCos such that multiples are integer-valued
        # This ensures exact equality checks (no floating rounding surprises).

        # TargetCo
        self.target = {
            "company_name": "TargetCo",
            "market_cap": 0.0,
            "shares_outstanding": 100.0,
            "cash": 0.0,
            "sub_debt": 0.0,
            "minority": 0.0,
            # Target metrics (LTM, CY+1, CY+2)
            "sales_ltm": 200.0,
            "sales_cy1": 220.0,
            "sales_cy2": 242.0,
            "ebitda_ltm": 400.0,
            "ebitda_cy1": 440.0,
            "ebitda_cy2": 484.0,
            "ebit_ltm": 100.0,
            "ebit_cy1": 110.0,
            "ebit_cy2": 121.0,
            "net_income_ltm": 40.0,
            "net_income_cy1": 44.0,
            "net_income_cy2": 48.4,
        }

        # Create 3 identical comps where EV=1000 and multiples are integers
        # Set sales=100, ebitda=200, ebit=50, net_income=20, market_cap=1000, cash=0, sub_debt=0
        self.peers = []
        for i in range(3):
            peer = {
                "company_name": f"Comp{i+1}",
                "market_cap": 1000.0,
                "shares_outstanding": 10.0,
                "cash": 0.0,
                "sub_debt": 0.0,
                "minority": 0.0,
                "sales_ltm": 100.0,
                "sales_cy1": 100.0,
                "sales_cy2": 100.0,
                "ebitda_ltm": 200.0,
                "ebitda_cy1": 200.0,
                "ebitda_cy2": 200.0,
                "ebit_ltm": 50.0,
                "ebit_cy1": 50.0,
                "ebit_cy2": 50.0,
                "net_income_ltm": 20.0,
                "net_income_cy1": 20.0,
                "net_income_cy2": 20.0,
            }
            self.peers.append(peer)

    def test_ev_computation(self):
        # EV for peers should be market_cap + debts + minority - cash = 1000
        for p in self.peers:
            ev = compute_ev(p)
            self.assertEqual(ev, 1000.0)

    def test_multiples_per_peer(self):
        # For each peer multiples should be exact integers: EV/Sales=10, EV/EBITDA=5, EV/EBIT=20, P/E=50
        expected = {"ev_sales": 10.0, "ev_ebitda": 5.0, "ev_ebit": 20.0, "pe": 50.0}
        for p in self.peers:
            m = compute_multiples_for_company(p)
            for metric, val in expected.items():
                # check LTM
                self.assertEqual(m[metric]["LTM"], val)

    def test_aggregate_stats(self):
        stats = aggregate_peer_stats(self.peers)
        # since all peers identical, min=max=avg=median=expected
        self.assertEqual(stats["ev_sales"]["LTM"]["min"], 10.0)
        self.assertEqual(stats["ev_sales"]["LTM"]["max"], 10.0)
        self.assertEqual(stats["ev_sales"]["LTM"]["avg"], 10.0)
        self.assertEqual(stats["ev_sales"]["LTM"]["median"], 10.0)

    def test_apply_multiples_to_target_exact(self):
        stats = aggregate_peer_stats(self.peers)
        # Apply median multiples to target
        result = apply_multiples_to_target(self.target, stats, method="median")
        # For EV/Sales LTM: multiple 10, target sales 200 -> implied EV=2000
        item = result["by_metric"]["ev_sales"]["LTM"]
        self.assertEqual(item["multiple"], 10.0)
        self.assertEqual(item["denom"], 200.0)
        self.assertEqual(item["implied_ev"], 2000.0)
        # implied equity = implied_ev - sub_debt - minority + cash = 2000
        self.assertEqual(item["implied_equity"], 2000.0)
        # implied price = equity / shares_outstanding = 2000 / 100 = 20.0
        self.assertEqual(item["implied_price"], 20.0)


if __name__ == "__main__":
    unittest.main()
