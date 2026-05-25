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
