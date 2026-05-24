# valuartion-auto

バリュエーションの自動化アプリ開発

## セットアップ

```bash
pip install streamlit
```

## 起動方法

```bash
streamlit run /home/runner/work/valuartion-auto/valuartion-auto/app.py
```

## 概要

- 類似企業比較法（マルチプル法）の簡易版アプリです
- 類似企業3社の PER を計算し、平均 PER を使って評価対象企業の推定企業価値を表示します
- ゼロ除算や不正な入力値を避けるための例外処理を含みます
