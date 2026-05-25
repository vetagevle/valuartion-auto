"""Streamlit app for global large-cap corporate valuation.

This module keeps the valuation logic testable and separates the Streamlit UI
from the calculation helpers used by the unit tests.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional, Sequence

st: Any
try:
    import streamlit as _streamlit
except ModuleNotFoundError:
    st = None
else:
    st = _streamlit

APP_TITLE = "グローバル大手企業特化型・企業価値評価ツール"
APP_DESCRIPTION = (
    "手入力ベースで、類似企業比較法とDCF法を一画面で実行できる企業価値評価ダッシュボードです。"
)
PEER_COUNT = 5
DEFAULT_FORECAST_YEARS = 5

KEY_MAP = {
    "売上高": "sales",
    "sales": "sales",
    "revenue": "sales",
    "net_sales": "sales",
    "営業利益": "operating_income",
    "operating_income": "operating_income",
    "operating profit": "operating_income",
    "純利益": "net_income",
    "当期純利益": "net_income",
    "net_income": "net_income",
    "profit": "net_income",
    "時価総額": "market_cap",
    "market_cap": "market_cap",
    "market capitalization": "market_cap",
    "純資産": "net_assets",
    "自己資本": "net_assets",
    "net_assets": "net_assets",
    "total_equity": "net_assets",
    "減価償却費": "depreciation",
    "減価償却": "depreciation",
    "depreciation": "depreciation",
    "有利子負債": "sub_debt",
    "有利子": "sub_debt",
    "interest_bearing_debt": "sub_debt",
    "sub_debt": "sub_debt",
    "現預金": "cash",
    "現金及び現金同等物": "cash",
    "cash": "cash",
    "cash_and_equivalents": "cash",
}

NEEDED_KEYS = {
    "market_cap",
    "sales",
    "net_income",
    "net_assets",
    "operating_income",
    "depreciation",
    "sub_debt",
    "cash",
}

DISPLAY_METHOD_ORDER = ["per", "pbr", "ev_ebitda", "ev_ebit"]
DISPLAY_METHOD_LABELS = {
    "per": "PER",
    "pbr": "PBR",
    "ev_ebitda": "EV/EBITDA",
    "ev_ebit": "EV/EBIT",
    "ev_sales": "EV/Sales",
}


def normalize_key(key: str) -> Optional[str]:
    if not key:
        return None
    raw_key = key.strip()
    lower_key = raw_key.lower()
    if raw_key in KEY_MAP:
        return KEY_MAP[raw_key]
    for original, mapped in KEY_MAP.items():
        if original.lower() == lower_key:
            return mapped
    normalized = lower_key.replace(" ", "").replace("（連結）", "").replace("(連結)", "")
    for original, mapped in KEY_MAP.items():
        if original.lower().replace(" ", "") == normalized:
            return mapped
    return None


def parse_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return 0.0
    text = text.replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        try:
            return -float(text[1:-1])
        except Exception:
            return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _empty_company() -> Dict[str, float]:
    company = {key: 0.0 for key in NEEDED_KEYS}
    return company


def _finalize_companies(companies: Sequence[Dict[str, float]]) -> Sequence[Dict[str, float]]:
    for company in companies:
        for key in NEEDED_KEYS:
            company.setdefault(key, 0.0)
    return companies


def parse_statement_style_csv(reader: csv.DictReader) -> tuple[Dict[str, float], List[Dict[str, float]]]:
    """Parse row-oriented financial statement CSV data.

    The first column is treated as the item label and the remaining columns as
    company values.
    """

    fieldnames = reader.fieldnames or []
    if len(fieldnames) < 2:
        return {}, []

    label_field = fieldnames[0]
    company_fields = fieldnames[1:]
    companies: List[Dict[str, float]] = [dict() for _ in company_fields]

    for row in reader:
        label = str(row.get(label_field, "")).strip()
        mapped_key = normalize_key(label)
        if mapped_key is None:
            continue
        for index, company_field in enumerate(company_fields):
            companies[index][mapped_key] = parse_number(row.get(company_field))

    _finalize_companies(companies)
    target = companies[0] if companies else {}
    peers = list(companies[1 : 1 + PEER_COUNT])
    return target, peers


def parse_pasted_statement(text: str) -> tuple[Dict[str, float], List[Dict[str, float]]]:
    """Parse pasted CSV-like statement data in row-oriented form."""

    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return {}, []

    max_cols = max(len(row) for row in rows) - 1
    companies: List[Dict[str, float]] = [dict() for _ in range(max_cols)]

    for row in rows:
        label = row[0].strip()
        mapped_key = normalize_key(label)
        if mapped_key is None:
            continue
        for index in range(max_cols):
            value = row[index + 1].strip() if index + 1 < len(row) else ""
            companies[index][mapped_key] = parse_number(value)

    _finalize_companies(companies)
    target = companies[0] if companies else {}
    peers = list(companies[1 : 1 + PEER_COUNT])
    return target, peers


def validate_non_negative(label: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{label}は0以上の値を入力してください。")


def validate_company_input(company: Dict[str, float], *, include_sales: bool = True) -> None:
    keys = [
        ("時価総額", company.get("market_cap", 0.0)),
        ("純利益", company.get("net_income", 0.0)),
        ("純資産", company.get("net_assets", 0.0)),
        ("営業利益", company.get("operating_income", 0.0)),
        ("減価償却費", company.get("depreciation", 0.0)),
        ("有利子負債", company.get("sub_debt", 0.0)),
        ("現預金", company.get("cash", 0.0)),
    ]
    if include_sales:
        keys.insert(1, ("売上高", company.get("sales", 0.0)))

    for label, value in keys:
        validate_non_negative(label, value)


def calculate_metrics(company: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Calculate the core valuation multiples for one company."""

    validate_company_input(company)

    market_cap = company.get("market_cap", 0.0)
    sales = company.get("sales", 0.0)
    net_income = company.get("net_income", 0.0)
    net_assets = company.get("net_assets", 0.0)
    operating_income = company.get("operating_income", 0.0)
    depreciation = company.get("depreciation", 0.0)
    sub_debt = company.get("sub_debt", 0.0)
    cash = company.get("cash", 0.0)

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
    """Apply peer multiples to the target company and summarize each method."""

    validate_company_input(target)
    for peer in peers:
        validate_company_input(peer)

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


