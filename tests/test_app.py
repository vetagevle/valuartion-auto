import unittest

from app import (
    compute_ev,
    calculate_market_cap,
    calculate_enterprise_value,
    compute_multiples_for_company,
    aggregate_peer_stats,
    apply_multiples_to_target,
    calculate_wacc,
    calculate_dcf_valuation,
    calculate_historical_trends,
    derive_dcf_defaults_from_history,
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

    def test_market_cap_and_enterprise_value(self):
        market_cap = calculate_market_cap(share_price=250.0, shares_outstanding=400.0)
        self.assertEqual(market_cap, 100000.0)

        enterprise_value = calculate_enterprise_value(
            market_cap=market_cap,
            cash=25000.0,
            debt=15000.0,
            minority=5000.0,
        )
        self.assertEqual(enterprise_value, 95000.0)

        self.assertEqual(
            compute_ev({"market_cap": market_cap, "cash": 25000.0, "sub_debt": 15000.0, "minority": 5000.0}),
            95000.0,
        )

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


class DCFTests(unittest.TestCase):
    def setUp(self):
        self.base_revenue = 1000.0
        self.cash = 200.0
        self.debt = 100.0
        self.shares_outstanding = 100.0

        self.historical_target = {
            "sales_fy_minus_3": 810.0,
            "sales_fy_minus_2": 900.0,
            "sales_fy_minus_1": 1000.0,
            "operating_income_fy_minus_3": 81.0,
            "operating_income_fy_minus_2": 90.0,
            "operating_income_fy_minus_1": 100.0,
            "depreciation_fy_minus_3": 24.3,
            "depreciation_fy_minus_2": 27.0,
            "depreciation_fy_minus_1": 30.0,
            "capex_fy_minus_3": 16.2,
            "capex_fy_minus_2": 18.0,
            "capex_fy_minus_1": 20.0,
            "nwc_fy_minus_3": 81.0,
            "nwc_fy_minus_2": 90.0,
            "nwc_fy_minus_1": 100.0,
        }

    def test_historical_trends_and_dcf_defaults(self):
        trends = calculate_historical_trends(self.historical_target)
        self.assertAlmostEqual(trends["average_growth"], 11.1111111111, places=6)
        self.assertAlmostEqual(trends["average_margin"], 10.0, places=6)
        self.assertAlmostEqual(trends["average_depreciation_ratio"], 3.0, places=6)
        self.assertAlmostEqual(trends["average_capex_ratio"], 2.0, places=6)
        self.assertAlmostEqual(trends["average_nwc_ratio"], 10.0, places=6)

        defaults = derive_dcf_defaults_from_history(self.historical_target)
        self.assertEqual(defaults["base_revenue"], 1000.0)
        self.assertAlmostEqual(defaults["base_nwc_ratio_pct"], 10.0, places=6)

        result = calculate_dcf_valuation(
            base_revenue=defaults["base_revenue"],
            cash=self.cash,
            debt=self.debt,
            shares_outstanding=self.shares_outstanding,
            wacc_pct=5.5,
            perpetual_growth_pct=1.0,
            tax_rate_pct=30.0,
            growth_rates_pct=[0.0, 0.0, 0.0, 0.0, 0.0],
            ebit_margin_pct=[20.0, 20.0, 20.0, 20.0, 20.0],
            capex=[20.0, 20.0, 20.0, 20.0, 20.0],
            depreciation=[50.0, 50.0, 50.0, 50.0, 50.0],
            nwc_inputs=[10.0, 10.0, 10.0, 10.0, 10.0],
            nwc_mode="amount",
        )
        self.assertEqual(result["rows"][0]["fcf_rounded"], 160)
        self.assertEqual(result["rounded"]["theoretical_price"], 35)

    def test_wacc_calculation(self):
        wacc = calculate_wacc(
            cost_of_debt_pct=4.0,
            risk_free_rate_pct=2.0,
            beta=1.0,
            equity_risk_premium_pct=6.0,
            target_de_ratio=1.0,
            tax_rate_pct=25.0,
        )
        self.assertEqual(wacc, 5.5)

    def test_dcf_valuation_rounds_to_yen(self):
        result = calculate_dcf_valuation(
            base_revenue=self.base_revenue,
            cash=self.cash,
            debt=self.debt,
            shares_outstanding=self.shares_outstanding,
            wacc_pct=5.5,
            perpetual_growth_pct=1.0,
            tax_rate_pct=30.0,
            growth_rates_pct=[0.0, 0.0, 0.0, 0.0, 0.0],
            ebit_margin_pct=[20.0, 20.0, 20.0, 20.0, 20.0],
            capex=[20.0, 20.0, 20.0, 20.0, 20.0],
            depreciation=[50.0, 50.0, 50.0, 50.0, 50.0],
            nwc_inputs=[10.0, 10.0, 10.0, 10.0, 10.0],
            nwc_mode="amount",
        )

        self.assertEqual(len(result["rows"]), 5)
        self.assertEqual(result["rows"][0]["fcf_rounded"], 160)
        self.assertEqual(result["rows"][4]["fcf_rounded"], 160)
        self.assertEqual(result["rounded"]["terminal_value"], 3591)
        self.assertEqual(result["rounded"]["terminal_value_pv"], 2748)
        self.assertEqual(result["rounded"]["enterprise_value"], 3431)
        self.assertEqual(result["rounded"]["equity_value"], 3531)
        self.assertEqual(result["rounded"]["theoretical_price"], 35)

    def test_dcf_wacc_must_exceed_growth(self):
        with self.assertRaises(ValueError):
            calculate_dcf_valuation(
                base_revenue=self.base_revenue,
                cash=self.cash,
                debt=self.debt,
                shares_outstanding=self.shares_outstanding,
                wacc_pct=1.0,
                perpetual_growth_pct=1.0,
                tax_rate_pct=30.0,
                growth_rates_pct=[0.0, 0.0, 0.0, 0.0, 0.0],
                ebit_margin_pct=[20.0, 20.0, 20.0, 20.0, 20.0],
                capex=[20.0, 20.0, 20.0, 20.0, 20.0],
                depreciation=[50.0, 50.0, 50.0, 50.0, 50.0],
                nwc_inputs=[10.0, 10.0, 10.0, 10.0, 10.0],
                nwc_mode="amount",
            )

    def test_nwc_from_days(self):
        # Use base revenue divisible by 365 to make day-based math exact
        base_revenue = 36500.0
        result = calculate_dcf_valuation(
            base_revenue=base_revenue,
            cash=0.0,
            debt=0.0,
            shares_outstanding=100.0,
            wacc_pct=5.5,
            perpetual_growth_pct=1.0,
            tax_rate_pct=30.0,
            growth_rates_pct=[0.0, 0.0, 0.0, 0.0, 0.0],
            ebit_margin_pct=[10.0, 10.0, 10.0, 10.0, 10.0],
            capex=[0.0, 0.0, 0.0, 0.0, 0.0],
            depreciation=[0.0, 0.0, 0.0, 0.0, 0.0],
            nwc_inputs=[0.0, 0.0, 0.0, 0.0, 0.0],
            nwc_mode="days",
            base_nwc_ratio_pct=0.0,
            cogs_pct=[50.0, 50.0, 50.0, 50.0, 50.0],
            dso_days=[45.0, 45.0, 45.0, 45.0, 45.0],
            dih_days=[60.0, 60.0, 60.0, 60.0, 60.0],
            dpo_days=[35.0, 35.0, 35.0, 35.0, 35.0],
        )

        first = result["rows"][0]
        # revenue = 36500; receivables = revenue * 45/365 = 4500
        self.assertEqual(first["receivables"], 4500.0)
        # cogs = revenue * 50% = 18250; inventory = cogs * 60/365 = 3000
        self.assertEqual(first["inventory"], 3000.0)
        # payables = cogs * 35/365 = 1750
        self.assertEqual(first["payables"], 1750.0)
        # nwc_current = receivables + inventory - payables = 5750
        self.assertEqual(first["nwc_current"], 5750.0)
        # nwc_change (previous 0) = 5750
        self.assertEqual(first["nwc_change"], 5750.0)


if __name__ == "__main__":
    unittest.main()
