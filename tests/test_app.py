import unittest

from app import calculate_average_per, calculate_per, estimate_company_value


class ValuationCalculationTests(unittest.TestCase):
    def test_estimate_company_value_uses_average_per(self):
        peer_companies = [
            {"market_cap": 1200.0, "net_income": 100.0},
            {"market_cap": 1800.0, "net_income": 150.0},
            {"market_cap": 2400.0, "net_income": 200.0},
        ]

        result = estimate_company_value(110.0, peer_companies)

        self.assertEqual([12.0, 12.0, 12.0], result["peer_pers"])
        self.assertEqual(12.0, result["average_per"])
        self.assertEqual(1320.0, result["estimated_company_value"])

    def test_calculate_average_per_requires_three_companies(self):
        with self.assertRaises(ValueError):
            calculate_average_per(
                [{"market_cap": 1000.0, "net_income": 100.0}],
            )

    def test_calculate_per_rejects_zero_net_income(self):
        with self.assertRaises(ZeroDivisionError):
            calculate_per(1000.0, 0.0)


if __name__ == "__main__":
    unittest.main()
