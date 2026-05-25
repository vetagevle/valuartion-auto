"""Professional Comps-style Valuation Streamlit App

This module provides a Streamlit UI for entering TargetCo and up to 15 Comps,
parsing CSV uploads, computing multiples (EV/Sales, EV/EBITDA, EV/EBIT, P/E)
for LTM/CY+1/CY+2, aggregating statistics (Min/Max/Average/Median), and
applying median/average multiples to the TargetCo to produce implied EV,
equity value, and implied share price.

All calculation functions are pure and testable without Streamlit.
UI uses only st.metric, st.dataframe and basic input widgets so it runs in
minimal environments.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Tuple
import statistics

st: Any
try:
    import streamlit as _st
except Exception:
    st = None
else:
    st = _st


PERIODS = ["LTM", "CY+1", "CY+2"]


def compute_ev(company: Dict[str, float]) -> float:
    """Compute EV = market_cap + sub_debt + minority - cash"""
    market_cap = float(company.get("market_cap", 0.0))
    sub_debt = float(company.get("sub_debt", 0.0))
    minority = float(company.get("minority", 0.0))
    cash = float(company.get("cash", 0.0))
    return market_cap + sub_debt + minority - cash


def safe_div(n: float, d: float) -> Optional[float]:
    try:
        if d == 0:
            return None
        # treat negative denominators as invalid for multiples
        if d <= 0:
            return None
        return n / d
    except Exception:
        return None


def validate_non_negative(label: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{label}は0以上の値を入力してください。")


def calculate_metrics(company: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Compatibility helper: compute common multiples for a simplified company dict.

    Returns keys: per, pbr, ev_sales, ev_ebitda, ev_ebit
    """
    # Validate a subset of fields
    keys_to_check = [
        ("時価総額", company.get("market_cap", 0.0)),
        ("純利益", company.get("net_income", 0.0)),
        ("純資産", company.get("net_assets", 0.0)),
        ("営業利益", company.get("operating_income", 0.0)),
        ("減価償却費", company.get("depreciation", 0.0)),
        ("有利子負債", company.get("sub_debt", 0.0)),
        ("現預金", company.get("cash", 0.0)),
    ]
    for label, v in keys_to_check:
        validate_non_negative(label, float(v))

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


def _apply_multiple(
    multiple: float,
    target: Dict[str, float],
    method: str,
) -> float:
    target_net_debt = target.get("sub_debt", 0.0) - target.get("cash", 0.0)

    if method == "per":
        value = multiple * target.get("net_income", 0.0)
    elif method == "pbr":
        value = multiple * target.get("net_assets", 0.0)
    elif method == "ev_sales":
        value = multiple * target.get("sales", 0.0) - target_net_debt
    elif method == "ev_ebitda":
        target_ebitda = target.get("operating_income", 0.0) + target.get("depreciation", 0.0)
        value = multiple * target_ebitda - target_net_debt
    elif method == "ev_ebit":
        value = multiple * target.get("operating_income", 0.0) - target_net_debt
    else:
        raise ValueError(f"未知の手法です: {method}")

    return max(0.0, value)


def compute_valuation_range(target: Dict[str, float], peers: List[Dict[str, float]]) -> Dict[str, Dict[str, Any]]:
    """Apply peer multiples to the target company and summarize each method.

    Returns a dict keyed by method with 'values', 'min', 'max', 'avg'
    where 'values' are the applied equity values (multiple applied to target denominator
    and adjusted for net debt where applicable).
    """
    # Basic validations (non-negative)
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


