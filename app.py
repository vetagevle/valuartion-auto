"""Professional Comps and DCF valuation Streamlit app.

This module contains:
- pure calculation functions for Comps and DCF
- CSV/XLSX import helpers
- a Streamlit UI with a Comps tab and a DCF tab

The UI uses 百万円 units for user input and display, while the internal
DCF calculations operate in yen to keep the math precise.
"""

from __future__ import annotations

import csv
import io
import statistics
from typing import Any, Dict, List, Optional, Tuple

st: Any
try:
    import streamlit as _st
except Exception:
    st = None
else:
    st = _st

PERIODS = ["LTM", "CY+1", "CY+2"]


def _load_pandas():
    try:
        import pandas as pd

        return pd
    except Exception:
        return None


def _display_table(
    data: Any,
    *,
    index_col: Optional[str] = None,
    numeric_cols: Optional[List[str]] = None,
    money_cols: Optional[List[str]] = None,
    percent_cols: Optional[List[str]] = None,
) -> None:
    """Display a table with pandas Styler formatting when available."""
    pd = _load_pandas()
    if pd is None:
        if hasattr(data, "to_dict"):
            st.dataframe(data.to_dict("records"), use_container_width=True, hide_index=True)
        else:
            st.dataframe(data, use_container_width=True, hide_index=True)
        return

    df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    if index_col and index_col in df.columns:
        df = df.set_index(index_col)

    formatters: Dict[str, Any] = {}
    right_align_cols: List[str] = []

    if numeric_cols:
        for col in numeric_cols:
            if col in df.columns:
                formatters[col] = lambda x: "" if x is None else f"{float(x):.2f}"
                right_align_cols.append(col)

    if money_cols:
        for col in money_cols:
            if col in df.columns:
                formatters[col] = lambda x: "" if x is None else f"{float(x):,.2f}"
                right_align_cols.append(col)

    if percent_cols:
        for col in percent_cols:
            if col in df.columns:
                formatters[col] = lambda x: "" if x is None else f"{float(x):.2f}%"
                right_align_cols.append(col)

    styler = df.style
    if formatters:
        styler = styler.format(formatters)
    if right_align_cols:
        styler = styler.set_properties(**{"text-align": "right"}, subset=right_align_cols)
    styler = styler.set_table_styles([{"selector": "th", "props": [("font-weight", "bold")]}])
    st.dataframe(styler, use_container_width=True, hide_index=True)