def calculate_dcf_valuation(
    target: Dict[str, float],
    forecast_years: int,
    growth_rate_pct: float,
    discount_rate_pct: float,
    terminal_growth_rate_pct: float,
) -> Dict[str, Any]:
    """Calculate a simple DCF valuation from manually entered assumptions."""

    validate_company_input(target, include_sales=True)
    if forecast_years < 5 or forecast_years > 10:
        raise ValueError("予測期間は5年から10年の範囲で入力してください。")

    discount_rate = discount_rate_pct / 100.0
    terminal_growth_rate = terminal_growth_rate_pct / 100.0
    growth_rate = growth_rate_pct / 100.0

    if discount_rate <= terminal_growth_rate:
        raise ValueError("割引率は永久成長率より大きく設定してください。")
    if discount_rate <= -1.0:
        raise ValueError("割引率は-100%より大きい値を入力してください。")
    if terminal_growth_rate <= -1.0:
        raise ValueError("永久成長率は-100%より大きい値を入力してください。")

    base_fcf = target.get("operating_income", 0.0) + target.get("depreciation", 0.0)
    forecast_rows: List[Dict[str, float]] = []
    pv_total = 0.0

    for year in range(1, forecast_years + 1):
        fcf = base_fcf * ((1.0 + growth_rate) ** year)
        present_value = fcf / ((1.0 + discount_rate) ** year)
        pv_total += present_value
        forecast_rows.append(
            {
                "year": float(year),
                "fcf": fcf,
                "discount_factor": 1.0 / ((1.0 + discount_rate) ** year),
                "present_value": present_value,
            }
        )

    terminal_fcf = base_fcf * ((1.0 + growth_rate) ** forecast_years)
    terminal_value = terminal_fcf * (1.0 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
    pv_terminal_value = terminal_value / ((1.0 + discount_rate) ** forecast_years)
    enterprise_value = pv_total + pv_terminal_value
    equity_value = enterprise_value + target.get("cash", 0.0) - target.get("sub_debt", 0.0)

    return {
        "base_fcf": base_fcf,
        "forecast_years": forecast_years,
        "growth_rate_pct": growth_rate_pct,
        "discount_rate_pct": discount_rate_pct,
        "terminal_growth_rate_pct": terminal_growth_rate_pct,
        "forecast_rows": forecast_rows,
        "pv_fcf_total": pv_total,
        "terminal_fcf": terminal_fcf,
        "terminal_value": terminal_value,
        "pv_terminal_value": pv_terminal_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "net_debt": target.get("sub_debt", 0.0) - target.get("cash", 0.0),
    }


def _format_amount(value: float) -> str:
    return f"{value:,.0f}"


def _metric_value(value: Optional[float]) -> str:
    if value is None:
        return "算定不可"
    return _format_amount(value)


def _method_summary_rows(ranges: Dict[str, Dict[str, Any]], methods: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for method in methods:
        stats = ranges.get(method)
        rows.append(
            {
                "手法": DISPLAY_METHOD_LABELS[method],
                "Min": None if stats is None else stats["min"],
                "Max": None if stats is None else stats["max"],
                "平均値": None if stats is None else stats["avg"],
            }
        )
    return rows


def _render_company_inputs(
    title: str,
    prefix: str,
    defaults: Dict[str, float],
    *,
    show_market_cap: bool,
) -> Dict[str, float]:
    st.subheader(title)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        market_cap = st.number_input(
            "時価総額",
            min_value=0.0,
            value=float(defaults.get("market_cap", 0.0)),
            step=1000.0,
            key=f"{prefix}_market_cap",
            disabled=not show_market_cap,
        )
        net_income = st.number_input(
            "純利益",
            min_value=0.0,
            value=float(defaults.get("net_income", 0.0)),
            step=100.0,
            key=f"{prefix}_net_income",
        )

    with col2:
        net_assets = st.number_input(
            "純資産",
            min_value=0.0,
            value=float(defaults.get("net_assets", 0.0)),
            step=1000.0,
            key=f"{prefix}_net_assets",
        )
        operating_income = st.number_input(
            "営業利益",
            min_value=0.0,
            value=float(defaults.get("operating_income", 0.0)),
            step=100.0,
            key=f"{prefix}_operating_income",
        )

    with col3:
        depreciation = st.number_input(
            "減価償却費",
            min_value=0.0,
            value=float(defaults.get("depreciation", 0.0)),
            step=100.0,
            key=f"{prefix}_depreciation",
        )
        sub_debt = st.number_input(
            "有利子負債",
            min_value=0.0,
            value=float(defaults.get("sub_debt", 0.0)),
            step=1000.0,
            key=f"{prefix}_sub_debt",
        )

    with col4:
        cash = st.number_input(
            "現預金",
            min_value=0.0,
            value=float(defaults.get("cash", 0.0)),
            step=1000.0,
            key=f"{prefix}_cash",
        )

    company = {
        "market_cap": float(market_cap),
        "sales": float(defaults.get("sales", 0.0)),
        "net_income": float(net_income),
        "net_assets": float(net_assets),
        "operating_income": float(operating_income),
        "depreciation": float(depreciation),
        "sub_debt": float(sub_debt),
        "cash": float(cash),
    }
    if not show_market_cap:
        company["market_cap"] = float(defaults.get("market_cap", 0.0))
    return company


def _render_input_tab() -> None:
    st.header("データ入力ページ")
    st.write("評価対象企業と類似企業5社の財務データを入力してください。売上高は入力不要です。")

    default_target = st.session_state.get(
        "default_target",
        {
            "market_cap": 250000.0,
            "net_income": 12000.0,
            "net_assets": 180000.0,
            "operating_income": 15000.0,
            "depreciation": 5000.0,
            "sub_debt": 40000.0,
            "cash": 30000.0,
            "sales": 0.0,
        },
    )
    default_peers = st.session_state.get(
        "default_peers",
        [
            {
                "market_cap": 300000.0 + 10000.0 * index,
                "net_income": 10000.0 + 500.0 * index,
                "net_assets": 160000.0 + 5000.0 * index,
                "operating_income": 14000.0 + 400.0 * index,
                "depreciation": 4500.0 + 100.0 * index,
                "sub_debt": 35000.0 + 1000.0 * index,
                "cash": 25000.0 + 800.0 * index,
                "sales": 0.0,
            }
            for index in range(PEER_COUNT)
        ],
    )

    target = _render_company_inputs("評価対象企業", "target", default_target, show_market_cap=True)
    peers: List[Dict[str, float]] = []
    st.subheader("類似企業 5社")
    for index in range(PEER_COUNT):
        peer_defaults = default_peers[index] if index < len(default_peers) else _empty_company()
        with st.expander(f"類似企業 {index + 1}", expanded=index == 0):
            peer = _render_company_inputs(
                f"類似企業 {index + 1}",
                f"peer_{index + 1}",
                peer_defaults,
                show_market_cap=True,
            )
            peers.append(peer)

    st.session_state["current_target"] = target
    st.session_state["current_peers"] = peers


def _render_assumption_tab() -> None:
    st.header("前提入力ページ")
    st.write("DCF法に使う予測期間、成長率、割引率、永久成長率を設定してください。")

    default_assumptions = st.session_state.get(
        "default_assumptions",
        {
            "forecast_years": DEFAULT_FORECAST_YEARS,
            "growth_rate_pct": 4.0,
            "discount_rate_pct": 7.0,
            "terminal_growth_rate_pct": 1.0,
        },
    )

    col1, col2 = st.columns(2)
    with col1:
        forecast_years = st.slider(
            "予測期間",
            min_value=5,
            max_value=10,
            value=int(default_assumptions.get("forecast_years", DEFAULT_FORECAST_YEARS)),
            step=1,
            key="forecast_years",
        )
        growth_rate_pct = st.number_input(
            "年間FCF成長率（%）",
            value=float(default_assumptions.get("growth_rate_pct", 4.0)),
            step=0.1,
            format="%.1f",
            key="growth_rate_pct",
        )
    with col2:
        discount_rate_pct = st.number_input(
            "割引率（WACC相当、%）",
            value=float(default_assumptions.get("discount_rate_pct", 7.0)),
            step=0.1,
            format="%.1f",
            key="discount_rate_pct",
        )
        terminal_growth_rate_pct = st.number_input(
            "永久成長率（%）",
            value=float(default_assumptions.get("terminal_growth_rate_pct", 1.0)),
            step=0.1,
            format="%.1f",
            key="terminal_growth_rate_pct",
        )

    st.session_state["current_assumptions"] = {
        "forecast_years": int(forecast_years),
        "growth_rate_pct": float(growth_rate_pct),
        "discount_rate_pct": float(discount_rate_pct),
        "terminal_growth_rate_pct": float(terminal_growth_rate_pct),
    }


def _render_comps_results(ranges: Dict[str, Dict[str, Any]]) -> None:
    st.subheader("類似企業比較法の結果")
    rows = _method_summary_rows(ranges, DISPLAY_METHOD_ORDER)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    for method in DISPLAY_METHOD_ORDER:
        stats = ranges.get(method)
        with st.container():
            st.markdown(f"#### {DISPLAY_METHOD_LABELS[method]}")
            col_min, col_max, col_avg = st.columns(3)
            with col_min:
                st.metric("Min", _metric_value(None if stats is None else stats["min"]))
            with col_max:
                st.metric("Max", _metric_value(None if stats is None else stats["max"]))
            with col_avg:
                st.metric("平均値", _metric_value(None if stats is None else stats["avg"]))


def _render_dcf_results(dcf_result: Dict[str, Any]) -> None:
    st.subheader("DCF法の結果")
    st.metric("DCFによる推定株式価値", _format_amount(float(dcf_result["equity_value"])))

    forecast_rows = dcf_result.get("forecast_rows", [])
    if forecast_rows:
        st.write("予測FCFの現在価値化")
        st.dataframe(forecast_rows, use_container_width=True, hide_index=True)

    summary_rows = [
        {"項目": "直近FCF", "値": dcf_result["base_fcf"]},
        {"項目": "割引後FCF合計", "値": dcf_result["pv_fcf_total"]},
        {"項目": "ターミナルバリュー", "値": dcf_result["terminal_value"]},
        {"項目": "割引後TV", "値": dcf_result["pv_terminal_value"]},
        {"項目": "事業価値（EV）", "値": dcf_result["enterprise_value"]},
        {"項目": "ネットデット", "値": dcf_result["net_debt"]},
    ]
    st.dataframe(summary_rows, use_container_width=True, hide_index=True)


def _render_result_tab() -> None:
    st.header("評価結果ページ")
    st.write("計算実行ボタンを押すと、類似企業比較法とDCF法の結果を表示します。")

    compute_clicked = st.button("計算実行", type="primary")
    if compute_clicked:
        target = st.session_state.get("current_target")
        peers = st.session_state.get("current_peers")
        assumptions = st.session_state.get("current_assumptions")

        if not target or not peers or not assumptions:
            st.error("まずデータ入力ページと前提入力ページを設定してください。")
            return

        try:
            ranges = compute_valuation_range(target, peers)
            dcf_result = calculate_dcf_valuation(
                target,
                forecast_years=int(assumptions["forecast_years"]),
                growth_rate_pct=float(assumptions["growth_rate_pct"]),
                discount_rate_pct=float(assumptions["discount_rate_pct"]),
                terminal_growth_rate_pct=float(assumptions["terminal_growth_rate_pct"]),
            )
        except Exception as exc:
            st.error(f"エラーが発生しました: {exc}")
            return

        st.session_state["last_result"] = {
            "ranges": ranges,
            "dcf_result": dcf_result,
        }

    last_result = st.session_state.get("last_result")
    if not last_result:
        st.info("まだ計算結果がありません。各ページを入力してから計算実行を押してください。")
        return

    # 結果を2つに分離して表示：Comps（類似企業比較）とDCF
    result_tabs = st.tabs(["類似企業比較（Comps）", "DCF法"])
    with result_tabs[0]:
        _render_comps_results(last_result["ranges"])
    with result_tabs[1]:
        _render_dcf_results(last_result["dcf_result"])


def render_app() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.write(APP_DESCRIPTION)

    tabs = st.tabs(["データ入力ページ", "前提入力ページ", "評価結果ページ"])
    with tabs[0]:
        _render_input_tab()
    with tabs[1]:
        _render_assumption_tab()
    with tabs[2]:
        _render_result_tab()


def main() -> None:
    if st is None:
        raise RuntimeError("Streamlitがインストールされていません。")
    render_app()


if __name__ == "__main__":
    main()