def compute_multiples_for_company(company: Dict[str, Any]) -> Dict[str, Dict[str, Optional[float]]]:
    """Return multiples per metric per period.

    Returns a dict: {metric: {period: value_or_None}}
    Metrics: ev_sales, ev_ebitda, ev_ebit, pe
    """
    ev = compute_ev(company)

    # Gather denominators
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

    for p in PERIODS:
        multiples["ev_sales"][p] = safe_div(ev, sales[p])
        multiples["ev_ebitda"][p] = safe_div(ev, ebitda[p])
        multiples["ev_ebit"][p] = safe_div(ev, ebit[p])
        # P/E uses market_cap / net_income
        market_cap = float(company.get("market_cap", 0.0))
        multiples["pe"][p] = safe_div(market_cap, net_income[p])

    return multiples


def aggregate_peer_stats(peers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Aggregate min/max/avg/median for each metric and period across peers.

    Returns: {metric: {period: {min,max,avg,median}}}
    """
    # collect multiples per metric/period
    collected: Dict[str, Dict[str, List[float]]] = {
        "ev_sales": {p: [] for p in PERIODS},
        "ev_ebitda": {p: [] for p in PERIODS},
        "ev_ebit": {p: [] for p in PERIODS},
        "pe": {p: [] for p in PERIODS},
    }

    for peer in peers:
        m = compute_multiples_for_company(peer)
        for metric in collected:
            for p in PERIODS:
                val = m.get(metric, {}).get(p)
                if val is not None:
                    collected[metric][p].append(val)

    stats: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for metric, per_dict in collected.items():
        stats[metric] = {}
        for p, values in per_dict.items():
            if not values:
                stats[metric][p] = {"min": None, "max": None, "avg": None, "median": None}
            else:
                stats[metric][p] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": statistics.mean(values),
                    "median": statistics.median(values),
                }
    return stats


def apply_multiples_to_target(target: Dict[str, Any], stats: Dict[str, Dict[str, Dict[str, Optional[float]]]], method: str = "median") -> Dict[str, Any]:
    """Apply chosen method ('median' or 'avg') to compute implied EV and equity for target.

    For each metric and period, compute:
      implied_ev = multiple * target_metric
      implied_equity = implied_ev - sub_debt - minority + cash
      implied_price = implied_equity / shares_outstanding (if shares>0)
    """
    result: Dict[str, Any] = {"by_metric": {}}
    for metric in ["ev_sales", "ev_ebitda", "ev_ebit", "pe"]:
        result["by_metric"][metric] = {}
        for p in PERIODS:
            multiple = stats.get(metric, {}).get(p, {}).get(method if method != "avg" else "avg")
            # allow method 'average' alias
            if method == "average":
                multiple = stats.get(metric, {}).get(p, {}).get("avg")
            if multiple is None:
                result["by_metric"][metric][p] = {"multiple": None, "implied_ev": None, "implied_equity": None, "implied_price": None}
                continue

            # select target denominator
            denom_map = {
                "ev_sales": f"sales_{p.lower().replace('+','_plus')}",
            }
            # map period keys
            denom_value = None
            if metric == "ev_sales":
                key = {"LTM": "sales_ltm", "CY+1": "sales_cy1", "CY+2": "sales_cy2"}[p]
                denom_value = float(target.get(key, 0.0))
            elif metric == "ev_ebitda":
                key = {"LTM": "ebitda_ltm", "CY+1": "ebitda_cy1", "CY+2": "ebitda_cy2"}[p]
                denom_value = float(target.get(key, 0.0))
            elif metric == "ev_ebit":
                key = {"LTM": "ebit_ltm", "CY+1": "ebit_cy1", "CY+2": "ebit_cy2"}[p]
                denom_value = float(target.get(key, 0.0))
            elif metric == "pe":
                key = {"LTM": "net_income_ltm", "CY+1": "net_income_cy1", "CY+2": "net_income_cy2"}[p]
                denom_value = float(target.get(key, 0.0))

            if denom_value <= 0:
                implied_ev = None
                implied_equity = None
                implied_price = None
            else:
                implied_ev = multiple * denom_value
                implied_equity = implied_ev - float(target.get("sub_debt", 0.0)) - float(target.get("minority", 0.0)) + float(target.get("cash", 0.0))
                shares = float(target.get("shares_outstanding", 0.0))
                implied_price = None if shares <= 0 else implied_equity / shares

            result["by_metric"][metric][p] = {
                "multiple": multiple,
                "denom": denom_value,
                "implied_ev": implied_ev,
                "implied_equity": implied_equity,
                "implied_price": implied_price,
            }

    return result


def parse_csv_upload(uploaded_file: io.BytesIO) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Parse CSV uploaded in expected format.

    Expected header columns (company-level):
    company_name, market_cap, shares_outstanding, cash, sub_debt, minority,
    sales_ltm, sales_cy1, sales_cy2,
    ebitda_ltm, ebitda_cy1, ebitda_cy2,
    ebit_ltm, ebit_cy1, ebit_cy2,
    net_income_ltm, net_income_cy1, net_income_cy2

    First row is TargetCo; subsequent rows (up to 15) are peers.
    """
    text = uploaded_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = [r for r in reader]
    if not rows:
        raise ValueError("CSVに有効な行が含まれていません。")

    def _normalize_row(r: Dict[str, str]) -> Dict[str, Any]:
        def f(k: str) -> float:
            v = r.get(k, "")
            try:
                return float(v) if v != "" else 0.0
            except Exception:
                return 0.0

        return {
            "company_name": r.get("company_name", ""),
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

    normalized = [_normalize_row(r) for r in rows]
    target = normalized[0]
    peers = normalized[1:16]
    return target, peers


def _render_ui() -> None:
    st.set_page_config(page_title="Comps Valuation", layout="wide")
    st.title("Comps形式バリュエーション（プロ仕様）")

    st.markdown("入力は手動または所定フォーマットのCSVで一括読み込みできます。CSVの見本はREADMEを参照してください。")

    col1, col2 = st.columns([2, 1])
    with col1:
        uploaded = st.file_uploader("所定フォーマットCSVをアップロード（1行目=Target、その後がComps）", type=["csv"])
    with col2:
        method = st.selectbox("適用するマルチプル", ["median", "average"], index=0)

    if uploaded is not None:
        try:
            target, peers = parse_csv_upload(uploaded)
            st.success("CSVを読み込みました。TargetとCompsを設定します。")
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e}")
            return
    else:
        st.info("手動入力を行う場合は下のフォームで Target と Comps を入力してください（省略時は0扱い）。")
        sample_load = st.checkbox("サンプルデータを読み込む（例：テスト用のTarget+3Comps）", value=False)
        if sample_load:
            # Sample target and 3 peers matching unit tests
            target = {
                "company_name": "TargetCo",
                "market_cap": 0.0,
                "shares_outstanding": 100.0,
                "cash": 0.0,
                "sub_debt": 0.0,
                "minority": 0.0,
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
            peers = []
            for i in range(3):
                peers.append(
                    {
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
                )
            st.success("サンプルデータを読み込みました。下の計算実行ボタンで結果を確認できます。")
        else:
            # For brevity implement minimal manual target input (single block, keys provided)
            st.subheader("TargetCo 入力")
            target = {}
            tcol1, tcol2 = st.columns(2)
            with tcol1:
                target["company_name"] = st.text_input("企業名", value="TargetCo", key="target_company_name")
                target["market_cap"] = st.number_input("市場時価総額", min_value=0.0, value=0.0, step=1.0, key="target_market_cap")
                target["shares_outstanding"] = st.number_input("発行済株式数", min_value=0.0, value=1.0, step=1.0, key="target_shares")
                target["cash"] = st.number_input("現預金", min_value=0.0, value=0.0, step=1.0, key="target_cash")
            with tcol2:
                target["sub_debt"] = st.number_input("有利子負債", min_value=0.0, value=0.0, step=1.0, key="target_sub_debt")
                target["minority"] = st.number_input("少数株主持分", min_value=0.0, value=0.0, step=1.0, key="target_minority")
            st.markdown("**財務（LTM / CY+1 / CY+2）**")
            for p in PERIODS:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    target[f"sales_{p.replace('+','plus').lower()}"] = st.number_input(f"売上高 {p}", value=0.0, key=f"target_sales_{p}")
                with c2:
                    target[f"ebitda_{p.replace('+','plus').lower()}"] = st.number_input(f"EBITDA {p}", value=0.0, key=f"target_ebitda_{p}")
                with c3:
                    target[f"ebit_{p.replace('+','plus').lower()}"] = st.number_input(f"EBIT {p}", value=0.0, key=f"target_ebit_{p}")
                with c4:
                    target[f"net_income_{p.replace('+','plus').lower()}"] = st.number_input(f"純利益 {p}", value=0.0, key=f"target_net_{p}")

            # Manual comps entry: allow a small number via expanders
            st.subheader("類似企業（手動入力またはCSVで最大15社）")
            peers: List[Dict[str, Any]] = []
            num_peers = st.number_input("手動で入力するCompsの数", min_value=0, max_value=15, value=0, step=1, key="num_peers_manual")
            for i in range(int(num_peers)):
                with st.expander(f"Comp {i+1}"):
                    c = {}
                    c["company_name"] = st.text_input("企業名", value=f"Comp{i+1}", key=f"comp_name_{i}")
                    c["market_cap"] = st.number_input("市場時価総額", min_value=0.0, value=0.0, key=f"comp_market_{i}")
                    c["shares_outstanding"] = st.number_input("発行済株式数", min_value=0.0, value=1.0, key=f"comp_shares_{i}")
                    c["cash"] = st.number_input("現預金", min_value=0.0, value=0.0, key=f"comp_cash_{i}")
                    c["sub_debt"] = st.number_input("有利子負債", min_value=0.0, value=0.0, key=f"comp_debt_{i}")
                    c["minority"] = st.number_input("少数株主持分", min_value=0.0, value=0.0, key=f"comp_min_{i}")
                    for p in PERIODS:
                        c[f"sales_{p.lower().replace('+','_plus')}"] = st.number_input(f"売上高 {p}", value=0.0, key=f"comp_sales_{i}_{p}")
                        c[f"ebitda_{p.lower().replace('+','_plus')}"] = st.number_input(f"EBITDA {p}", value=0.0, key=f"comp_ebitda_{i}_{p}")
                        c[f"ebit_{p.lower().replace('+','_plus')}"] = st.number_input(f"EBIT {p}", value=0.0, key=f"comp_ebit_{i}_{p}")
                        c[f"net_income_{p.lower().replace('+','_plus')}"] = st.number_input(f"純利益 {p}", value=0.0, key=f"comp_net_{i}_{p}")
                    peers.append(c)
        # For brevity implement minimal manual target input
        st.subheader("TargetCo 入力")
        target = {}
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            target["company_name"] = st.text_input("企業名", value="TargetCo")
            target["market_cap"] = st.number_input("市場時価総額", min_value=0.0, value=0.0, step=1.0)
            target["shares_outstanding"] = st.number_input("発行済株式数", min_value=0.0, value=1.0, step=1.0)
            target["cash"] = st.number_input("現預金", min_value=0.0, value=0.0, step=1.0)
        with tcol2:
            target["sub_debt"] = st.number_input("有利子負債", min_value=0.0, value=0.0, step=1.0)
            target["minority"] = st.number_input("少数株主持分", min_value=0.0, value=0.0, step=1.0)
        st.markdown("**財務（LTM / CY+1 / CY+2）**")
        for p in PERIODS:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                target[f"sales_{p.replace('+','plus').lower()}"] = st.number_input(f"売上高 {p}", value=0.0, key=f"target_sales_{p}")
            with c2:
                target[f"ebitda_{p.replace('+','plus').lower()}"] = st.number_input(f"EBITDA {p}", value=0.0, key=f"target_ebitda_{p}")
            with c3:
                target[f"ebit_{p.replace('+','plus').lower()}"] = st.number_input(f"EBIT {p}", value=0.0, key=f"target_ebit_{p}")
            with c4:
                target[f"net_income_{p.replace('+','plus').lower()}"] = st.number_input(f"純利益 {p}", value=0.0, key=f"target_net_{p}")

        # Manual comps entry: allow a small number via expanders
        st.subheader("類似企業（手動入力またはCSVで最大15社）")
        peers: List[Dict[str, Any]] = []
        num_peers = st.number_input("手動で入力するCompsの数", min_value=0, max_value=15, value=0, step=1)
        for i in range(int(num_peers)):
            with st.expander(f"Comp {i+1}"):
                c = {}
                c["company_name"] = st.text_input("企業名", value=f"Comp{i+1}", key=f"comp_name_{i}")
                c["market_cap"] = st.number_input("市場時価総額", min_value=0.0, value=0.0, key=f"comp_market_{i}")
                c["shares_outstanding"] = st.number_input("発行済株式数", min_value=0.0, value=1.0, key=f"comp_shares_{i}")
                c["cash"] = st.number_input("現預金", min_value=0.0, value=0.0, key=f"comp_cash_{i}")
                c["sub_debt"] = st.number_input("有利子負債", min_value=0.0, value=0.0, key=f"comp_debt_{i}")
                c["minority"] = st.number_input("少数株主持分", min_value=0.0, value=0.0, key=f"comp_min_{i}")
                for p in PERIODS:
                    c[f"sales_{p.lower().replace('+','_plus')}"] = st.number_input(f"売上高 {p}", value=0.0, key=f"comp_sales_{i}_{p}")
                    c[f"ebitda_{p.lower().replace('+','_plus')}"] = st.number_input(f"EBITDA {p}", value=0.0, key=f"comp_ebitda_{i}_{p}")
                    c[f"ebit_{p.lower().replace('+','_plus')}"] = st.number_input(f"EBIT {p}", value=0.0, key=f"comp_ebit_{i}_{p}")
                    c[f"net_income_{p.lower().replace('+','_plus')}"] = st.number_input(f"純利益 {p}", value=0.0, key=f"comp_net_{i}_{p}")
                peers.append(c)

    # Calculation and Output
    if st.button("計算実行"):
        if not target:
            st.error("Targetのデータが不足しています。")
            return

        # prepare peers: if uploaded provided, peers variable set above
        try:
            stats = aggregate_peer_stats(peers)
            valuation = apply_multiples_to_target(target, stats, method=method)
        except Exception as e:
            st.error(f"計算エラー: {e}")
            return

        st.subheader("Benchmarking（マルチプル要約）")
        # Build table for display: rows = metric x period x stats
        display_rows = []
        for metric in ["ev_sales", "ev_ebitda", "ev_ebit", "pe"]:
            for p in PERIODS:
                s = stats.get(metric, {}).get(p, {})
                display_rows.append({"Metric": metric, "Period": p, "Min": s.get("min"), "Max": s.get("max"), "Avg": s.get("avg"), "Median": s.get("median")})
        st.dataframe(display_rows, use_container_width=True)

        st.subheader("企業価値評価（Output）")
        out_rows = []
        for metric in ["ev_sales", "ev_ebitda", "ev_ebit", "pe"]:
            for p in PERIODS:
                item = valuation["by_metric"][metric][p]
                out_rows.append({"Metric": metric, "Period": p, "Multiple": item["multiple"], "Implied EV": item["implied_ev"], "Implied Equity": item["implied_equity"], "Implied Price": item["implied_price"]})
        st.dataframe(out_rows, use_container_width=True)


def main():
    if st is None:
        print("Streamlit is not available in this environment. Import the module's functions for testing.")
        return
    _render_ui()


if __name__ == "__main__":
    main()
