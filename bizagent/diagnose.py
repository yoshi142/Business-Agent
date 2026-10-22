"""業務自動化診断：顧客の業務内容から自動化候補と金額効果を算出する。

2つのエンジンを持つ。
- heuristic: 規則ベース。API キー不要。営業デモや検証用。
- claude:    Claude API による構造化出力。ANTHROPIC_API_KEY があるときに使う。
"""

from __future__ import annotations

import json
import os
from datetime import date
from importlib import resources
from typing import Literal

from pydantic import BaseModel, Field

WEEKS_PER_YEAR = 50  # 休暇を除いた実稼働週数（保守的に）
DEFAULT_HOURLY_COST = 2500  # 円。人件費の目安（給与＋社会保険等）
DEFAULT_MODEL = os.environ.get("BIZAGENT_MODEL", "claude-opus-5-5")


# ---------- 入出力モデル ----------


class DiagnosisInput(BaseModel):
    company_name: str = Field(description="会社名・屋号")
    industry: str = Field(description="業種（例：飲食、建設、士業、小売、製造、医療・介護）")
    staff_count: int = Field(ge=1, description="従業員数（経営者含む）")
    hourly_cost: int = Field(default=DEFAULT_HOURLY_COST, ge=500, description="1時間あたり人件費の目安（円）")
    description: str = Field(description="主な業務の流れ。自由記述")
    pain_points: str = Field(description="時間がかかっている・困っている作業。自由記述")
    tools_in_use: str = Field(default="", description="使っているツール（Excel、LINE、freee など）")


class AutomationCandidate(BaseModel):
    title: str = Field(description="自動化施策の名前")
    problem: str = Field(description="現状の課題。顧客の言葉に寄せる")
    solution: str = Field(description="何をどう自動化するか。人が確認する箇所も明記")
    tools: list[str] = Field(description="使うツール")
    hours_saved_per_week: float = Field(ge=0, description="週あたり削減時間（会社全体）")
    annual_saving_yen: int = Field(ge=0, description="年間の人件費換算効果（円）")
    build_hours: int = Field(ge=1, description="構築に必要な工数（時間）")
    difficulty: Literal[1, 2, 3] = Field(description="難易度 1=容易 2=中 3=高")
    proposed_price_yen: int = Field(ge=0, description="提案価格（円、税抜）")
    payback_months: float = Field(ge=0, description="投資回収までの月数")
    rationale: str = Field(description="なぜこの会社に合うかの根拠（1〜2文）")


class DiagnosisReport(BaseModel):
    company_name: str
    generated_on: str = Field(description="作成日 YYYY-MM-DD")
    engine: Literal["heuristic", "claude"]
    summary: str = Field(description="診断の要約（3〜5文）")
    candidates: list[AutomationCandidate] = Field(description="優先度順の自動化候補。3〜5件")
    total_annual_saving_yen: int
    recommended_first_step: str = Field(description="最初に着手すべき1件とその理由")
    caveats: list[str] = Field(description="前提・注意点。数字は目安であること等")


# ---------- レシピ読み込み ----------


def load_recipes() -> list[dict]:
    with resources.files("bizagent.data").joinpath("recipes.json").open(encoding="utf-8") as f:
        return json.load(f)


# ---------- 共通計算 ----------


def annual_saving(hours_per_week: float, hourly_cost: int) -> int:
    return int(round(hours_per_week * WEEKS_PER_YEAR * hourly_cost))


def payback_months(price_yen: int, annual_saving_yen: int) -> float:
    if annual_saving_yen <= 0:
        return 99.0
    return round(price_yen / (annual_saving_yen / 12), 1)


def scale_hours(base_hours: float, staff_count: int) -> float:
    """レシピの基準値（5人規模を想定）を従業員数で緩やかに補正する。"""
    factor = min(3.0, max(0.5, (staff_count / 5) ** 0.5))
    return round(base_hours * factor, 1)


def price_within_band(band: list[int], difficulty: int, staff_count: int) -> int:
    lo, hi = band
    # 規模が大きいほど要件が増えるので帯の上側に寄せる
    t = min(1.0, max(0.0, (staff_count - 3) / 27))
    price = lo + (hi - lo) * t
    return int(round(price / 10000) * 10000)


# ---------- 規則ベースエンジン ----------


