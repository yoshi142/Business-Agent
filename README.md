# Business-Agent

元手10万円から、中小企業向け “AI 業務自動化サービス” を立ち上げ、累計売上1,000万円を目指すための運営一式。

- 事業計画・価格表・営業の手引き・納品手順・開業時の整理（docs/）
- 営業の入口になる「業務自動化診断ツール」（CLI と Web 画面。API キー無しでも動く）
- 元手から目標までの進捗を記録する台帳とダッシュボード（ledger/）
- サービス案内ページ（site/）

## 第1関門：90日スプリント

| 項目 | 値 |
|------|----|
| 期間 | 2026-10-22 〜 2027-01-20 |
| 合格条件 | 期間内の売上 3万円以上 |
| AI 利用料の上限 | 3万円 |
| 確認 | `python -m bizagent ledger sprint` |

最短の道筋は、1万円・当日納品の入口商品（SNS 投稿案、口コミ返信案、問い合わせ返信テンプレート）を3件売ることである。
手順と文面は docs/07_sprint_90days.md、生成コマンドは下記「入口商品」を参照。

## 前提の確認

「10万円を1,000万円に」は100倍である。金融商品で再現性のある手段は無いため、本リポジトリでは
“10万円を開業資金として使い、事業の累計売上として1,000万円を目指す” と解釈している。理由と検討した代替案は docs/00_premise.md にある。
売上は保証できない。営業と納品は依頼者の行動が必要である。

## 構成

```
docs/
  00_premise.md         前提：なぜ投資ではなく事業か。選んだ事業と見送った案
  01_plan.md            10万円の使い道、商品の三段階、90日計画、18か月の目安
  02_offers.md          商品・価格表、見積と契約の骨子
  03_sales_playbook.md  対象顧客、接触経路、週の行動量、文面の雛形、反論への答え
  04_delivery.md        納品の手順、標準構成、効果測定、流用の仕方
  05_legal_tax.md       開業届、青色申告、インボイス、契約、Web 表示（要確認事項）
  06_weekly_review.md   週次レビューの記入欄と判断の規則
  07_sprint_90days.md   90日スプリント：入口商品3種、日程、文面、判定の扱い
  templates/            契約骨子、提案書、失注理由の記録
bizagent/
  diagnose.py           診断エンジン（規則ベース／Claude API）とレポート整形
  data/recipes.json     自動化レシピ15件（営業資料と診断の元データ）
  ledger.py             台帳の集計、90日スプリント判定、到達予測、ダッシュボード HTML
  mini.py               入口商品の生成（SNS 投稿案／口コミ返信案／問い合わせテンプレート）
  usage.py              API 利用量と概算費用（円）の記録
  web.py                診断フォームとサービス案内の Web 画面（FastAPI）
  cli.py                コマンドライン入口
ledger/ledger.csv       台帳（初期値：2026-10-22 元手 100,000 円）
ledger/api_usage.csv    API 利用量の記録（ツールが自動生成）
site/index.html         サービス案内ページ
examples/               入力例と生成したレポート例
tests/                  pytest（17件）
```

## 使い方

```bash
pip install -r requirements.txt

# 診断（API キーが無ければ規則ベースの簡易診断で動く）
python -m bizagent diagnose --json examples/sample_input.json
python -m bizagent diagnose --interactive --out report.md

# Claude API で診断する場合（任意）
export ANTHROPIC_API_KEY=...
python -m bizagent diagnose --json examples/sample_input.json --engine claude

# Web 画面（診断フォーム http://127.0.0.1:8000 、案内ページ /site）
python -m bizagent serve

# 入口商品（Claude API が必要。--dry-run で API を呼ばず概算費用だけ表示）
python -m bizagent mini --dry-run sns --json examples/mini_shop.json
python -m bizagent mini sns --json examples/mini_shop.json                       # deliverables/sns_posts.csv, .md
python -m bizagent mini reviews --csv examples/mini_reviews.csv --name 喫茶ひだまり --business カフェ
python -m bizagent mini inquiry --json examples/mini_business.json

# 台帳（status の先頭に90日スプリントの判定が出る）
python -m bizagent ledger sprint
python -m bizagent ledger add --kind income --category 入口商品 --amount 10000 --memo "○○店 SNS 11月分"
python -m bizagent ledger add --kind expense --category AI利用料 --amount 1500 --memo "Claude Code 10月分"
python -m bizagent ledger status
python -m bizagent ledger dashboard      # ledger/dashboard.html を生成

# テスト
python -m pytest -q
```

## 診断ツールの2つのエンジン

| エンジン | 条件 | 用途 |
|---------|------|------|
| heuristic | 既定。API キー不要 | 営業デモ、動作確認、レシピの検証 |
| claude | ANTHROPIC_API_KEY があると自動選択。モデルは claude-opus-5-5（BIZAGENT_MODEL で変更可） | 顧客向けレポートのたたき台 |

claude エンジンと入口商品の生成は構造化出力（pydantic モデル）で結果を受け取り、1回ごとの API 費を ledger/api_usage.csv に概算記録する（1回あたり数十円）。本セッションでは API キーが無かったため、API を呼ぶ部分は実際の API に対して未検証である。初回利用時に examples/sample_input.json で動作を確認すること。
いずれのエンジンでも、数字は目安であり、ヒアリングで補正して使う前提である。

## 最初の1週間でやること

1. docs/07_sprint_90days.md を読む。
2. ANTHROPIC_API_KEY を設定し、examples/ の入力例で入口商品3種を1回ずつ生成して流れを確かめる（API 費は合計100円以下）。
3. 知っている店・事業者を20件書き出し、3件に入口商品のサンプルを無料で作って渡す。
4. docs/05_legal_tax.md を見て、開業届と青色申告承認申請書を出す。
5. 週末に `python -m bizagent ledger sprint` を実行し、docs/06_weekly_review.md を埋める。

## 注意

- docs/05_legal_tax.md の制度に関する記述は一般的な整理であり、提出前に公式情報で確認が必要である。
- 台帳は進捗管理用であり、税務上の帳簿ではない。
