"""入口商品（1万円・当日納品）の納品物を生成する。

  sns      : 店舗・商品情報から1か月分（30本）の SNS 投稿案
  reviews  : 口コミ一覧から返信文の下書きと傾向の要約
  inquiry  : 業務内容から、よくある問い合わせへの返信テンプレート10種

いずれも Claude API を使う（文章生成は規則ベースでは品質が出ないため）。
--dry-run で、API を呼ばずに入力の確認と概算費用だけを表示できる。
"""

from __future__ import annotations

import csv
import json
import os
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .usage import estimate_cost, record_usage

DEFAULT_MODEL = os.environ.get("BIZAGENT_MODEL", "claude-opus-5-5")


# ---------- 1. SNS 投稿案 ----------


class ShopInfo(BaseModel):
    name: str
    business: str = Field(description="業態（例：カフェ、整骨院、工務店）")
    area: str = Field(default="", description="地域")
    features: str = Field(description="売り・こだわり・メニューなど")
    target: str = Field(default="", description="来てほしい客層")
    tone: str = Field(default="丁寧で親しみやすい", description="文体")
    platform: str = Field(default="Instagram", description="投稿先")
    month: str = Field(default_factory=lambda: date.today().strftime("%Y-%m"), description="対象月 YYYY-MM")
    events: str = Field(default="", description="その月の予定・キャンペーン・季節の話題")


class Post(BaseModel):
    day: int = Field(ge=1, le=31)
    theme: str
    text: str = Field(description="投稿本文。150〜300字")
    hashtags: list[str]
    image_idea: str = Field(description="添える写真の案")


class PostPlan(BaseModel):
    shop_name: str
    month: str
    posts: list[Post] = Field(description="30本。日付順")
    notes: list[str] = Field(description="運用上の注意（投稿時間、返信の仕方など）3件")


SNS_SYSTEM = """あなたは日本の小規模店舗の SNS 運用を代行する担当者です。
指定された店舗の1か月分の投稿案を30本作ってください。
- 同じ話題を続けない。商品紹介・お客様の声風・舞台裏・季節・お知らせ・豆知識を混ぜる。
- 誇大表現（日本一、最高、絶対）と、根拠の無い効能表現は使わない。
- 本文は150〜300字。ハッシュタグは5〜10個で、地域名と業態を必ず含める。
- 店が提供していないことを書かない。情報が足りない場合は無難な内容にし、notes で確認を促す。"""


# ---------- 2. 口コミ返信 ----------


class Review(BaseModel):
    id: str
    rating: int = Field(ge=1, le=5)
    text: str
    date: str = ""


class ReviewReply(BaseModel):
    id: str
    rating: int
    reply: str = Field(description="返信文。100〜250字")
    needs_attention: bool = Field(description="店側の確認・対応が必要か（低評価や事実確認が要るもの）")
    reason: str = Field(description="needs_attention の理由。不要なら空")


class ReviewReplyPlan(BaseModel):
    shop_name: str
    replies: list[ReviewReply]
    summary: str = Field(description="口コミ全体の傾向。良い点・不満の多い点を3〜5文で")
    improvements: list[str] = Field(description="不満から読み取れる改善候補。最大5件")


REVIEW_SYSTEM = """あなたは日本の小規模店舗の口コミ返信を担当しています。
- 返信は、感謝 → 具体的に触れる → 次につなげる、の順で100〜250字。定型文に見えないよう、口コミの内容に触れる。
- 低評価には、言い訳をせず、事実確認と改善の姿勢を示す。店側で確認が要る場合は needs_attention を true にする。
- 個人情報や、店が約束できない補償（返金など）は書かない。
- 店の名前・業態・文体の指定に従う。"""


# ---------- 3. 問い合わせ返信テンプレート ----------


class BusinessInfo(BaseModel):
    name: str
    business: str
    description: str = Field(description="業務内容・営業時間・対応範囲など")
    tone: str = Field(default="丁寧", description="文体")
    channels: str = Field(default="メール", description="問い合わせの経路（メール、LINE、フォーム）")


class InquiryTemplate(BaseModel):
    situation: str = Field(description="どんな問い合わせに使うか")
    subject: str = Field(description="件名（メール用）")
    body: str = Field(description="本文。差し込み箇所は {{お名前}} のように書く")
    followup: str = Field(description="返信後に店側がやること。無ければ空")


class InquiryTemplateSet(BaseModel):
    business_name: str
    templates: list[InquiryTemplate] = Field(description="10種")
    usage_notes: list[str] = Field(description="使い方の注意。3件")


INQUIRY_SYSTEM = """あなたは日本の小規模事業者の顧客対応を整える担当者です。
業務内容から、実際に来そうな問い合わせを10種類想定し、それぞれに返信テンプレートを作ってください。
- 想定する問い合わせ：料金、空き状況・予約、対応範囲、所要時間、キャンセル、支払方法、アクセス、クレーム一次対応、見積依頼、求人応募 など業種に合わせて選ぶ。
- 本文は200〜400字。差し込み箇所は {{お名前}} {{日時}} のように明示する。
- 事業者が提供していないサービスを約束しない。不明な点は {{要確認}} と書く。
- 指定された文体と経路（LINE なら短めに）に合わせる。"""


# ---------- 共通 ----------