INDUSTRY_HINTS = {
    "飲食": ["review_reply", "sns_content", "shift_schedule", "inquiry_triage"],
    "小売": ["inventory_alert", "sns_content", "customer_followup", "review_reply"],
    "建設": ["quote_draft", "daily_report", "invoice_ocr", "data_entry"],
    "製造": ["inventory_alert", "data_entry", "daily_report", "quote_draft"],
    "士業": ["inquiry_triage", "contract_check", "meeting_minutes", "faq_bot"],
    "医療": ["inquiry_triage", "shift_schedule", "recruit_screen", "review_reply"],
    "介護": ["daily_report", "shift_schedule", "recruit_screen", "faq_bot"],
    "不動産": ["inquiry_triage", "contract_check", "sns_content", "customer_followup"],
    "美容": ["review_reply", "sns_content", "customer_followup", "shift_schedule"],
    "教育": ["inquiry_triage", "faq_bot", "sns_content", "daily_report"],
    "IT": ["meeting_minutes", "faq_bot", "quote_draft", "web_monitor"],
}


def _score_recipe(recipe: dict, text: str, industry: str) -> tuple[int, int]:
    """(記述とのキーワード一致数, 業種補正) を返す。"""
    hits = sum(1 for kw in recipe["keywords"] if kw.lower() in text)
    bonus = 0
    for key, ids in INDUSTRY_HINTS.items():
        if key in industry and recipe["id"] in ids:
            bonus = 1
    return hits, bonus


def diagnose_heuristic(inp: DiagnosisInput, max_candidates: int = 5) -> DiagnosisReport:
    text = f"{inp.description} {inp.pain_points} {inp.tools_in_use}".lower()
    recipes = load_recipes()
    scored = []
    for r in recipes:
        hits, bonus = _score_recipe(r, text, inp.industry)
        scored.append((hits, bonus, r))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]["difficulty"], -x[2]["hours_saved_per_week"]))
    # 記述に一致したものを優先し、足りなければ業種補正・汎用性の高いもので3件まで埋める
    chosen = [(h, r) for h, b, r in scored if h > 0][:max_candidates]
    if len(chosen) < 3:
        for h, b, r in scored:
            if all(r is not c for _, c in chosen):
                chosen.append((0, r))
            if len(chosen) >= 3:
                break

    candidates: list[AutomationCandidate] = []
    scores: dict[str, int] = {}
    for s, r in chosen:
        scores[r["title"]] = s
        hours = scale_hours(r["hours_saved_per_week"], inp.staff_count)
        saving = annual_saving(hours, inp.hourly_cost)
        price = price_within_band(r["price_band"], r["difficulty"], inp.staff_count)
        candidates.append(
            AutomationCandidate(
                title=r["title"],
                problem=r["problem"],
                solution=r["solution"],
                tools=r["tools"],
                hours_saved_per_week=hours,
                annual_saving_yen=saving,
                build_hours=r["build_hours"],
                difficulty=r["difficulty"],
                proposed_price_yen=price,
                payback_months=payback_months(price, saving),
                rationale=(
                    f"{inp.industry}の{inp.staff_count}名規模で頻出する作業。"
                    + ("記述内容に該当する作業が含まれている。" if s > 0 else "記述には直接現れないが、同業種で効果が出やすい。")
                ),
            )
        )

    # 記述との一致度が高く、回収期間が短く、難易度が低いものを先頭に
    candidates.sort(key=lambda c: (-scores[c.title], c.payback_months, c.difficulty))
    total = sum(c.annual_saving_yen for c in candidates)
    first = candidates[0]
    return DiagnosisReport(
        company_name=inp.company_name,
        generated_on=date.today().isoformat(),
        engine="heuristic",
        summary=(
            f"{inp.company_name}（{inp.industry}、{inp.staff_count}名）の記述から、"
            f"{len(candidates)}件の自動化候補を抽出した。"
            f"合計で週あたり約{sum(c.hours_saved_per_week for c in candidates):.1f}時間、"
            f"年間で約{total:,}円相当の人件費削減が見込める。"
            f"いずれも最終確認は人が行う前提で設計し、業務の品質を落とさないことを優先する。"
        ),
        candidates=candidates,
        total_annual_saving_yen=total,
        recommended_first_step=(
            f"「{first.title}」から着手する。難易度{first.difficulty}で構築{first.build_hours}時間程度、"
            f"投資回収は約{first.payback_months}か月と短く、効果を早く実感できるため。"
        ),
        caveats=[
            "削減時間と金額は、同規模の企業での一般的な目安であり、実測値ではない。",
            "導入前に現状の作業時間を1〜2週間計測し、効果を確認してから次の施策に進む。",
            "個人情報・機密情報を扱う場合は、取り扱い範囲と保存先を事前に合意する。",
            "規則ベースの簡易診断のため、ヒアリングで内容を補正する必要がある。",
        ],
    )


