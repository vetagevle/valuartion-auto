"""Standalone Streamlit page for entering financial statements (target + peers).
Saves the entered data to `data/loaded_financials.json`.
"""
import os
import json
import csv
import io
from typing import List, Dict

import streamlit as st

from app import (
    PEER_COUNT,
    NEEDED_KEYS,
    normalize_key,
    parse_number,
    parse_pasted_statement,
    parse_statement_style_csv,
)


OUT_PATH = os.path.join("data", "loaded_financials.json")


def ensure_output_dir():
    d = os.path.dirname(OUT_PATH)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def save_data(target: Dict[str, float], peers: List[Dict[str, float]]):
    ensure_output_dir()
    obj = {"target": target, "peers": peers}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def conv_row_to_company(row: Dict[str, str]) -> Dict[str, float]:
    out = {}
    for k, v in row.items():
        nk = normalize_key(k) or k
        out[nk] = parse_number(v)
    for kk in NEEDED_KEYS:
        out.setdefault(kk, 0.0)
    return out


def main():
    st.set_page_config(page_title="財務データ入力ページ", layout="wide")
    st.title("財務データ入力ページ")

    mode = st.radio("入力モードを選択してください", ("手入力フォーム", "貼付け（行形式）", "ファイルアップロード"))

    if mode == "手入力フォーム":
        st.header("評価対象企業（手入力）")
        t_sl = st.number_input("売上高", min_value=0.0, value=2000.0, step=1.0)
        t_ni = st.number_input("純利益", min_value=0.0, value=500.0, step=1.0)
        t_na = st.number_input("純資産", min_value=0.0, value=6000.0, step=1.0)
        t_oi = st.number_input("営業利益", min_value=0.0, value=700.0, step=1.0)
        t_dep = st.number_input("減価償却費", min_value=0.0, value=300.0, step=1.0)
        t_debt = st.number_input("有利子負債", min_value=0.0, value=2000.0, step=1.0)
        t_cash = st.number_input("現預金", min_value=0.0, value=1500.0, step=1.0)
        target = {"sales": t_sl, "net_income": t_ni, "net_assets": t_na, "operating_income": t_oi, "depreciation": t_dep, "sub_debt": t_debt, "cash": t_cash}

        st.header("類似企業（手入力）")
        peers = []
        cols = st.columns(PEER_COUNT)
        for i in range(PEER_COUNT):
            with cols[i]:
                st.subheader(f"類似{i+1}")
                p_mc = st.number_input(f"時価総額_{i+1}", min_value=0.0, value=10000.0*(i+1), key=f"mc_{i}")
                p_sl = st.number_input(f"売上高_{i+1}", min_value=0.0, value=3000.0*(i+1), key=f"sl_{i}")
                p_ni = st.number_input(f"純利益_{i+1}", min_value=0.0, value=600.0*(i+1), key=f"ni_{i}")
                p_na = st.number_input(f"純資産_{i+1}", min_value=0.0, value=7000.0*(i+1), key=f"na_{i}")
                p_oi = st.number_input(f"営業利益_{i+1}", min_value=0.0, value=800.0*(i+1), key=f"oi_{i}")
                p_dep = st.number_input(f"減価償却_{i+1}", min_value=0.0, value=350.0*(i+1), key=f"dep_{i}")
                p_debt = st.number_input(f"有利子負債_{i+1}", min_value=0.0, value=2500.0*(i+1), key=f"debt_{i}")
                p_cash = st.number_input(f"現預金_{i+1}", min_value=0.0, value=1800.0*(i+1), key=f"cash_{i}")
                peers.append({"market_cap": p_mc, "sales": p_sl, "net_income": p_ni, "net_assets": p_na, "operating_income": p_oi, "depreciation": p_dep, "sub_debt": p_debt, "cash": p_cash})

        if st.button("保存"):
            save_data(target, peers)
            st.success(f"保存しました: {OUT_PATH}")

    elif mode == "貼付け（行形式）":
        st.write("1行目が項目名、以降が会社の列（対象企業が最初）になっている行形式のCSVを貼り付けてください。")
        sample = "売上高,2000,3000,4000,5000,6000\n営業利益,700,800,900,1000,1100\n純利益,500,600,700,800,900"
        pasted = st.text_area("財務諸表を貼付け", value=sample, height=200)
        if st.button("解析して保存"):
            t, p = parse_pasted_statement(pasted)
            save_data(t, p)
            st.success(f"保存しました: {OUT_PATH}")

    else:  # ファイルアップロード
        st.write("CSV または JSON をアップロードできます。CSV は行形式（項目×会社）か、会社ごとの行形式のどちらにも対応します。")
        uploaded = st.file_uploader("ファイルを選択", type=["csv", "json"])
        if uploaded is not None:
            raw = uploaded.read()
            if uploaded.name.lower().endswith('.json'):
                data = json.loads(raw.decode('utf-8'))
                if isinstance(data, dict) and 'target' in data:
                    t = data['target']
                    p = data.get('peers', [])
                elif isinstance(data, list) and len(data) >= 1:
                    t = data[0]
                    p = data[1:1+PEER_COUNT]
                else:
                    st.error("JSON 形式が期待値と異なります。")
                    t, p = {}, []
            else:
                s = raw.decode('utf-8')
                reader = csv.DictReader(io.StringIO(s))
                fn = reader.fieldnames or []
                first_hdr = fn[0] if fn else ''
                if first_hdr in ("項目", "item", "label") or all(not normalize_key(h) for h in fn if h):
                    t, p = parse_statement_style_csv(reader)
                else:
                    rows = [r for r in reader]
                    if rows:
                        t = conv_row_to_company(rows[0])
                        p = [conv_row_to_company(r) for r in rows[1:1+PEER_COUNT]]
                    else:
                        t, p = {}, []

            if st.button("アップロード内容を保存"):
                save_data(t, p)
                st.success(f"保存しました: {OUT_PATH}")


if __name__ == "__main__":
    main()