def _read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_reviews_csv(path: str | Path) -> list[Review]:
    with Path(path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    reviews = []
    for i, r in enumerate(rows, 1):
        reviews.append(
            Review(
                id=str(r.get("id") or i),
                rating=int(r.get("rating") or 3),
                text=(r.get("text") or "").strip(),
                date=(r.get("date") or "").strip(),
            )
        )
    return reviews


def _call(system: str, user: str, output_model, purpose: str, model: str = DEFAULT_MODEL):
    """Claude API を呼び、構造化出力を返す。テストでは差し替える。"""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=output_model,
    )
    record_usage(purpose, model, response.usage)
    if response.stop_reason == "refusal":
        raise RuntimeError("モデルが応答を拒否しました。入力内容を見直してください。")
    if response.parsed_output is None:
        raise RuntimeError("構造化出力の解析に失敗しました。")
    return response.parsed_output


def _rough_cost(system: str, user: str, expected_output_tokens: int, model: str = DEFAULT_MODEL) -> tuple[float, int]:
    # 日本語は概ね1文字≒1〜1.5トークン。粗い上振れ見積り。
    input_tokens = int((len(system) + len(user)) * 1.5)
    return estimate_cost(model, input_tokens, expected_output_tokens)


# ---------- 実行関数 ----------


def build_sns_prompt(shop: ShopInfo) -> str:
    return (
        f"店舗情報:\n{shop.model_dump_json(indent=2)}\n\n"
        f"{shop.month} の1か月分、30本の投稿案を日付順に作ってください。shop_name は \"{shop.name}\"、month は \"{shop.month}\"。"
    )


def run_sns(shop: ShopInfo, dry_run: bool = False, model: str = DEFAULT_MODEL):
    user = build_sns_prompt(shop)
    if dry_run:
        return _rough_cost(SNS_SYSTEM, user, 9000, model)
    return _call(SNS_SYSTEM, user, PostPlan, "mini:sns", model)


def build_review_prompt(shop_name: str, business: str, tone: str, reviews: list[Review]) -> str:
    body = "\n".join(f"- id={r.id} 評価={r.rating} 日付={r.date or '不明'}\n  {r.text}" for r in reviews)
    return f"店名: {shop_name}\n業態: {business}\n文体: {tone}\n\n口コミ一覧:\n{body}\n\nすべての口コミに返信文を作り、全体の傾向と改善候補をまとめてください。"


def run_reviews(shop_name: str, business: str, tone: str, reviews: list[Review], dry_run: bool = False, model: str = DEFAULT_MODEL):
    user = build_review_prompt(shop_name, business, tone, reviews)
    if dry_run:
        return _rough_cost(REVIEW_SYSTEM, user, 250 * len(reviews) + 800, model)
    return _call(REVIEW_SYSTEM, user, ReviewReplyPlan, "mini:reviews", model)


def build_inquiry_prompt(biz: BusinessInfo) -> str:
    return f"事業者情報:\n{biz.model_dump_json(indent=2)}\n\n問い合わせ返信テンプレートを10種作ってください。business_name は \"{biz.name}\"。"


def run_inquiry(biz: BusinessInfo, dry_run: bool = False, model: str = DEFAULT_MODEL):
    user = build_inquiry_prompt(biz)
    if dry_run:
        return _rough_cost(INQUIRY_SYSTEM, user, 6000, model)
    return _call(INQUIRY_SYSTEM, user, InquiryTemplateSet, "mini:inquiry", model)


# ---------- 出力 ----------


def posts_to_csv(plan: PostPlan) -> str:
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日", "テーマ", "本文", "ハッシュタグ", "写真の案"])
    for p in plan.posts:
        w.writerow([p.day, p.theme, p.text, " ".join("#" + h.lstrip("#") for h in p.hashtags), p.image_idea])
    return buf.getvalue()


def posts_to_markdown(plan: PostPlan) -> str:
    lines = [f"# {plan.shop_name} {plan.month} 投稿案（30本）", ""]
    for p in plan.posts:
        tags = " ".join("#" + h.lstrip("#") for h in p.hashtags)
        lines += [f"## {plan.month}-{p.day:02d}　{p.theme}", "", p.text, "", tags, "", f"写真の案：{p.image_idea}", ""]
    lines += ["## 運用上の注意", ""] + [f"- {n}" for n in plan.notes] + [""]
    return "\n".join(lines)


def replies_to_csv(plan: ReviewReplyPlan) -> str:
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "評価", "返信文", "要確認", "理由"])
    for r in plan.replies:
        w.writerow([r.id, r.rating, r.reply, "要確認" if r.needs_attention else "", r.reason])
    return buf.getvalue()


def replies_to_markdown(plan: ReviewReplyPlan) -> str:
    lines = [f"# {plan.shop_name} 口コミ返信案", "", "## 傾向", "", plan.summary, "", "## 改善候補", ""]
    lines += [f"- {i}" for i in plan.improvements] + ["", "## 返信文", ""]
    for r in plan.replies:
        flag = "　【要確認】" + r.reason if r.needs_attention else ""
        lines += [f"### id {r.id}（評価 {r.rating}）{flag}", "", r.reply, ""]
    return "\n".join(lines)


def templates_to_markdown(ts: InquiryTemplateSet) -> str:
    lines = [f"# {ts.business_name} 問い合わせ返信テンプレート（10種）", ""]
    for i, t in enumerate(ts.templates, 1):
        lines += [f"## {i}. {t.situation}", "", f"件名：{t.subject}", "", t.body, ""]
        if t.followup:
            lines += [f"返信後にやること：{t.followup}", ""]
    lines += ["## 使い方の注意", ""] + [f"- {n}" for n in ts.usage_notes] + [""]
    return "\n".join(lines)
