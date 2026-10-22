# Business-Agent

元手10万円から、中小企業向け “AI 業務自動化サービス” を立ち上げ、累計売上1,000万円を目指すための運営一式。

- 事業計画・価格表・営業の手引き・納品手順・開業時の整理（docs/）
- 営業の入口になる「業務自動化診断ツール」（CLI と Web 画面。API キー無しでも動く）
- 元手から目標までの進捗を記録する台帳とダッシュボード（ledger/）
- サービス案内ページ（site/）

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
  templates/            契約骨子、提案書、失注理由の記録
bizagent/
  diagnose.py           診断エンジン（規則ベース／Claude API）とレポート整形
  data/recipes.json     自動化レシピ15件（営業資料と診断の元データ）
  ledger.py             台帳の集計、到達予測、ダッシュボード HTML
  web.py                診断フォームとサービス案内の Web 画面（FastAPI）
  cli.py                コマンドライン入口
ledger/ledger.csv       台帳（初期値：2026-10-22 元手 100,000 円）
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

# 台帳
python -m bizagent ledger add --kind income --category 診断 --amount 30000 --memo "A社"
python -m bizagent ledger add --kind expense --category ドメイン --amount 1500
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

claude エンジンは構造化出力（pydantic モデル）で結果を受け取る。本セッションでは API キーが無かったため、claude エンジンは実際の API に対して未検証である。初回利用時に examples/sample_input.json で動作を確認すること。
いずれのエンジンでも、数字は目安であり、ヒアリングで補正して使う前提である。

## 最初の1週間でやること

1. docs/00_premise.md と 01_plan.md を読み、同意できない点があれば直す（自分の事業計画にする）。
2. docs/05_legal_tax.md を見て、開業届と青色申告承認申請書を出す。
3. site/index.html のフッターに事業者情報を入れ、公開する。
4. 知人3社に無料診断を行う。`python -m bizagent diagnose --interactive` でたたき台を作り、ヒアリングで補正する。
5. 週末に docs/06_weekly_review.md を埋め、台帳を更新する。

## 注意

- docs/05_legal_tax.md の制度に関する記述は一般的な整理であり、提出前に公式情報で確認が必要である。
- 台帳は進捗管理用であり、税務上の帳簿ではない。