# ---------- Claude エンジン ----------

SYSTEM_PROMPT = """あなたは日本の中小企業向けに業務自動化を提案するコンサルタントです。
顧客の業務記述から、現実的で小さく始められる自動化候補を3〜5件、優先度順に提案してください。

守ること:
- 数字（削減時間・金額）は保守的に見積もる。根拠を rationale に書く。
- 年間効果 = 週あたり削減時間 × 50週 × 時間あたり人件費。
- 提案価格は参考レシピの price_band の範囲内。payback_months = 価格 ÷ (年間効果 ÷ 12)。
- AI の出力は必ず人が確認する設計にし、その確認箇所を solution に書く。
- 顧客が使っているツールを優先して組み込む。
- 専門用語を避け、経営者が読んで判断できる文章にする。
- 参考レシピに無い施策を提案してもよいが、構築工数は現実的に。

参考レシピ（JSON）:
"""


def diagnose_claude(inp: DiagnosisInput, model: str = DEFAULT_MODEL) -> DiagnosisReport:
    """Claude API で診断する。ANTHROPIC_API_KEY（または ant auth のプロファイル）が必要。"""
    import anthropic

    client = anthropic.Anthropic()
    recipes = load_recipes()
    user_content = (
        "以下の企業を診断してください。\n\n"
        f"会社名: {inp.company_name}\n業種: {inp.industry}\n従業員数: {inp.staff_count}\n"
        f"時間あたり人件費: {inp.hourly_cost}円\n使用ツール: {inp.tools_in_use or '不明'}\n\n"
        f"業務の流れ:\n{inp.description}\n\n困っている作業:\n{inp.pain_points}\n\n"
        f"generated_on は {date.today().isoformat()}、engine は \"claude\" とすること。"
    )
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT + json.dumps(recipes, ensure_ascii=False),
        messages=[{"role": "user", "content": user_content}],
        output_format=DiagnosisReport,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("モデルが応答を拒否しました。入力内容を見直してください。")
    report = response.parsed_output
    if report is None:
        raise RuntimeError("構造化出力の解析に失敗しました。")
    report.engine = "claude"
    report.generated_on = date.today().isoformat()
    return report


def diagnose(inp: DiagnosisInput, engine: str | None = None) -> DiagnosisReport:
    """engine が None なら、API 認証情報があれば claude、無ければ heuristic。"""
    if engine is None:
        engine = "claude" if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else "heuristic"
    if engine == "claude":
        return diagnose_claude(inp)
    return diagnose_heuristic(inp)


# ---------- 出力整形 ----------


def report_to_markdown(r: DiagnosisReport) -> str:
    lines = [
        f"# 業務自動化 診断レポート：{r.company_name}",
        "",
        f"作成日：{r.generated_on}　／　エンジン：{'AI診断' if r.engine == 'claude' else '簡易診断'}",
        "",
        "## 要約",
        "",
        r.summary,
        "",
        f"年間削減効果の合計（目安）：{r.total_annual_saving_yen:,}円",
        "",
        "## 自動化候補（優先度順）",
        "",
        "| # | 施策 | 週あたり削減 | 年間効果 | 提案価格（税抜） | 回収 | 難易度 |",
        "|---|------|-------------|---------|----------------|------|--------|",
    ]
    for i, c in enumerate(r.candidates, 1):
        lines.append(
            f"| {i} | {c.title} | {c.hours_saved_per_week}時間 | {c.annual_saving_yen:,}円 | "
            f"{c.proposed_price_yen:,}円 | {c.payback_months}か月 | {'★' * c.difficulty} |"
        )
    lines.append("")
    for i, c in enumerate(r.candidates, 1):
        lines += [
            f"### {i}. {c.title}",
            "",
            f"- 現状の課題：{c.problem}",
            f"- 自動化の内容：{c.solution}",
            f"- 使うツール：{'、'.join(c.tools)}",
            f"- 構築工数の目安：{c.build_hours}時間",
            f"- 根拠：{c.rationale}",
            "",
        ]
    lines += ["## 最初の一歩", "", r.recommended_first_step, "", "## 前提と注意点", ""]
    lines += [f"- {c}" for c in r.caveats]
    lines.append("")
    return "\n".join(lines)