def _round_yen(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    return int(round(value))


def _to_million(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value / 1_000_000.0


def calculate_market_cap(share_price: float, shares_outstanding: float) -> float:
    """Calculate equity value from share price and shares outstanding."""
    validate_non_negative("株価", float(share_price))
    validate_non_negative("発行済株式数", float(shares_outstanding))
    return float(share_price) * float(shares_outstanding)


def calculate_enterprise_value(market_cap: float, cash: float, debt: float, minority: float) -> float:
    """Calculate enterprise value from equity value and net debt components."""
    for label, value in [
        ("時価総額", market_cap),
        ("現預金", cash),
        ("有利子負債", debt),
        ("少数株主持分", minority),
    ]:
        validate_non_negative(label, float(value))
    return float(market_cap) + float(debt) + float(minority) - float(cash)


def _build_target_profile_snapshot(target: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize the TargetCo profile and derive market cap / EV fields."""
    profile = dict(target)
    company_name = str(profile.get("company_name", "TargetCo"))
    ticker = str(profile.get("ticker", "TGT"))
    business_description = str(profile.get("business_description", ""))
    share_price = float(profile.get("share_price", 0.0))
    shares_outstanding = float(profile.get("shares_outstanding", 0.0))
    cash = float(profile.get("cash", 0.0))
    sub_debt = float(profile.get("sub_debt", 0.0))
    minority = float(profile.get("minority", 0.0))
    receivables = float(profile.get("receivables", 0.0))
    inventory = float(profile.get("inventory", 0.0))
    payables = float(profile.get("payables", 0.0))
    existing_market_cap = float(profile.get("market_cap", 0.0))
    market_cap = calculate_market_cap(share_price, shares_outstanding) if share_price > 0 and shares_outstanding > 0 else existing_market_cap
    enterprise_value = calculate_enterprise_value(market_cap, cash, sub_debt, minority)
    operating_nwc = receivables + inventory - payables

    profile.update(
        {
            "company_name": company_name,
            "ticker": ticker,
            "business_description": business_description,
            "share_price": share_price,
            "shares_outstanding": shares_outstanding,
            "cash": cash,
            "sub_debt": sub_debt,
            "minority": minority,
            "receivables": receivables,
            "inventory": inventory,
            "payables": payables,
            "market_cap": market_cap,
            "equity_value": market_cap,
            "enterprise_value": enterprise_value,
            "net_debt": sub_debt - cash,
            "operating_nwc": operating_nwc,
        }
    )
    return profile


def _inject_excel_ui_styles() -> None:
    """Apply a light Excel-like visual system to the app."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 100%;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid rgba(49, 51, 63, 0.14);
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.82rem;
            color: #6b7280;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.5rem;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _percent_to_rate(value: float) -> float:
    return value / 100.0


def _rate_to_percent(value: float) -> float:
    return value * 100.0


def forecast_compounded_series(base_value: float, growth_rates_pct: List[float]) -> List[float]:
    """Build a compounded forecast series from the previous year's forecast value."""
    forecasts: List[float] = []
    previous_value = float(base_value)
    for growth_rate_pct in growth_rates_pct:
        next_value = previous_value * (1.0 + _percent_to_rate(float(growth_rate_pct)))
        forecasts.append(next_value)
        previous_value = next_value
    return forecasts


def _scale_company_to_yen(company: Dict[str, Any]) -> Dict[str, Any]:
    """Scale monetary fields from 百万円 to 円 for internal calculations."""
    money_fields = {
        "market_cap",
        "cash",
        "sub_debt",
        "minority",
        "sales_ltm",
        "sales_cy1",
        "sales_cy2",
        "ebitda_ltm",
        "ebitda_cy1",
        "ebitda_cy2",
        "ebit_ltm",
        "ebit_cy1",
        "ebit_cy2",
        "net_income_ltm",
        "net_income_cy1",
        "net_income_cy2",
        "sales",
        "net_income",
        "net_assets",
        "operating_income",
        "depreciation",
    }
    scaled: Dict[str, Any] = {}
    for key, value in company.items():
        if key in money_fields:
            try:
                scaled[key] = float(value) * 1_000_000.0
            except Exception:
                scaled[key] = 0.0
        else:
            scaled[key] = value
    return scaled


def _scale_companies_list_to_yen(companies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_scale_company_to_yen(company) for company in companies]


HISTORICAL_PERIODS = ["FY-3", "FY-2", "FY-1"]


def calculate_historical_trends(target: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate historical 3-year trends from target FY-3/FY-2/FY-1 inputs.

    Returns growth rates, margins, and averages to support DCF assumptions.
    """
    revenues = [float(target.get(f"sales_fy_minus_{i}", 0.0)) for i in [3, 2, 1]]
    operating_profits = [float(target.get(f"operating_income_fy_minus_{i}", 0.0)) for i in [3, 2, 1]]
    depreciation = [float(target.get(f"depreciation_fy_minus_{i}", 0.0)) for i in [3, 2, 1]]
    capex = [float(target.get(f"capex_fy_minus_{i}", 0.0)) for i in [3, 2, 1]]
    nwc = [float(target.get(f"nwc_fy_minus_{i}", 0.0)) for i in [3, 2, 1]]

    growth_rates: List[Optional[float]] = [None, None, None]
    if revenues[0] > 0 and revenues[1] > 0:
        growth_rates[1] = (revenues[1] / revenues[0] - 1.0) * 100.0
    if revenues[1] > 0 and revenues[2] > 0:
        growth_rates[2] = (revenues[2] / revenues[1] - 1.0) * 100.0

    operating_margins = [((op / rev) * 100.0 if rev > 0 else None) for op, rev in zip(operating_profits, revenues)]
    dep_ratios = [((dep / rev) * 100.0 if rev > 0 else None) for dep, rev in zip(depreciation, revenues)]
    capex_ratios = [((cap / rev) * 100.0 if rev > 0 else None) for cap, rev in zip(capex, revenues)]
    nwc_ratios = [((n / rev) * 100.0 if rev > 0 else None) for n, rev in zip(nwc, revenues)]

    valid_growth = [value for value in growth_rates if value is not None]
    valid_margin = [value for value in operating_margins if value is not None]
    valid_dep = [value for value in dep_ratios if value is not None]
    valid_capex = [value for value in capex_ratios if value is not None]
    valid_nwc = [value for value in nwc_ratios if value is not None]

    return {
        "revenues": revenues,
        "operating_profits": operating_profits,
        "depreciation": depreciation,
        "capex": capex,
        "nwc": nwc,
        "growth_rates": growth_rates,
        "operating_margins": operating_margins,
        "depreciation_ratios": dep_ratios,
        "capex_ratios": capex_ratios,
        "nwc_ratios": nwc_ratios,
        "average_growth": (statistics.mean(valid_growth) if valid_growth else None),
        "average_margin": (statistics.mean(valid_margin) if valid_margin else None),
        "average_depreciation_ratio": (statistics.mean(valid_dep) if valid_dep else None),
        "average_capex_ratio": (statistics.mean(valid_capex) if valid_capex else None),
        "average_nwc_ratio": (statistics.mean(valid_nwc) if valid_nwc else None),
    }


def build_historical_summary_lines(trends: Dict[str, Any]) -> Dict[str, str]:
    """Build concise Japanese summary strings for UI captions."""
    growth_labels = []
    for idx, period in enumerate(HISTORICAL_PERIODS):
        value = trends["growth_rates"][idx]
        growth_labels.append(f"{period}: {value:.1f}%" if value is not None else f"{period}: -")

    margin_labels = []
    for idx, period in enumerate(HISTORICAL_PERIODS):
        value = trends["operating_margins"][idx]
        margin_labels.append(f"{period}: {value:.1f}%" if value is not None else f"{period}: -")

    return {
        "growth": f"過去実績：{' | '.join(growth_labels)}（直近3年平均: {trends['average_growth']:.1f}%）" if trends.get("average_growth") is not None else f"過去実績：{' | '.join(growth_labels)}（直近3年平均: -）",
        "margin": f"過去実績：{' | '.join(margin_labels)}（直近3年平均: {trends['average_margin']:.1f}%）" if trends.get("average_margin") is not None else f"過去実績：{' | '.join(margin_labels)}（直近3年平均: -）",
    }


def format_history_line(label: str, values: List[Optional[float]], average: Optional[float], suffix: str = "%") -> str:
    parts = []
    for period, value in zip(HISTORICAL_PERIODS, values):
        parts.append(f"{period}: {value:.1f}{suffix}" if value is not None else f"{period}: -")
    avg_text = f"{average:.1f}{suffix}" if average is not None else "-"
    return f"{label}：{' | '.join(parts)}（直近3年平均: {avg_text}）"


def derive_dcf_defaults_from_history(target: Dict[str, Any]) -> Dict[str, Any]:
    """Derive DCF defaults from the target's FY-1 actuals."""
    trends = calculate_historical_trends(target)
    fy1_revenue = float(target.get("sales_fy_minus_1", 0.0))
    # Adjust historical NWC to exclude financial items: remove cash and add back interest-bearing debt
    # operating_nwc = (current_assets - cash) - (current_liabilities - interest_bearing_debt)
    fy1_nwc = float(target.get("nwc_fy_minus_1", 0.0))
    fy1_cash = float(target.get("cash", 0.0))
    fy1_sub_debt = float(target.get("sub_debt", 0.0))
    adjusted_nwc = fy1_nwc - fy1_cash + fy1_sub_debt
    base_nwc_ratio_pct = (adjusted_nwc / fy1_revenue * 100.0) if fy1_revenue > 0 else 0.0

    return {
        "base_revenue": fy1_revenue,
        "base_nwc_ratio_pct": base_nwc_ratio_pct,
        "average_growth": trends.get("average_growth"),
        "average_margin": trends.get("average_margin"),
        "average_capex_ratio": trends.get("average_capex_ratio"),
        "average_depreciation_ratio": trends.get("average_depreciation_ratio"),
        "average_nwc_ratio": trends.get("average_nwc_ratio"),
        "trends": trends,
    }


def compute_ev(company: Dict[str, float]) -> float:
    """Compute EV = market_cap + sub_debt + minority - cash."""
    market_cap = float(company.get("market_cap", 0.0))
    sub_debt = float(company.get("sub_debt", 0.0))
    minority = float(company.get("minority", 0.0))
    cash = float(company.get("cash", 0.0))
    return calculate_enterprise_value(market_cap, cash, sub_debt, minority)


def safe_div(n: float, d: float) -> Optional[float]:
    try:
        if d <= 0:
            return None
        return n / d
    except Exception:
        return None


def validate_non_negative(label: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{label}は0以上の値を入力してください。")


def calculate_metrics(company: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Compatibility helper: compute simplified multiples for a single company dict."""
    for label, value in [
        ("時価総額", company.get("market_cap", 0.0)),
        ("純利益", company.get("net_income", 0.0)),
        ("純資産", company.get("net_assets", 0.0)),
        ("営業利益", company.get("operating_income", 0.0)),
        ("減価償却費", company.get("depreciation", 0.0)),
        ("有利子負債", company.get("sub_debt", 0.0)),
        ("現預金", company.get("cash", 0.0)),
    ]:
        validate_non_negative(label, float(value))

    market_cap = float(company.get("market_cap", 0.0))
    sales = float(company.get("sales", 0.0))
    net_income = float(company.get("net_income", 0.0))
    net_assets = float(company.get("net_assets", 0.0))
    operating_income = float(company.get("operating_income", 0.0))
    depreciation = float(company.get("depreciation", 0.0))
    sub_debt = float(company.get("sub_debt", 0.0))
    cash = float(company.get("cash", 0.0))

    enterprise_value = market_cap + sub_debt - cash
    ebitda = operating_income + depreciation

    return {
        "per": market_cap / net_income if net_income > 0 else None,
        "pbr": market_cap / net_assets if net_assets > 0 else None,
        "ev_sales": enterprise_value / sales if sales > 0 else None,
        "ev_ebitda": enterprise_value / ebitda if ebitda > 0 else None,
        "ev_ebit": enterprise_value / operating_income if operating_income > 0 else None,
    }


def compute_multiples_for_company(company: Dict[str, Any]) -> Dict[str, Dict[str, Optional[float]]]:
    """Return multiples per period for EV/Sales, EV/EBITDA, EV/EBIT, and P/E."""
    ev = compute_ev(company)
    sales = {
        "LTM": float(company.get("sales_ltm", 0.0)),
        "CY+1": float(company.get("sales_cy1", 0.0)),
        "CY+2": float(company.get("sales_cy2", 0.0)),
    }
    ebitda = {
        "LTM": float(company.get("ebitda_ltm", 0.0)),
        "CY+1": float(company.get("ebitda_cy1", 0.0)),
        "CY+2": float(company.get("ebitda_cy2", 0.0)),
    }
    ebit = {
        "LTM": float(company.get("ebit_ltm", 0.0)),
        "CY+1": float(company.get("ebit_cy1", 0.0)),
        "CY+2": float(company.get("ebit_cy2", 0.0)),
    }
    net_income = {
        "LTM": float(company.get("net_income_ltm", 0.0)),
        "CY+1": float(company.get("net_income_cy1", 0.0)),
        "CY+2": float(company.get("net_income_cy2", 0.0)),
    }

    multiples: Dict[str, Dict[str, Optional[float]]] = {
        "ev_sales": {},
        "ev_ebitda": {},
        "ev_ebit": {},
        "pe": {},
    }

    for period in PERIODS:
        # Exclude non-positive denominators explicitly to avoid misleading multiples
        multiples["ev_sales"][period] = ev / sales[period] if sales[period] > 0 else None
        multiples["ev_ebitda"][period] = ev / ebitda[period] if ebitda[period] > 0 else None
        multiples["ev_ebit"][period] = ev / ebit[period] if ebit[period] > 0 else None
        multiples["pe"][period] = float(company.get("market_cap", 0.0)) / net_income[period] if net_income[period] > 0 else None

    return multiples


def _apply_multiple(multiple: float, target: Dict[str, float], method: str) -> float:
    target_net_debt = float(target.get("sub_debt", 0.0)) - float(target.get("cash", 0.0))

    if method == "per":
        value = multiple * float(target.get("net_income", 0.0))
    elif method == "pbr":
        value = multiple * float(target.get("net_assets", 0.0))
    elif method == "ev_sales":
        value = multiple * float(target.get("sales", 0.0)) - target_net_debt
    elif method == "ev_ebitda":
        target_ebitda = float(target.get("operating_income", 0.0)) + float(target.get("depreciation", 0.0))
        value = multiple * target_ebitda - target_net_debt
    elif method == "ev_ebit":
        value = multiple * float(target.get("operating_income", 0.0)) - target_net_debt
    else:
        raise ValueError(f"未知の手法です: {method}")

    return max(0.0, value)


def aggregate_peer_stats(peers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Aggregate min/max/avg/median of each multiple across peers."""
    collected: Dict[str, Dict[str, List[float]]] = {
        "ev_sales": {p: [] for p in PERIODS},
        "ev_ebitda": {p: [] for p in PERIODS},
        "ev_ebit": {p: [] for p in PERIODS},
        "pe": {p: [] for p in PERIODS},
    }

    for peer in peers:
        multiples = compute_multiples_for_company(peer)
        for metric in collected:
            for period in PERIODS:
                value = multiples.get(metric, {}).get(period)
                # Only collect strictly positive multiples (exclude None, zero or negative)
                if value is not None and value > 0:
                    collected[metric][period].append(value)

    stats: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for metric, per_dict in collected.items():
        stats[metric] = {}
        for period, values in per_dict.items():
            if not values:
                stats[metric][period] = {"min": None, "max": None, "avg": None, "median": None}
            else:
                stats[metric][period] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": statistics.mean(values),
                    "median": statistics.median(values),
                }
    return stats


def compute_valuation_range(target: Dict[str, float], peers: List[Dict[str, float]]) -> Dict[str, Dict[str, Any]]:
    """Apply peer multiples to the target company and summarize each method."""
    validate_non_negative("時価総額", float(target.get("market_cap", 0.0)))
    for peer in peers:
        validate_non_negative("時価総額(peer)", float(peer.get("market_cap", 0.0)))

    peer_metrics = [calculate_metrics(peer) for peer in peers]
    methods = ["per", "pbr", "ev_sales", "ev_ebitda", "ev_ebit"]
    ranges: Dict[str, Dict[str, Any]] = {}

    for method in methods:
        multiples = [metrics[method] for metrics in peer_metrics if metrics.get(method) is not None]
        if not multiples:
            continue

        values = [_apply_multiple(float(multiple), target, method) for multiple in multiples]
        ranges[method] = {
            "values": values,
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    return ranges


def apply_multiples_to_target(
    target: Dict[str, Any],
    stats: Dict[str, Dict[str, Dict[str, Optional[float]]]],
    method: str = "median",
) -> Dict[str, Any]:
    """Apply chosen multiple statistic to compute implied EV, equity and price for the target."""
    result: Dict[str, Any] = {"by_metric": {}}
    for metric in ["ev_sales", "ev_ebitda", "ev_ebit", "pe"]:
        result["by_metric"][metric] = {}
        for period in PERIODS:
            if method == "average":
                chosen = stats.get(metric, {}).get(period, {}).get("avg")
            else:
                chosen = stats.get(metric, {}).get(period, {}).get(method)

            if chosen is None:
                result["by_metric"][metric][period] = {
                    "multiple": None,
                    "denom": None,
                    "implied_ev": None,
                    "implied_equity": None,
                    "implied_price": None,
                }
                continue

            if metric == "ev_sales":
                denom = float(target.get({"LTM": "sales_ltm", "CY+1": "sales_cy1", "CY+2": "sales_cy2"}[period], 0.0))
            elif metric == "ev_ebitda":
                denom = float(target.get({"LTM": "ebitda_ltm", "CY+1": "ebitda_cy1", "CY+2": "ebitda_cy2"}[period], 0.0))
            elif metric == "ev_ebit":
                denom = float(target.get({"LTM": "ebit_ltm", "CY+1": "ebit_cy1", "CY+2": "ebit_cy2"}[period], 0.0))
            else:
                denom = float(target.get({"LTM": "net_income_ltm", "CY+1": "net_income_cy1", "CY+2": "net_income_cy2"}[period], 0.0))

            if denom <= 0:
                implied_ev = None
                implied_equity = None
                implied_price = None
            else:
                implied_ev = float(chosen) * denom
                implied_equity = implied_ev - float(target.get("sub_debt", 0.0)) - float(target.get("minority", 0.0)) + float(target.get("cash", 0.0))
                shares = float(target.get("shares_outstanding", 0.0))
                implied_price = None if shares <= 0 else implied_equity / shares

            result["by_metric"][metric][period] = {
                "multiple": chosen,
                "denom": denom,
                "implied_ev": implied_ev,
                "implied_equity": implied_equity,
                "implied_price": implied_price,
            }

    return result


def parse_csv_upload(uploaded_file: io.BytesIO) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Parse the expected CSV template."""
    text = uploaded_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = [row for row in reader]
    if not rows:
        raise ValueError("CSVに有効な行が含まれていません。")

    def _normalize_row(row: Dict[str, str]) -> Dict[str, Any]:
        def f(key: str) -> float:
            value = row.get(key, "")
            try:
                return float(value) if value != "" else 0.0
            except Exception:
                return 0.0

        return {
            "company_name": row.get("company_name", ""),
            "market_cap": f("market_cap"),
            "shares_outstanding": f("shares_outstanding"),
            "cash": f("cash"),
            "sub_debt": f("sub_debt"),
            "minority": f("minority"),
            "sales_ltm": f("sales_ltm"),
            "sales_cy1": f("sales_cy1"),
            "sales_cy2": f("sales_cy2"),
            "ebitda_ltm": f("ebitda_ltm"),
            "ebitda_cy1": f("ebitda_cy1"),
            "ebitda_cy2": f("ebitda_cy2"),
            "ebit_ltm": f("ebit_ltm"),
            "ebit_cy1": f("ebit_cy1"),
            "ebit_cy2": f("ebit_cy2"),
            "net_income_ltm": f("net_income_ltm"),
            "net_income_cy1": f("net_income_cy1"),
            "net_income_cy2": f("net_income_cy2"),
        }

    normalized = [_normalize_row(row) for row in rows]
    return normalized[0], normalized[1:16]


def parse_excel_upload(uploaded_file: io.BytesIO) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Parse an Excel workbook with the same headers as the CSV template."""
    try:
        import openpyxl
    except Exception as exc:
        raise ImportError("Excel読み込みには openpyxl が必要です。") from exc

    uploaded_file.seek(0)
    wb = openpyxl.load_workbook(uploaded_file, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        raise ValueError("Excelに有効な行が含まれていません。")

    headers = ["" if cell is None else str(cell).strip() for cell in rows[0]]

    dict_rows: List[Dict[str, str]] = []
    for row in rows[1:]:
        current: Dict[str, str] = {}
        for header, cell in zip(headers, row):
            current[header] = "" if cell is None else str(cell)
        dict_rows.append(current)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in dict_rows:
        writer.writerow(row)
    buffer.seek(0)
    return parse_csv_upload(io.BytesIO(buffer.getvalue().encode("utf-8")))


def build_benchmark_table(
    target: Dict[str, Any],
    peers: List[Dict[str, Any]],
    stats: Dict[str, Dict[str, Dict[str, Optional[float]]]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for label, company in [(target.get("company_name", "Target"), target)] + [(peer.get("company_name", f"Comp{i+1}"), peer) for i, peer in enumerate(peers)]:
        multiples = compute_multiples_for_company(company)
        row: Dict[str, Any] = {"企業": label}
        for metric, metric_label in [("ev_sales", "EV/Sales"), ("ev_ebitda", "EV/EBITDA"), ("ev_ebit", "EV/EBIT"), ("pe", "P/E")]:
            for period in PERIODS:
                row[f"{metric_label} {period}"] = multiples.get(metric, {}).get(period)
        rows.append(row)

    for summary_label, summary_key in [("平均", "avg"), ("中央値", "median")]:
        row = {"企業": summary_label}
        for metric, metric_label in [("ev_sales", "EV/Sales"), ("ev_ebitda", "EV/EBITDA"), ("ev_ebit", "EV/EBIT"), ("pe", "P/E")]:
            for period in PERIODS:
                row[f"{metric_label} {period}"] = stats.get(metric, {}).get(period, {}).get(summary_key)
        rows.append(row)

    return rows


def _render_target_profile_inputs(prefix: str, allow_edit: bool = True) -> Dict[str, Any]:
    """Render or summarize the TargetCo profile used across pages."""
    target: Dict[str, Any] = st.session_state.get("target_data", {}) or {}

    if allow_edit:
        st.subheader("TargetCo 基本情報")
        basic_left, basic_mid, basic_right = st.columns([1.2, 1.0, 1.0])
        with basic_left:
            target["company_name"] = st.text_input("社名", value=str(target.get("company_name", "TargetCo")), key=f"{prefix}_company_name")
            target["ticker"] = st.text_input("Ticker", value=str(target.get("ticker", "TGT")), key=f"{prefix}_ticker")
            target["business_description"] = st.text_area(
                "事業概要（Business Description）",
                value=str(target.get("business_description", "")),
                key=f"{prefix}_business_description",
                height=120,
            )
        with basic_mid:
            target["share_price"] = st.number_input(
                "現在の株価（Share Price, 円）",
                min_value=0.0,
                value=float(target.get("share_price", 0.0)),
                step=1.0,
                format="%.2f",
                key=f"{prefix}_share_price",
            )
            target["shares_outstanding"] = st.number_input(
                "発行済株式総数（Shares Outstanding, 株）",
                min_value=0.0,
                value=float(target.get("shares_outstanding", 1.0)),
                step=1.0,
                format="%.2f",
                key=f"{prefix}_shares_outstanding",
            )
            target["cash"] = st.number_input(
                "現預金（Cash & Cash Equivalents, 百万円）",
                min_value=0.0,
                value=float(target.get("cash", 0.0)),
                step=1.0,
                key=f"{prefix}_cash",
            )
        with basic_right:
            target["sub_debt"] = st.number_input(
                "有利子負債（Total Debt, 百万円）",
                min_value=0.0,
                value=float(target.get("sub_debt", 0.0)),
                step=1.0,
                key=f"{prefix}_sub_debt",
            )
            target["minority"] = st.number_input(
                "少数株主持分（Minority Interest, 百万円）",
                min_value=0.0,
                value=float(target.get("minority", 0.0)),
                step=1.0,
                key=f"{prefix}_minority",
            )
            target["sector"] = st.text_input("業種", value=str(target.get("sector", "")), key=f"{prefix}_sector")

        st.markdown("**財務（LTM / CY+1 / CY+2）**")
        for period in PERIODS:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                target[f"sales_{period.replace('+', 'plus').lower()}"] = st.number_input(
                    f"売上高 {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"sales_{period.replace('+', 'plus').lower()}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_sales_{period}",
                )
            with c2:
                target[f"ebitda_{period.replace('+', 'plus').lower()}"] = st.number_input(
                    f"EBITDA {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"ebitda_{period.replace('+', 'plus').lower()}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_ebitda_{period}",
                )
            with c3:
                target[f"ebit_{period.replace('+', 'plus').lower()}"] = st.number_input(
                    f"EBIT {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"ebit_{period.replace('+', 'plus').lower()}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_ebit_{period}",
                )
            with c4:
                target[f"net_income_{period.replace('+', 'plus').lower()}"] = st.number_input(
                    f"純利益 {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"net_income_{period.replace('+', 'plus').lower()}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_net_{period}",
                )

        st.markdown("**過去3年実績（FY-3 / FY-2 / FY-1）**")
        st.caption("DCF のベース年と前提の初期値に利用します。金額は百万円単位です。")
        hist_cols = st.columns(3)
        hist_periods = ["FY-3", "FY-2", "FY-1"]
        for idx, period in enumerate(hist_periods):
            with hist_cols[idx]:
                st.markdown(f"**{period}**")
                target[f"sales_fy_minus_{3 - idx}"] = st.number_input(
                    f"売上高 {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"sales_fy_minus_{3 - idx}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_hist_sales_{period}",
                )
                target[f"operating_income_fy_minus_{3 - idx}"] = st.number_input(
                    f"営業利益 {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"operating_income_fy_minus_{3 - idx}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_hist_op_{period}",
                )
                target[f"depreciation_fy_minus_{3 - idx}"] = st.number_input(
                    f"減価償却費 {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"depreciation_fy_minus_{3 - idx}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_hist_dep_{period}",
                )
                target[f"capex_fy_minus_{3 - idx}"] = st.number_input(
                    f"設備投資額 CapEx {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"capex_fy_minus_{3 - idx}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_hist_capex_{period}",
                )
                target[f"nwc_fy_minus_{3 - idx}"] = st.number_input(
                    f"正味運転資本 NWC {period}（百万円）",
                    min_value=0.0,
                    value=float(target.get(f"nwc_fy_minus_{3 - idx}", 0.0)),
                    step=1.0,
                    key=f"{prefix}_hist_nwc_{period}",
                )

        target = _build_target_profile_snapshot(target)
        st.session_state["target_data"] = target
        st.session_state["target_profile"] = target

    else:
        target = _build_target_profile_snapshot(target)
        if target:
            st.info("TargetCo の基本情報は全体の概要ページで編集してください。ここでは参照のみ行います。")
            summary_cols = st.columns(4)
            with summary_cols[0]:
                st.metric("社名", target.get("company_name", "TargetCo"))
            with summary_cols[1]:
                st.metric("Ticker", target.get("ticker", "-"))
            with summary_cols[2]:
                st.metric("株価", f"{float(target.get('share_price', 0.0)) :,.2f} 円")
            with summary_cols[3]:
                st.metric("時価総額", f"{_to_million(float(target.get('market_cap', 0.0))) :,.2f} 百万円")

    return target


def calculate_wacc(
    cost_of_debt_pct: float,
    risk_free_rate_pct: float,
    beta: float,
    equity_risk_premium_pct: float,
    target_de_ratio: float,
    tax_rate_pct: float,
) -> float:
    for label, value in [
        ("負債コスト", cost_of_debt_pct),
        ("無リスク金利", risk_free_rate_pct),
        ("ベータ", beta),
        ("株式リスクプレミアム", equity_risk_premium_pct),
        ("目標D/E比率", target_de_ratio),
        ("実効税率", tax_rate_pct),
    ]:
        validate_non_negative(label, float(value))

    risk_free_rate = _percent_to_rate(risk_free_rate_pct)
    cost_of_debt = _percent_to_rate(cost_of_debt_pct)
    equity_risk_premium = _percent_to_rate(equity_risk_premium_pct)
    tax_rate = _percent_to_rate(tax_rate_pct)

    cost_of_equity_rate = risk_free_rate + beta * equity_risk_premium
    equity_weight = 1.0 / (1.0 + target_de_ratio)
    debt_weight = target_de_ratio / (1.0 + target_de_ratio)
    after_tax_debt_cost_rate = cost_of_debt * (1.0 - tax_rate)
    wacc_rate = equity_weight * cost_of_equity_rate + debt_weight * after_tax_debt_cost_rate
    return _rate_to_percent(wacc_rate)


def calculate_dcf_valuation(
    base_revenue: float,
    cash: float,
    debt: float,
    shares_outstanding: float,
    wacc_pct: float,
    perpetual_growth_pct: float,
    tax_rate_pct: float,
    growth_rates_pct: List[float],
    ebit_margin_pct: List[float],
    capex: List[float],
    depreciation: List[float],
    nwc_inputs: List[float],
    nwc_mode: str = "ratio",
    base_nwc_ratio_pct: float = 0.0,
    cogs_pct: Optional[List[float]] = None,
    dso_days: Optional[List[float]] = None,
    dih_days: Optional[List[float]] = None,
    dpo_days: Optional[List[float]] = None,
) -> Dict[str, Any]:
    if base_revenue <= 0:
        raise ValueError("直近期売上高は0より大きい値を入力してください。")
    if shares_outstanding <= 0:
        raise ValueError("発行済株式数は0より大きい値を入力してください。")
    if (
        len(growth_rates_pct) != 5
        or len(ebit_margin_pct) != 5
        or len(capex) != 5
        or len(depreciation) != 5
        or len(nwc_inputs) != 5
    ):
        raise ValueError("5年分の前提値をすべて入力してください。")
    if nwc_mode not in {"ratio", "amount", "days"}:
        raise ValueError("NWC入力方式が不正です。")

    for label, value in [("永久成長率", perpetual_growth_pct), ("実効税率", tax_rate_pct), ("WACC", wacc_pct), ("基準NWC比率", base_nwc_ratio_pct)]:
        validate_non_negative(label, float(value))

    wacc_rate = _percent_to_rate(wacc_pct)
    growth_rate = _percent_to_rate(perpetual_growth_pct)
    tax_rate = _percent_to_rate(tax_rate_pct)

    if wacc_rate <= growth_rate:
        raise ValueError("WACCは永久成長率より大きくなければなりません。")

    rows: List[Dict[str, Any]] = []
    previous_revenue = float(base_revenue)
    # For days-based NWC, caller should supply dso/dih/dpo; we initialize previous_nwc to 0 unless ratio mode
    previous_nwc = previous_revenue * (base_nwc_ratio_pct / 100.0) if nwc_mode == "ratio" else 0.0

    # Validate days-based inputs if provided
    if nwc_mode == "days":
        if cogs_pct is None or dso_days is None or dih_days is None or dpo_days is None:
            raise ValueError("NWCの日数前提を指定する場合、cogs_pct, dso_days, dih_days, dpo_days を全て渡してください。")
        if not (len(cogs_pct) == len(dso_days) == len(dih_days) == len(dpo_days) == 5):
            raise ValueError("日数前提は5年分を指定してください。")

    forecast_revenues = forecast_compounded_series(previous_revenue, growth_rates_pct)

    for index in range(5):
        year = index + 1
        revenue = forecast_revenues[index]
        ebit = revenue * (ebit_margin_pct[index] / 100.0)

        # Compute NWC depending on input mode
        if nwc_mode == "ratio":
            current_nwc = revenue * (nwc_inputs[index] / 100.0)
            nwc_change = current_nwc - previous_nwc
            previous_nwc = current_nwc
        elif nwc_mode == "amount":
            current_nwc = None
            nwc_change = nwc_inputs[index]
        elif nwc_mode == "days":
            # COGS is derived from revenue and COGS%
            assert cogs_pct is not None and dso_days is not None and dih_days is not None and dpo_days is not None
            cogs = revenue * (cogs_pct[index] / 100.0)
            receivables = revenue * (dso_days[index] / 365.0)
            inventory = cogs * (dih_days[index] / 365.0)
            payables = cogs * (dpo_days[index] / 365.0)
            current_nwc = receivables + inventory - payables
            nwc_change = current_nwc - previous_nwc
            previous_nwc = current_nwc
        else:
            raise ValueError("不正なNWC入力方式です。")

        fcf = ebit * (1.0 - tax_rate) + depreciation[index] - capex[index] - nwc_change
        discount_factor = 1.0 / ((1.0 + wacc_rate) ** year)
        present_value = fcf * discount_factor

        rows.append(
            {
                "year": year,
                "revenue": revenue,
                "growth_rate_pct": growth_rates_pct[index],
                "ebit_margin_pct": ebit_margin_pct[index],
                "ebit": ebit,
                "depreciation": depreciation[index],
                "capex": capex[index],
                "nwc_input": nwc_inputs[index],
                "nwc_change": nwc_change,
                "fcf": fcf,
                "discount_factor": discount_factor,
                "pv": present_value,
                "revenue_rounded": _round_yen(revenue),
                "ebit_rounded": _round_yen(ebit),
                "fcf_rounded": _round_yen(fcf),
                "pv_rounded": _round_yen(present_value),
                "nwc_current": current_nwc,
                "receivables": receivables if nwc_mode == "days" else None,
                "inventory": inventory if nwc_mode == "days" else None,
                "payables": payables if nwc_mode == "days" else None,
            }
        )
        previous_revenue = revenue

    terminal_fcf = rows[-1]["fcf"]
    terminal_value = terminal_fcf * (1.0 + growth_rate) / (wacc_rate - growth_rate)
    terminal_discount_factor = rows[-1]["discount_factor"]
    terminal_value_pv = terminal_value * terminal_discount_factor

    pv_fcf_sum = sum(row["pv"] for row in rows)
    enterprise_value = pv_fcf_sum + terminal_value_pv
    equity_value = enterprise_value + cash - debt
    theoretical_price = equity_value / shares_outstanding

    return {
        "wacc_pct": wacc_pct,
        "wacc_rate": wacc_rate,
        "rows": rows,
        "terminal_value": terminal_value,
        "terminal_value_pv": terminal_value_pv,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "theoretical_price": theoretical_price,
        "rounded": {
            "terminal_value": _round_yen(terminal_value),
            "terminal_value_pv": _round_yen(terminal_value_pv),
            "enterprise_value": _round_yen(enterprise_value),
            "equity_value": _round_yen(equity_value),
            "theoretical_price": _round_yen(theoretical_price),
        },
    }


def _render_comps_tab() -> None:
    st.markdown("入力は手動または所定フォーマットのCSV/XLSXで一括読み込みできます。")
    st.info("※有利子負債には短期・長期借入金および社債を含めてください。金額は百万円単位で入力します。")

    col1, col2 = st.columns([2, 1])
    with col1:
        with st.expander("データ入力／一括読込（CSV/XLSX）", expanded=True):
            uploaded = st.file_uploader(
                "所定フォーマットCSVまたはExcel(.xlsx)をアップロード（1行目=Target、その後がComps）",
                type=["csv", "xlsx"],
                key="comps_upload",
            )
            try:
                with open("comps_template.csv", "rb") as handle:
                    sample_bytes = handle.read()
                st.download_button(
                    "サンプルCSVをダウンロード",
                    data=sample_bytes,
                    file_name="comps_template.csv",
                    mime="text/csv",
                )
            except Exception:
                pass
            st.caption("CSV/XLSX ともに金額は百万円単位で記載してください。")
            sample_load = st.checkbox("サンプルデータを読み込む（例：テスト用のTarget+3Comps）", value=True, key="comps_sample")
    with col2:
        method = st.selectbox("適用するマルチプル", ["median", "average"], index=0, key="comps_method")

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".xlsx"):
                target, peers = parse_excel_upload(uploaded)
                st.success("Excelを読み込みました。TargetとCompsを設定します。")
            else:
                target, peers = parse_csv_upload(uploaded)
                st.success("CSVを読み込みました。TargetとCompsを設定します。")
            st.session_state["target_data"] = _build_target_profile_snapshot(target)
        except Exception as exc:
            st.error(f"読み込みエラー: {exc}")
            return
    else:
        st.info("手動入力を行う場合は、概要ページで TargetCo を設定したうえで Comps を入力してください。TargetCo の再入力は不要です。")
        if sample_load and not st.session_state.get("target_data"):
            target = {
                "company_name": "TargetCo",
                "ticker": "TGT",
                "business_description": "Sample target company for valuation workflow.",
                "share_price": 100.0,
                "market_cap": 0.0,
                "shares_outstanding": 100.0,
                "cash": 0.0,
                "sub_debt": 0.0,
                "minority": 0.0,
                "sales_fy_minus_3": 180.0,
                "sales_fy_minus_2": 190.0,
                "sales_fy_minus_1": 200.0,
                "operating_income_fy_minus_3": 18.0,
                "operating_income_fy_minus_2": 20.0,
                "operating_income_fy_minus_1": 22.0,
                "depreciation_fy_minus_3": 8.0,
                "depreciation_fy_minus_2": 8.5,
                "depreciation_fy_minus_1": 9.0,
                "capex_fy_minus_3": 10.0,
                "capex_fy_minus_2": 10.5,
                "capex_fy_minus_1": 11.0,
                "nwc_fy_minus_3": 10.0,
                "nwc_fy_minus_2": 11.0,
                "nwc_fy_minus_1": 12.0,
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
            st.session_state["target_data"] = _build_target_profile_snapshot(target)
            st.success("サンプルデータを読み込みました。")

        target = st.session_state.get("target_data", {})
        if not target:
            st.warning("概要ページでTargetCoの基本情報を入力してください。")
        else:
            _render_target_profile_inputs("comps", allow_edit=False)

        st.subheader("類似企業（手動入力またはCSV/XLSXで最大15社）")
        st.caption("各企業はデフォルトで折りたたみ表示です。必要な会社だけ展開して入力してください。")
        peers = []
        num_peers = st.number_input("手動で入力するCompsの数", min_value=0, max_value=15, value=0, step=1, key="num_peers_manual")
        for i in range(int(num_peers)):
            with st.expander(f"Comp {i+1}", expanded=False):
                comp: Dict[str, Any] = {}
                top_left, top_right = st.columns([2, 1])
                with top_left:
                    comp["company_name"] = st.text_input("企業名", value=f"Comp{i+1}", key=f"comp_name_{i}")
                with top_right:
                    comp["shares_outstanding"] = st.number_input("発行済株式数", min_value=0.0, value=1.0, key=f"comp_shares_{i}")

                money1, money2, money3 = st.columns(3)
                with money1:
                    comp["market_cap"] = st.number_input("市場時価総額（百万円）", min_value=0.0, value=0.0, key=f"comp_market_{i}")
                    comp["cash"] = st.number_input("現預金（百万円）", min_value=0.0, value=0.0, key=f"comp_cash_{i}")
                with money2:
                    comp["sub_debt"] = st.number_input("有利子負債（百万円）", min_value=0.0, value=0.0, key=f"comp_debt_{i}")
                    comp["minority"] = st.number_input("少数株主持分（百万円）", min_value=0.0, value=0.0, key=f"comp_min_{i}")
                with money3:
                    st.caption("※有利子負債には短期・長期借入金および社債を含めてください。")

                st.markdown("**財務数値（百万円）**")
                for period in PERIODS:
                    f1, f2, f3, f4 = st.columns(4)
                    with f1:
                        comp[f"sales_{period.lower().replace('+', '_plus')}"] = st.number_input(f"売上高 {period}", value=0.0, key=f"comp_sales_{i}_{period}")
                    with f2:
                        comp[f"ebitda_{period.lower().replace('+', '_plus')}"] = st.number_input(f"EBITDA {period}", value=0.0, key=f"comp_ebitda_{i}_{period}")
                    with f3:
                        comp[f"ebit_{period.lower().replace('+', '_plus')}"] = st.number_input(f"EBIT {period}", value=0.0, key=f"comp_ebit_{i}_{period}")
                    with f4:
                        comp[f"net_income_{period.lower().replace('+', '_plus')}"] = st.number_input(f"純利益 {period}", value=0.0, key=f"comp_net_{i}_{period}")
                peers.append(comp)

    if st.button("計算実行", key="comps_calc"):
        try:
            scaled_target = _scale_company_to_yen(target)
            scaled_peers = _scale_companies_list_to_yen(peers)
            stats = aggregate_peer_stats(scaled_peers)
            valuation = apply_multiples_to_target(scaled_target, stats, method=method)
            st.session_state["last_comps_result"] = {
                "target": target,
                "peers": peers,
                "stats": stats,
                "valuation": valuation,
                "method": method,
            }
        except Exception as exc:
            st.error(f"計算エラー: {exc}")
            return

        st.subheader("Benchmarking（マルチプル要約）")
        _display_table(build_benchmark_table(target, peers, stats))

        st.subheader("企業価値評価（Output）")
        out_rows: List[Dict[str, Any]] = []
        for metric in ["ev_sales", "ev_ebitda", "ev_ebit", "pe"]:
            for period in PERIODS:
                item = valuation["by_metric"][metric][period]
                out_rows.append(
                    {
                        "Metric": metric,
                        "Period": period,
                        "Multiple": item["multiple"],
                        "Implied EV (百万円)": _to_million(item["implied_ev"]),
                        "Implied Equity (百万円)": _to_million(item["implied_equity"]),
                        "Implied Price (百万円)": _to_million(item["implied_price"]),
                    }
                )
        _display_table(out_rows, numeric_cols=["Multiple"], money_cols=["Implied EV (百万円)", "Implied Equity (百万円)", "Implied Price (百万円)"])


def _render_dcf_tab() -> None:
    st.markdown("5年のDCFを数値のみで計算します。WACCと永久成長率の整合性が取れない場合はエラーにします。")
    st.caption("単位：百万円（入力・表示ともに百万円単位）")
    st.info("※永久成長率はWACC未満（推奨0%〜2%）で設定してください。WACC逆転時は計算できません。")

    target_data = st.session_state.get("target_data", {})
    historical = calculate_historical_trends(target_data) if target_data else None
    dcf_defaults = derive_dcf_defaults_from_history(target_data) if target_data else {
        "base_revenue": 1000.0,
        "base_nwc_ratio_pct": 0.0,
        "average_growth": None,
        "average_margin": None,
        "average_capex_ratio": None,
        "average_depreciation_ratio": None,
        "average_nwc_ratio": None,
        "trends": None,
    }

    top_left, top_right = st.columns([1.05, 1.2])
    with top_left:
        st.subheader("過去3年の実績サマリー")
        if historical:
            st.caption(format_history_line("売上高成長率", historical["growth_rates"], historical["average_growth"]))
            st.caption(format_history_line("営業利益率", historical["operating_margins"], historical["average_margin"]))
            st.caption(format_history_line("減価償却費対売上高比率", historical["depreciation_ratios"], historical["average_depreciation_ratio"]))
            st.caption(format_history_line("CapEx対売上高比率", historical["capex_ratios"], historical["average_capex_ratio"]))
            st.caption(format_history_line("NWC対売上高比率", historical["nwc_ratios"], historical["average_nwc_ratio"]))
            st.metric("FY-1 売上高", f"{(historical['revenues'][-1] or 0.0):,.2f} 百万円")
            st.metric("FY-1 営業利益", f"{(historical['operating_profits'][-1] or 0.0):,.2f} 百万円")
        else:
            st.warning("CompsページでTargetCoのFY-3〜FY-1実績を入力すると、ここに自動で過去推移が表示されます。")

    with top_right:
        st.subheader("DCF ベース年と資本構成")
        target_snapshot = st.session_state.get("target_data", {}) or {}
        if target_snapshot:
            st.metric("直近期売上高（FY-1, 百万円）", f"{float(dcf_defaults['base_revenue'] or 1000.0):,.2f}")
            st.metric("現預金（百万円）", f"{float(target_snapshot.get('cash', 0.0)):,.2f}")
            st.metric("有利子負債（百万円）", f"{float(target_snapshot.get('sub_debt', 0.0)):,.2f}")
            st.metric("発行済株式数", f"{float(target_snapshot.get('shares_outstanding', 0.0)):,.2f}")
        else:
            st.warning("概要ページでTargetCoの基本情報を入力してください。DCFはその内容を参照します。")

        base_revenue = float(dcf_defaults["base_revenue"] or 1000.0)
        cash = float(target_snapshot.get("cash", 200.0))
        debt = float(target_snapshot.get("sub_debt", 100.0))
        shares_outstanding = float(target_snapshot.get("shares_outstanding", 100.0))

        if historical and historical.get("average_margin") is not None:
            st.success(f"FY-1ベースでDCFを開始します。営業利益率の直近3年平均は {historical['average_margin']:.1f}% です。")

    st.markdown("---")

    wacc_left, wacc_right = st.columns([1.0, 1.2])
    with wacc_left:
        st.subheader("WACC 設定")
        st.caption("負債コスト、株主資本コスト、目標D/E比率から自動計算します。")
    with wacc_right:
        w1, w2, w3 = st.columns(3)
        with w1:
            risk_free_rate_pct = st.number_input("無リスク金利 Rf(%)", min_value=0.0, value=2.0, step=0.1, format="%.2f", key="dcf_rf")
        with w2:
            beta = st.number_input("ベータ", min_value=0.0, value=1.0, step=0.1, format="%.2f", key="dcf_beta")
        with w3:
            equity_risk_premium_pct = st.number_input("株式リスクプレミアム(%)", min_value=0.0, value=6.0, step=0.1, format="%.2f", key="dcf_erp")
        w4, w5 = st.columns(2)
        with w4:
            cost_of_debt_pct = st.number_input("負債コスト(%)", min_value=0.0, value=4.0, step=0.1, format="%.2f", key="dcf_cost_debt")
        with w5:
            target_de_ratio = st.number_input("目標D/E比率", min_value=0.0, value=1.0, step=0.1, format="%.2f", key="dcf_de_ratio")
        tax_rate_pct = st.number_input("実効税率(%)", min_value=0.0, value=30.0, step=0.1, format="%.2f", key="dcf_tax_rate")
        perpetual_growth_pct = st.number_input("永久成長率(%)", min_value=0.0, value=1.0, step=0.1, format="%.2f", key="dcf_perpetual_growth")

        wacc_pct = calculate_wacc(
            cost_of_debt_pct=cost_of_debt_pct,
            risk_free_rate_pct=risk_free_rate_pct,
            beta=beta,
            equity_risk_premium_pct=equity_risk_premium_pct,
            target_de_ratio=target_de_ratio,
            tax_rate_pct=tax_rate_pct,
        )
        st.metric("計算WACC", f"{wacc_pct:.2f}%")

    scenario = st.selectbox("ケースシナリオ", ["ベース", "楽観", "悲観"], index=0, key="dcf_scenario")
    scenario_slug = {"ベース": "base", "楽観": "bull", "悲観": "bear"}[scenario]
    nwc_mode = st.radio("NWC入力方式", ["ratio", "amount", "days"], horizontal=True, key="dcf_nwc_mode")

    defaults = {
        "ベース": {"growth": 5.0, "margin": 15.0, "capex": 8.0, "depreciation": 6.0, "nwc": 8.0},
        "楽観": {"growth": 8.0, "margin": 18.0, "capex": 9.0, "depreciation": 6.5, "nwc": 7.0},
        "悲観": {"growth": 2.0, "margin": 12.0, "capex": 7.0, "depreciation": 5.5, "nwc": 9.0},
    }[scenario]

    growth_default = float(dcf_defaults["average_growth"] if dcf_defaults["average_growth"] is not None else defaults["growth"])
    margin_default = float(dcf_defaults["average_margin"] if dcf_defaults["average_margin"] is not None else defaults["margin"])
    capex_default = float(dcf_defaults["average_capex_ratio"] if dcf_defaults["average_capex_ratio"] is not None else defaults["capex"])
    depreciation_default = float(
        dcf_defaults["average_depreciation_ratio"] if dcf_defaults["average_depreciation_ratio"] is not None else defaults["depreciation"]
    )
    nwc_default = float(dcf_defaults["average_nwc_ratio"] if dcf_defaults["average_nwc_ratio"] is not None else defaults["nwc"])

    if nwc_mode == "ratio":
        base_nwc_ratio_pct = st.number_input(
            "基準NWC比率(%)",
            min_value=0.0,
            value=float(dcf_defaults["base_nwc_ratio_pct"] or defaults["nwc"]),
            step=0.1,
            format="%.2f",
            key=f"dcf_base_nwc_{scenario_slug}",
            help="FY-1実績NWCから自動推定した比率を初期値にしています。",
        )
    else:
        base_nwc_ratio_pct = 0.0
        st.caption("NWC増加額を各年で直接入力します。")

    growth_rates: List[float] = []
    ebit_margins: List[float] = []
    capex_list: List[float] = []
    depreciation_list: List[float] = []
    nwc_inputs: List[float] = []
    cogs_list: List[float] = []

    metric_specs = [
        (
            "売上高成長率",
            "growth",
            historical["growth_rates"] if historical else [None, None, None],
            historical["average_growth"] if historical else None,
            "%",
        ),
        (
            "営業利益率",
            "margin",
            historical["operating_margins"] if historical else [None, None, None],
            historical["average_margin"] if historical else None,
            "%",
        ),
        (
            "CapEx対売上高比率",
            "capex",
            historical["capex_ratios"] if historical else [None, None, None],
            historical["average_capex_ratio"] if historical else None,
            "%",
        ),
        (
            "減価償却費対売上高比率",
            "dep",
            historical["depreciation_ratios"] if historical else [None, None, None],
            historical["average_depreciation_ratio"] if historical else None,
            "%",
        ),
        (
            "NWC対売上高比率",
            "nwc",
            historical["nwc_ratios"] if historical else [None, None, None],
            historical["average_nwc_ratio"] if historical else None,
            "%",
        ),
        (
            "COGS対売上高比率",
            "cogs",
            [None, None, None],
            None,
            "%",
        ),
    ]

    with st.expander("5年予測（Yearごとの前提）", expanded=True):
        for label, slug, hist_values, hist_avg, suffix in metric_specs:
            left, right = st.columns([1.25, 1.75])
            with left:
                st.markdown(f"**{label}**")
                if historical:
                    st.caption(format_history_line(label, hist_values, hist_avg, suffix=suffix))
                else:
                    st.caption("CompsページでTargetCoのFY-3〜FY-1実績を入力すると、ここに過去推移が表示されます。")
            with right:
                year_cols = st.columns(5)
                for idx, year in enumerate(range(1, 6)):
                    with year_cols[idx]:
                        if slug == "growth":
                            growth_rates.append(
                                st.slider(
                                    f"Year {year}",
                                    min_value=0.0,
                                    max_value=20.0,
                                    value=growth_default,
                                    step=0.1,
                                    format="%.1f%%",
                                    key=f"dcf_growth_{scenario_slug}_{year}",
                                )
                            )
                        elif slug == "margin":
                            ebit_margins.append(
                                st.slider(
                                    f"Year {year}",
                                    min_value=0.0,
                                    max_value=50.0,
                                    value=margin_default,
                                    step=0.1,
                                    format="%.1f%%",
                                    key=f"dcf_margin_{scenario_slug}_{year}",
                                )
                            )
                        elif slug == "capex":
                            capex_ratio = st.number_input(
                                f"Year {year}",
                                min_value=0.0,
                                value=capex_default,
                                step=0.1,
                                format="%.2f",
                                key=f"dcf_capex_{scenario_slug}_{year}",
                            )
                            capex_list.append(capex_ratio)
                        elif slug == "dep":
                            dep_ratio = st.number_input(
                                f"Year {year}",
                                min_value=0.0,
                                value=depreciation_default,
                                step=0.1,
                                format="%.2f",
                                key=f"dcf_dep_{scenario_slug}_{year}",
                            )
                            depreciation_list.append(dep_ratio)
                        elif slug == "nwc":
                            if nwc_mode == "ratio":
                                nwc_inputs.append(
                                    st.slider(
                                        f"Year {year}",
                                        min_value=0.0,
                                        max_value=20.0,
                                        value=nwc_default,
                                        step=0.1,
                                        format="%.1f%%",
                                        key=f"dcf_nwc_ratio_{scenario_slug}_{year}",
                                    )
                                )
                            else:
                                nwc_inputs.append(
                                    st.number_input(
                                        f"Year {year}",
                                        min_value=0.0,
                                        value=0.0,
                                        step=1.0,
                                        key=f"dcf_nwc_amount_{scenario_slug}_{year}",
                                    )
                                )
                        elif slug == "cogs":
                            cogs_ratio = st.number_input(
                                f"Year {year}",
                                min_value=0.0,
                                value=60.0,
                                step=0.1,
                                format="%.2f",
                                key=f"dcf_cogs_{scenario_slug}_{year}",
                            )
                            # cogs as percent of revenue
                            cogs_list.append(cogs_ratio)

        # If days-based NWC mode is selected, collect DSO/DIH/DPO per year
        if nwc_mode == "days":
            st.markdown("**B/S回転日数（各年）**")
            st.caption("※DSO = 売上債権 ÷ 売上高 × 365、DIH = 棚卸資産 ÷ 売上原価 × 365、DPO = 仕入債務 ÷ 売上原価 × 365")
            days_labels = [f"Year {y}" for y in range(1, 6)]
            dso_cols = st.columns(5)
            dso_list: List[float] = []
            for idx in range(5):
                with dso_cols[idx]:
                    dso_list.append(
                        st.number_input(
                            f"DSO {days_labels[idx]}",
                            min_value=0.0,
                            value=45.0,
                            step=1.0,
                            key=f"dcf_dso_{scenario_slug}_{idx+1}",
                        )
                    )

            dih_cols = st.columns(5)
            dih_list: List[float] = []
            for idx in range(5):
                with dih_cols[idx]:
                    dih_list.append(
                        st.number_input(
                            f"DIH {days_labels[idx]}",
                            min_value=0.0,
                            value=60.0,
                            step=1.0,
                            key=f"dcf_dih_{scenario_slug}_{idx+1}",
                        )
                    )

            dpo_cols = st.columns(5)
            dpo_list: List[float] = []
            for idx in range(5):
                with dpo_cols[idx]:
                    dpo_list.append(
                        st.number_input(
                            f"DPO {days_labels[idx]}",
                            min_value=0.0,
                            value=35.0,
                            step=1.0,
                            key=f"dcf_dpo_{scenario_slug}_{idx+1}",
                        )
                    )
        else:
            dso_list = []
            dih_list = []
            dpo_list = []

    if st.button("企業価値を計算", key="dcf_calc"):
        with st.spinner("財務モデルを計算中..."):
            try:
                scaled_base_revenue = base_revenue * 1_000_000.0
                scaled_cash = cash * 1_000_000.0
                scaled_debt = debt * 1_000_000.0
                forecast_revenues = []
                previous_revenue = scaled_base_revenue
                for growth in growth_rates:
                    current_revenue = previous_revenue * (1.0 + growth / 100.0)
                    forecast_revenues.append(current_revenue)
                    previous_revenue = current_revenue

                scaled_capex = [revenue * (ratio / 100.0) for revenue, ratio in zip(forecast_revenues, capex_list)]
                scaled_depreciation = [revenue * (ratio / 100.0) for revenue, ratio in zip(forecast_revenues, depreciation_list)]
                if nwc_mode == "ratio":
                    scaled_nwc_inputs = [revenue * (ratio / 100.0) for revenue, ratio in zip(forecast_revenues, nwc_inputs)]
                elif nwc_mode == "amount":
                    scaled_nwc_inputs = [value * 1_000_000.0 for value in nwc_inputs]
                else:
                    # days mode: NWC inputs not used as direct amounts - pass zeros placeholder
                    scaled_nwc_inputs = [0.0 for _ in range(5)]

                # Prepare COGS% and days lists for days-based NWC calc
                scaled_cogs_pct = cogs_list if len(cogs_list) == 5 else [60.0] * 5
                dso_days_list = dso_list if len(dso_list) == 5 else [45.0] * 5
                dih_days_list = dih_list if len(dih_list) == 5 else [60.0] * 5
                dpo_days_list = dpo_list if len(dpo_list) == 5 else [35.0] * 5

                valuation = calculate_dcf_valuation(
                    base_revenue=scaled_base_revenue,
                    cash=scaled_cash,
                    debt=scaled_debt,
                    shares_outstanding=shares_outstanding,
                    wacc_pct=wacc_pct,
                    perpetual_growth_pct=perpetual_growth_pct,
                    tax_rate_pct=tax_rate_pct,
                    growth_rates_pct=growth_rates,
                    ebit_margin_pct=ebit_margins,
                    capex=scaled_capex,
                    depreciation=scaled_depreciation,
                    nwc_inputs=scaled_nwc_inputs,
                    nwc_mode=nwc_mode,
                    base_nwc_ratio_pct=base_nwc_ratio_pct,
                    cogs_pct=scaled_cogs_pct,
                    dso_days=dso_days_list,
                    dih_days=dih_days_list,
                    dpo_days=dpo_days_list,
                )
                st.session_state["last_dcf_result"] = {
                    "valuation": valuation,
                    "wacc_pct": wacc_pct,
                    "target": target_snapshot,
                    "scenario": scenario,
                    "nwc_mode": nwc_mode,
                }
            except ValueError as exc:
                st.error(f"前提条件を見直してください: {exc}")
                return
            except Exception as exc:
                st.error(f"DCF計算エラー: {exc}")
                return

        st.subheader("将来FCFと現在価値")
        st.caption("ΔNWC は NWC残高の前年差です。正のΔNWCはFCFを押し下げます。表の金額は百万円表示です。")
        metrics_table: List[Dict[str, Any]] = []
        for label in ["Revenue", "Growth %", "EBIT Margin %", "EBIT", "Depreciation", "CapEx", "NWC残高", "ΔNWC", "FCF", "Discount Factor", "PV"]:
            row: Dict[str, Any] = {"項目": label}
            for entry in valuation["rows"]:
                col = f"Year {entry['year']}"
                if label == "Revenue":
                    row[col] = _to_million(entry["revenue"])
                elif label == "Growth %":
                    row[col] = entry["growth_rate_pct"]
                elif label == "EBIT Margin %":
                    row[col] = entry["ebit_margin_pct"]
                elif label == "EBIT":
                    row[col] = _to_million(entry["ebit"])
                elif label == "Depreciation":
                    row[col] = _to_million(entry["depreciation"])
                elif label == "CapEx":
                    row[col] = _to_million(entry["capex"])
                elif label == "NWC残高":
                    row[col] = _to_million(entry["nwc_current"])
                elif label == "ΔNWC":
                    row[col] = _to_million(entry["nwc_change"])
                elif label == "FCF":
                    row[col] = _to_million(entry["fcf"])
                elif label == "Discount Factor":
                    row[col] = round(entry["discount_factor"], 6)
                elif label == "PV":
                    row[col] = _to_million(entry["pv"])
            metrics_table.append(row)

        # If days-based NWC, show B/S breakdown per year
        if any(entry.get("receivables") is not None for entry in valuation["rows"]):
            st.subheader("B/S回転日数ベースの残高(売上債権/棚卸資産/仕入債務)")
            bs_rows: List[Dict[str, Any]] = []
            for label in ["Receivables", "Inventory", "Payables"]:
                row = {"項目": label}
                for entry in valuation["rows"]:
                    col = f"Year {entry['year']}"
                    if label == "Receivables":
                        row[col] = _to_million(entry.get("receivables"))
                    elif label == "Inventory":
                        row[col] = _to_million(entry.get("inventory"))
                    elif label == "Payables":
                        row[col] = _to_million(entry.get("payables"))
                bs_rows.append(row)
            _display_table(bs_rows, money_cols=["Receivables", "Inventory", "Payables"]) 

        _display_table(
            metrics_table,
            money_cols=["Revenue", "EBIT", "Depreciation", "CapEx", "NWC残高", "ΔNWC", "FCF", "PV"],
            percent_cols=["Growth %", "EBIT Margin %"],
            numeric_cols=["Discount Factor"],
        )

        st.subheader("ターミナルバリュー")
        tv_rows = [
            {"項目": "TV (百万円)", "金額": _to_million(valuation["terminal_value"])},
            {"項目": "TVの現在価値 (百万円)", "金額": _to_million(valuation["terminal_value_pv"])},
        ]
        _display_table(tv_rows, money_cols=["金額"])

        st.subheader("企業価値から理論株価")
        summary_rows = [
            {"項目": "事業価値(EV) (百万円)", "金額": _to_million(valuation["enterprise_value"])},
            {"項目": "株式価値(Equity Value) (百万円)", "金額": _to_million(valuation["equity_value"])},
            {"項目": "理論株価 (円/株)", "金額": valuation["theoretical_price"]},
        ]
        _display_table(summary_rows, money_cols=["金額"])

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("EV", f"{_to_million(valuation['enterprise_value']):,.2f} 百万円")
        with c2:
            st.metric("Equity", f"{_to_million(valuation['equity_value']):,.2f} 百万円")
        with c3:
            st.metric("理論株価", f"{valuation['theoretical_price']:,.2f} 円/株")


def _render_overview_page() -> None:
    target = _build_target_profile_snapshot(st.session_state.get("target_data", {}) or {})

    st.markdown("## 📋 Cover")
    st.caption("Excelテンプレートの表紙に相当するランディングページです。現在の設定状況をひと目で確認できます。")

    top_cols = st.columns(4)
    with top_cols[0]:
        st.metric("社名", target.get("company_name", "TargetCo"))
    with top_cols[1]:
        st.metric("Ticker", target.get("ticker", "TGT"))
    with top_cols[2]:
        st.metric("時価総額 / Equity Value", f"{_to_million(target.get('equity_value', 0.0)) :,.2f} 百万円")
    with top_cols[3]:
        st.metric("事業価値 / EV", f"{_to_million(target.get('enterprise_value', 0.0)) :,.2f} 百万円")

    st.markdown("---")
    st.subheader("BSスナップショット")
    st.caption("概要ページでは、企業価値だけでなく貸借対照表の主要項目も同時に確認できます。")
    bs_cols = st.columns(4)
    with bs_cols[0]:
        st.metric("現預金", f"{float(target.get('cash', 0.0)) :,.2f} 百万円")
    with bs_cols[1]:
        st.metric("有利子負債", f"{float(target.get('sub_debt', 0.0)) :,.2f} 百万円")
    with bs_cols[2]:
        st.metric("少数株主持分", f"{float(target.get('minority', 0.0)) :,.2f} 百万円")
    with bs_cols[3]:
        st.metric("ネットデット", f"{_to_million(target.get('net_debt', 0.0)) :,.2f} 百万円")

    st.markdown("**簡易内訳**")
    st.caption("※売上債権 + 棚卸資産 - 仕入債務 を営業運転資本の簡易指標として表示します。")
    breakdown_cols = st.columns(4)
    with breakdown_cols[0]:
        target["receivables"] = st.number_input(
            "売上債権",
            min_value=0.0,
            value=float(target.get("receivables", 0.0)),
            step=1.0,
            key="overview_receivables",
        )
    with breakdown_cols[1]:
        target["inventory"] = st.number_input(
            "棚卸資産",
            min_value=0.0,
            value=float(target.get("inventory", 0.0)),
            step=1.0,
            key="overview_inventory",
        )
    with breakdown_cols[2]:
        target["payables"] = st.number_input(
            "仕入債務",
            min_value=0.0,
            value=float(target.get("payables", 0.0)),
            step=1.0,
            key="overview_payables",
        )
    with breakdown_cols[3]:
        operating_nwc = float(target.get("receivables", 0.0)) + float(target.get("inventory", 0.0)) - float(target.get("payables", 0.0))
        st.metric("営業運転資本", f"{operating_nwc :,.2f} 百万円")

    target = _build_target_profile_snapshot(target)
    st.session_state["target_data"] = target

    info_left, info_right = st.columns([1.35, 1.0])
    with info_left:
        st.markdown(
            """
            ### 使い方

            1. [TargetCo] で社名、株価、株式数、財務情報、過去3年実績を入力
            2. [Comps] で最大15社の類似企業を入力または CSV / Excel を読み込み
            3. [DCF] で WACC と回転日数前提を入力して将来FCFを計算
            4. [Output] で DCF と Comps の最終結果を確認
            """
        )
        st.info("左のサイドバーでシートを切り替えると、Excelのタブを移動する感覚で操作できます。")
    with info_right:
        summary_cols = st.columns(2)
        with summary_cols[0]:
            st.metric("入力単位", "百万円")
        with summary_cols[1]:
            st.metric("評価手法", "Comps / DCF")
        if target.get("business_description"):
            st.caption(f"Business Description: {target['business_description']}")

    st.markdown("---")
    st.subheader("現在のTargetCoスナップショット")
    snapshot_cols = st.columns(4)
    with snapshot_cols[0]:
        st.metric("株価", f"{float(target.get('share_price', 0.0)) :,.2f} 円")
    with snapshot_cols[1]:
        st.metric("株式数", f"{float(target.get('shares_outstanding', 0.0)) :,.2f}")
    with snapshot_cols[2]:
        st.metric("現預金", f"{float(target.get('cash', 0.0)) :,.2f} 百万円")
    with snapshot_cols[3]:
        st.metric("有利子負債", f"{float(target.get('sub_debt', 0.0)) :,.2f} 百万円")

    st.markdown("---")
    st.subheader("直近実績（FY-1 / LTM）サマリー")
    ltm_cols = st.columns(4)
    with ltm_cols[0]:
        st.metric("売上高", f"{float(target.get('sales_fy_minus_1', 0.0)) :,.2f} 百万円")
    with ltm_cols[1]:
        st.metric("営業利益", f"{float(target.get('operating_income_fy_minus_1', 0.0)) :,.2f} 百万円")
    with ltm_cols[2]:
        st.metric("EBITDA", f"{float(target.get('ebitda_ltm', target.get('ebitda_cy2', 0.0))) :,.2f} 百万円")
    with ltm_cols[3]:
        st.metric("純利益", f"{float(target.get('net_income_ltm', 0.0)) :,.2f} 百万円")

    st.caption("ヒント: TargetCo の詳細編集は [TargetCo] シートで行います。Cover は現在値の確認用です。")


def _render_targetco_page() -> None:
    st.markdown("## 🏢 TargetCo")
    st.caption("評価対象企業の基本情報と過去実績をまとめて入力するシートです。ExcelのTargetCoタブのように使えます。")

    target = _build_target_profile_snapshot(st.session_state.get("target_data", {}) or {})
    summary_cols = st.columns(4)
    with summary_cols[0]:
        st.metric("時価総額 / Equity Value", f"{_to_million(target.get('equity_value', 0.0)) :,.2f} 百万円")
    with summary_cols[1]:
        st.metric("事業価値 / Enterprise Value", f"{_to_million(target.get('enterprise_value', 0.0)) :,.2f} 百万円")
    with summary_cols[2]:
        st.metric("株価", f"{float(target.get('share_price', 0.0)) :,.2f} 円")
    with summary_cols[3]:
        st.metric("ネットデット", f"{_to_million(target.get('net_debt', 0.0)) :,.2f} 百万円")

    st.markdown("---")
    with st.container():
        target = _render_target_profile_inputs("targetco", allow_edit=True)

    st.markdown("---")
    st.subheader("直近実績（FY-1 / LTM）")
    ltm_cols = st.columns(4)
    with ltm_cols[0]:
        st.metric("売上高", f"{float(target.get('sales_fy_minus_1', 0.0)) :,.2f} 百万円")
    with ltm_cols[1]:
        st.metric("営業利益", f"{float(target.get('operating_income_fy_minus_1', 0.0)) :,.2f} 百万円")
    with ltm_cols[2]:
        st.metric("EBITDA", f"{float(target.get('ebitda_ltm', target.get('ebitda_cy2', 0.0))) :,.2f} 百万円")
    with ltm_cols[3]:
        st.metric("純利益", f"{float(target.get('net_income_ltm', 0.0)) :,.2f} 百万円")


def _render_output_page() -> None:
    st.markdown("## 🏆 Output")
    st.caption("DCF と Comps の最終結果を一画面に集約したエグゼクティブ・サマリーです。")

    target = _build_target_profile_snapshot(st.session_state.get("target_data", {}) or {})
    last_dcf = st.session_state.get("last_dcf_result") or {}
    last_comps = st.session_state.get("last_comps_result") or {}

    dcf_valuation = last_dcf.get("valuation") or {}
    comps_valuation = (last_comps.get("valuation") or {}).get("by_metric", {})

    top_cols = st.columns(3)
    with top_cols[0]:
        if dcf_valuation:
            st.metric("DCF 理論株価", f"{float(dcf_valuation.get('theoretical_price', 0.0)) :,.2f} 円/株")
        else:
            st.metric("DCF 理論株価", "-")
    with top_cols[1]:
        st.metric("TargetCo 時価総額", f"{_to_million(target.get('equity_value', 0.0)) :,.2f} 百万円")
    with top_cols[2]:
        st.metric("TargetCo 事業価値", f"{_to_million(target.get('enterprise_value', 0.0)) :,.2f} 百万円")

    st.markdown("---")
    st.subheader("Comps 推定株価レンジ")
    if comps_valuation:
        comp_cards = st.columns(4)
        comp_labels = [
            ("EV/Sales", "ev_sales"),
            ("EV/EBITDA", "ev_ebitda"),
            ("EV/EBIT", "ev_ebit"),
            ("P/E", "pe"),
        ]
        comp_summary_rows: List[Dict[str, Any]] = []
        for idx, (label, metric_key) in enumerate(comp_labels):
            periods = comps_valuation.get(metric_key, {})
            prices = [periods[p].get("implied_price") for p in PERIODS if periods.get(p) and periods[p].get("implied_price") is not None]
            prices = [float(price) for price in prices if price is not None]
            if prices:
                min_price = min(prices)
                max_price = max(prices)
                avg_price = statistics.mean(prices)
                median_price = statistics.median(prices)
            else:
                min_price = max_price = avg_price = median_price = None

            with comp_cards[idx]:
                if median_price is not None:
                    st.metric(label, f"{median_price:,.2f} 円/株", f"{min_price:,.2f} - {max_price:,.2f}")
                else:
                    st.metric(label, "-")

            comp_summary_rows.append(
                {
                    "Method": label,
                    "Min Price (円/株)": min_price,
                    "Median Price (円/株)": median_price,
                    "Avg Price (円/株)": avg_price,
                    "Max Price (円/株)": max_price,
                }
            )

        _display_table(
            comp_summary_rows,
            numeric_cols=["Min Price (円/株)", "Median Price (円/株)", "Avg Price (円/株)", "Max Price (円/株)"],
        )
    else:
        st.info("Comps の計算結果がまだありません。Comps シートで計算を実行してください。")

    st.markdown("---")
    st.subheader("DCF サマリー")
    if dcf_valuation:
        dcf_cols = st.columns(4)
        with dcf_cols[0]:
            st.metric("WACC", f"{float(last_dcf.get('wacc_pct', 0.0)) :,.2f}%")
        with dcf_cols[1]:
            st.metric("事業価値(EV)", f"{_to_million(dcf_valuation.get('enterprise_value', 0.0)) :,.2f} 百万円")
        with dcf_cols[2]:
            st.metric("株式価値", f"{_to_million(dcf_valuation.get('equity_value', 0.0)) :,.2f} 百万円")
        with dcf_cols[3]:
            st.metric("理論株価", f"{float(dcf_valuation.get('theoretical_price', 0.0)) :,.2f} 円/株")

        summary_table = [
            {"項目": "WACC", "値": last_dcf.get("wacc_pct")},
            {"項目": "理論株価 (円/株)", "値": dcf_valuation.get("theoretical_price")},
            {"項目": "EV (百万円)", "値": _to_million(dcf_valuation.get("enterprise_value"))},
            {"項目": "Equity (百万円)", "値": _to_million(dcf_valuation.get("equity_value"))},
        ]
        _display_table(summary_table, numeric_cols=["値"])
    else:
        st.info("DCF の計算結果がまだありません。DCF シートで計算を実行してください。")


def _render_sidebar() -> str:
    st.sidebar.title("Workbook Navigation")
    st.sidebar.caption("Excelのシートを切り替える感覚で操作できます。")
    page = st.sidebar.radio(
        "シート",
        [
            "📋 [Cover] アプリの概要・使い方",
            "🏢 [TargetCo] 評価対象企業の基本情報・過去実績",
            "📊 [Comps] 類似企業比較法（最大15社）の入力とベンチマーク表",
            "⏳ [DCF] WACC・回転日数前提の入力と将来キャッシュフロー表",
            "🏆 [Output] 最終的な価値算定結果サマリー",
        ],
        index=0,
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown("**使い方**")
    st.sidebar.write("1. Cover で全体像を確認")
    st.sidebar.write("2. TargetCo で基本情報と過去実績を入力")
    st.sidebar.write("3. Comps で比較企業を入力または読込")
    st.sidebar.write("4. DCF で WACC と回転日数前提を入力")
    st.sidebar.write("5. Output で最終サマリーを確認")
    return page


def _render_ui() -> None:
    st.set_page_config(page_title="Comps Valuation", layout="wide")
    _inject_excel_ui_styles()
    page = _render_sidebar()
    st.title("Comps形式バリュエーション Workbook")
    st.markdown("Excelテンプレートのシート構成に沿って、入力・計算・出力を分離したプロ仕様UIです。")

    if page == "📋 [Cover] アプリの概要・使い方":
        _render_overview_page()
    elif page == "🏢 [TargetCo] 評価対象企業の基本情報・過去実績":
        _render_targetco_page()
    elif page == "📊 [Comps] 類似企業比較法（最大15社）の入力とベンチマーク表":
        _render_comps_tab()
    elif page == "⏳ [DCF] WACC・回転日数前提の入力と将来キャッシュフロー表":
        _render_dcf_tab()
    else:
        _render_output_page()


def main() -> None:
    if st is None:
        print("Streamlit is not available in this environment.")
        return
    _render_ui()


if __name__ == "__main__":
    main()