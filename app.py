"""Streamlit app for simple comparable company valuation."""

from typing import Dict, List

try:
    import streamlit as st
except ModuleNotFoundError:  # pragma: no cover - handled for local test imports
    st = None


APP_TITLE = "企業価値評価（類似企業比較法）"
APP_DESCRIPTION = (
    "評価対象企業の純利益と、類似企業3社の時価総額・純利益を入力すると、"
    "平均PERを使って推定企業価値を自動計算します。"
)
PIP_INSTALL_COMMAND = "pip install streamlit"
PEER_COUNT = 3


def validate_non_negative_number(label: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{label}は0以上の値を入力してください。")


def calculate_per(market_cap: float, net_income: float) -> float:
    validate_non_negative_number("時価総額", market_cap)
    if net_income == 0:
        raise ZeroDivisionError("類似企業の純利益が0のため、PERを計算できません。")
    if net_income < 0:
        raise ValueError("類似企業の純利益は0より大きい値を入力してください。")
    return market_cap / net_income


def calculate_average_per(peer_companies: List[Dict[str, float]]) -> float:
    if len(peer_companies) != PEER_COUNT:
        raise ValueError(f"類似企業は{PEER_COUNT}社分入力してください。")

    per_values = [
        calculate_per(company["market_cap"], company["net_income"])
        for company in peer_companies
    ]
    return sum(per_values) / len(per_values)


def estimate_company_value(
    target_net_income: float, peer_companies: List[Dict[str, float]]
) -> Dict[str, float | List[float]]:
    validate_non_negative_number("評価対象企業の純利益", target_net_income)

    per_values = [
        calculate_per(company["market_cap"], company["net_income"])
        for company in peer_companies
    ]
    average_per = calculate_average_per(peer_companies)

    return {
        "peer_pers": per_values,
        "average_per": average_per,
        "estimated_company_value": average_per * target_net_income,
    }


def format_amount(value: float) -> str:
    return f"{value:,.2f}"


def render_app() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="centered")
    st.title(APP_TITLE)
    st.write(APP_DESCRIPTION)
    st.caption(f"必要ライブラリのインストール: `{PIP_INSTALL_COMMAND}`")
    st.info("※ 金額はすべて同じ単位（例: 百万円）で入力してください。")

    with st.form("valuation_form"):
        target_net_income = st.number_input(
            "評価対象企業の純利益",
            min_value=0.0,
            value=100.0,
            step=1.0,
        )

        peer_companies: List[Dict[str, float]] = []
        for index in range(1, PEER_COUNT + 1):
            st.subheader(f"類似企業 {index}")
            market_cap_col, net_income_col = st.columns(2)
            with market_cap_col:
                market_cap = st.number_input(
                    f"類似企業{index}の時価総額",
                    min_value=0.0,
                    value=1000.0 * index,
                    step=1.0,
                    key=f"market_cap_{index}",
                )
            with net_income_col:
                net_income = st.number_input(
                    f"類似企業{index}の純利益",
                    min_value=0.0,
                    value=100.0 * index,
                    step=1.0,
                    key=f"net_income_{index}",
                )
            peer_companies.append(
                {"market_cap": market_cap, "net_income": net_income}
            )

        submitted = st.form_submit_button("推定企業価値を計算")

    if not submitted:
        return

    try:
        result = estimate_company_value(target_net_income, peer_companies)
    except ZeroDivisionError as error:
        st.error(str(error))
    except ValueError as error:
        st.error(str(error))
    except Exception:
        st.error("計算中に予期しないエラーが発生しました。入力値を確認してください。")
    else:
        st.success("推定企業価値を計算しました。")
        st.metric("平均PER", f"{result['average_per']:.2f}倍")
        st.metric(
            "推定企業価値",
            format_amount(result["estimated_company_value"]),
        )
        st.write(
            "各類似企業のPER:",
            ", ".join(f"{per_value:.2f}倍" for per_value in result["peer_pers"]),
        )


def main() -> None:
    if st is None:
        raise RuntimeError(
            "Streamlit がインストールされていません。"
            f" 先に `{PIP_INSTALL_COMMAND}` を実行してください。"
        )
    render_app()


if __name__ == "__main__":
    main()
