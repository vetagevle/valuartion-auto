# valuartion-auto

バリュエーションの自動化アプリ開発

## セットアップ

```bash
pip install streamlit
```

必要に応じて仮想環境を作成し、依存をインストールしてください。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # または pip install streamlit pytest
```

## 起動方法

```bash
streamlit run app.py
```

## CSV一括読み込みテンプレート

所定フォーマットのCSVを使って Target（1行目）と複数のComps（以降最大15行）を一括読み込みできます。サンプルテンプレートを同梱しています:

- [comps_template.csv](comps_template.csv)

注意: CSV内の金額項目は「百万円」単位で記載してください（例：1000 は 1000 百万円 = 1,000,000,000 円 を意味します）。

補足: Excel形式（.xlsx）でも同じヘッダー構成で読み込み可能です。Excelを使う場合も金額は百万円単位で入力してください。

ヘッダーは次の列（順序・名称を厳守）です:

company_name, market_cap, shares_outstanding, cash, sub_debt, minority, sales_ltm, sales_cy1, sales_cy2, ebitda_ltm, ebitda_cy1, ebitda_cy2, ebit_ltm, ebit_cy1, ebit_cy2, net_income_ltm, net_income_cy1, net_income_cy2

1行目がTarget、2行目以降がCompsです。空欄は0として扱われます。

入力専用ページを使う場合:

```bash
streamlit run input_page.py
```

または開発中に直接 Python でテスト実行を行う方法:

ユニットテスト（pytest）:

```bash
# プロジェクトルートで
PYTHONPATH=. pytest -q
```

標準ライブラリの unittest を使う場合:

```bash
python -m unittest discover -v
```

## 概要

- 類似企業比較法とDCF法をまとめた企業価値評価アプリです
- 画面は「データ入力」「前提入力」「評価結果」の3タブで構成されています
- 評価対象企業と類似企業5社の手入力データをもとに、PER, PBR, EV/EBITDA, EV/EBIT のレンジを表示します
- DCF法は直近FCFを営業利益 + 減価償却費で近似し、予測FCF、TV、EV、株式価値を算定します
- ゼロ除算や不正な入力値を避けるための例外処理を含みます
