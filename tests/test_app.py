import unittest

from app import calculate_dcf_valuation, calculate_metrics, compute_valuation_range


class GlobalValuationTests(unittest.TestCase):
    def setUp(self):
        self.target = {
            "market_cap": 50000.0,
            "net_income": 500.0,
            "net_assets": 6000.0,
            "operating_income": 700.0,
            "depreciation": 300.0,
            "sub_debt": 2000.0,
            "cash": 1500.0,
            "sales": 0.0,
        }

        self.peers = []
        for index in range(1, 6):
            self.peers.append(
                {
                    "market_cap": 10000.0 * index,
                    "net_income": 500.0 * index,
                    "net_assets": 5000.0 * index,
                    "operating_income": 800.0 * index,
                    "depreciation": 200.0 * index,
                    "sub_debt": 2000.0 * index,
                    "cash": 2000.0 * index,
                    "sales": 1000.0 * index,
                }
            )

    def test_calculate_metrics_success(self):
        metrics = calculate_metrics(self.peers[0])
        self.assertEqual(metrics["per"], 20.0)
        self.assertEqual(metrics["pbr"], 2.0)
        self.assertEqual(metrics["ev_ebitda"], 10.0)
        self.assertEqual(metrics["ev_ebit"], 12.5)

    def test_compute_valuation_range_exact(self):
        ranges = compute_valuation_range(self.target, self.peers)

        self.assertIn("per", ranges)
        self.assertIn("pbr", ranges)
        self.assertIn("ev_ebitda", ranges)
        self.assertIn("ev_ebit", ranges)

        self.assertAlmostEqual(ranges["per"]["min"], 10000.0)
        self.assertAlmostEqual(ranges["per"]["max"], 10000.0)
        self.assertAlmostEqual(ranges["per"]["avg"], 10000.0)

        self.assertAlmostEqual(ranges["pbr"]["avg"], 12000.0)
        self.assertAlmostEqual(ranges["ev_ebitda"]["avg"], 9500.0)
        self.assertAlmostEqual(ranges["ev_ebit"]["avg"], 8250.0)

    def test_zero_division_handling_in_metrics(self):
        bad_peer = {
            "market_cap": 1000.0,
            "net_income": 0.0,
            "net_assets": 0.0,
            "operating_income": 0.0,
            "depreciation": 0.0,
            "sub_debt": 0.0,
            "cash": 0.0,
            "sales": 0.0,
        }
        metrics = calculate_metrics(bad_peer)
        self.assertIsNone(metrics["per"])
        self.assertIsNone(metrics["pbr"])
        self.assertIsNone(metrics["ev_sales"])
        self.assertIsNone(metrics["ev_ebitda"])
        self.assertIsNone(metrics["ev_ebit"])

    def test_negative_values_are_rejected(self):
        bad_company = {
            "market_cap": 1000.0,
            "net_income": -1.0,
            "net_assets": 10.0,
            "operating_income": 10.0,
            "depreciation": 10.0,
            "sub_debt": 0.0,
            "cash": 0.0,
            "sales": 0.0,
        }
        with self.assertRaises(ValueError):
            calculate_metrics(bad_company)

    def test_dcf_valuation_success(self):
        result = calculate_dcf_valuation(
            self.target,
            forecast_years=5,
            growth_rate_pct=5.0,
            discount_rate_pct=7.0,
            terminal_growth_rate_pct=1.0,
        )

        base_fcf = 1000.0
        growth = 0.05
        discount = 0.07
        terminal_growth = 0.01

        expected_forecast = []
        for year in range(1, 6):
            fcf = base_fcf * ((1 + growth) ** year)
            pv = fcf / ((1 + discount) ** year)
            expected_forecast.append((fcf, pv))

        expected_pv_fcf_total = sum(pv for _, pv in expected_forecast)
        terminal_fcf = base_fcf * ((1 + growth) ** 5)
        terminal_value = terminal_fcf * (1 + terminal_growth) / (discount - terminal_growth)
        expected_pv_terminal_value = terminal_value / ((1 + discount) ** 5)
        expected_enterprise_value = expected_pv_fcf_total + expected_pv_terminal_value
        expected_equity_value = expected_enterprise_value + self.target["cash"] - self.target["sub_debt"]

        self.assertEqual(result["forecast_years"], 5)
        self.assertAlmostEqual(result["base_fcf"], base_fcf)
        self.assertAlmostEqual(result["pv_fcf_total"], expected_pv_fcf_total)
        self.assertAlmostEqual(result["terminal_value"], terminal_value)
        self.assertAlmostEqual(result["pv_terminal_value"], expected_pv_terminal_value)
        self.assertAlmostEqual(result["enterprise_value"], expected_enterprise_value)
        self.assertAlmostEqual(result["equity_value"], expected_equity_value)

        self.assertEqual(len(result["forecast_rows"]), 5)
        self.assertAlmostEqual(result["forecast_rows"][0]["fcf"], expected_forecast[0][0])
        self.assertAlmostEqual(result["forecast_rows"][-1]["present_value"], expected_forecast[-1][1])

    def test_dcf_invalid_discount_rate(self):
        with self.assertRaises(ValueError):
            calculate_dcf_valuation(
                self.target,
                forecast_years=5,
                growth_rate_pct=2.0,
                discount_rate_pct=1.0,
                terminal_growth_rate_pct=1.0,
            )

    def test_dcf_negative_values_are_rejected(self):
        bad_target = dict(self.target)
        bad_target["operating_income"] = -1.0
        with self.assertRaises(ValueError):
            calculate_dcf_valuation(
                bad_target,
                forecast_years=5,
                growth_rate_pct=2.0,
                discount_rate_pct=7.0,
                terminal_growth_rate_pct=1.0,
            )


if __name__ == "__main__":
    unittest.main()