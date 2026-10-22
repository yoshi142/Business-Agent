"""台帳：元手10万円から累計売上1,000万円までの進捗を記録・集計する。

CSV 1枚（ledger/ledger.csv）に、資本・売上・経費を1行ずつ記録する。
集計は「累計売上」「累計利益」「現金残高」「目標達成率」「直近90日の売上ペースによる到達予測」。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

GOAL_REVENUE_YEN = 10_000_000
INITIAL_CAPITAL_YEN = 100_000

# 90日スプリント（第1関門）：期限までに売上 3万円。AI 利用料の上限 3万円。
SPRINT_START = date(2026, 10, 22)
SPRINT_DAYS = 90
SPRINT_DEADLINE = date(2027, 1, 20)
SPRINT_GOAL_YEN = 30_000
AI_BUDGET_YEN = 30_000
AI_COST_CATEGORIES = ("AI利用料", "API")
KINDS = ("capital", "income", "expense")
FIELDS = ["date", "kind", "category", "amount", "memo"]
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "ledger" / "ledger.csv"


@dataclass
class Entry:
    date: date
    kind: str
    category: str
    amount: int
    memo: str = ""


@dataclass
class SprintStatus:
    as_of: date
    day: int
    days_left: int
    revenue: int
    goal: int
    ai_spent_yen: int
    ai_budget_yen: int
    passed: bool


@dataclass
class Status:
    as_of: date
    capital: int
    revenue: int
    expenses: int
    profit: int
    cash: int
    goal: int
    progress: float  # 0.0〜1.0
    revenue_last_90d: int
    monthly_pace: float
    projected_goal_date: date | None
    months_to_goal: float | None


def read_entries(path: Path = DEFAULT_PATH) -> list[Entry]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    entries = []
    for row in rows:
        kind = row["kind"].strip()
        if kind not in KINDS:
            raise ValueError(f"kind は {KINDS} のいずれか: {row}")
        entries.append(
            Entry(
                date=datetime.strptime(row["date"].strip(), "%Y-%m-%d").date(),
                kind=kind,
                category=row["category"].strip(),
                amount=int(row["amount"]),
                memo=row.get("memo", "").strip(),
            )
        )
    return sorted(entries, key=lambda e: e.date)


def append_entry(entry: Entry, path: Path = DEFAULT_PATH) -> None:
    if entry.kind not in KINDS:
        raise ValueError(f"kind は {KINDS} のいずれか")
    if entry.amount <= 0:
        raise ValueError("amount は正の整数（支出も正で記録する）")
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(
            {
                "date": entry.date.isoformat(),
                "kind": entry.kind,
                "category": entry.category,
                "amount": entry.amount,
                "memo": entry.memo,
            }
        )


def compute_status(entries: list[Entry], as_of: date | None = None, goal: int = GOAL_REVENUE_YEN) -> Status:
    as_of = as_of or date.today()
    entries = [e for e in entries if e.date <= as_of]
    capital = sum(e.amount for e in entries if e.kind == "capital")
    revenue = sum(e.amount for e in entries if e.kind == "income")
    expenses = sum(e.amount for e in entries if e.kind == "expense")
    profit = revenue - expenses
    cash = capital + profit
    since = as_of - timedelta(days=90)
    rev90 = sum(e.amount for e in entries if e.kind == "income" and since < e.date <= as_of)
    monthly_pace = rev90 / 3.0
    remaining = max(0, goal - revenue)
    if remaining == 0:
        months = 0.0
        projected = as_of
    elif monthly_pace > 0:
        months = remaining / monthly_pace
        projected = as_of + timedelta(days=int(months * 30.4))
    else:
        months = None
        projected = None
    return Status(
        as_of=as_of,
        capital=capital,
        revenue=revenue,
        expenses=expenses,
        profit=profit,
        cash=cash,
        goal=goal,
        progress=min(1.0, revenue / goal) if goal else 0.0,
        revenue_last_90d=rev90,
        monthly_pace=monthly_pace,
        projected_goal_date=projected,
        months_to_goal=months,
    )


def compute_sprint(entries: list[Entry], as_of: date | None = None, api_usage_yen: int | None = None) -> SprintStatus:
    """90日スプリントの判定。AI 利用料は台帳の該当区分と api_usage.csv の概算の大きい方を採用する。"""
    as_of = as_of or date.today()
    in_window = [e for e in entries if SPRINT_START <= e.date <= min(as_of, SPRINT_DEADLINE)]
    revenue = sum(e.amount for e in in_window if e.kind == "income")
    ledger_ai = sum(e.amount for e in in_window if e.kind == "expense" and e.category in AI_COST_CATEGORIES)
    if api_usage_yen is None:
        from .usage import total_yen

        api_usage_yen = total_yen()
    ai_spent = max(ledger_ai, api_usage_yen)
    day = (as_of - SPRINT_START).days + 1
    return SprintStatus(
        as_of=as_of,
        day=day,
        days_left=max(0, (SPRINT_DEADLINE - as_of).days),
        revenue=revenue,
        goal=SPRINT_GOAL_YEN,
        ai_spent_yen=ai_spent,
        ai_budget_yen=AI_BUDGET_YEN,
        passed=revenue >= SPRINT_GOAL_YEN,
    )


def format_sprint(sp: SprintStatus) -> str:
    judge = "達成" if sp.passed else ("未達（期限切れ）" if sp.days_left == 0 and sp.as_of >= SPRINT_DEADLINE else "未達")
    need = max(0, sp.goal - sp.revenue)
    lines = [
        f"90日スプリント : {sp.day}日目 / {SPRINT_DAYS}日（残り {sp.days_left} 日、期限 {SPRINT_DEADLINE}）",
        f"売上           : {sp.revenue:>9,} 円 / 目標 {sp.goal:,} 円（あと {need:,} 円）→ {judge}",
        f"AI 利用料      : {sp.ai_spent_yen:>9,} 円 / 上限 {sp.ai_budget_yen:,} 円（残り {max(0, sp.ai_budget_yen - sp.ai_spent_yen):,} 円）",
    ]
    if sp.ai_spent_yen > sp.ai_budget_yen:
        lines.append("警告           : AI 利用料が上限を超えている")
    return "\n".join(lines)


def format_status(s: Status) -> str:
    bar_len = 30
    filled = int(round(s.progress * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)
    lines = [
        f"基準日        : {s.as_of.isoformat()}",
        f"投入資本      : {s.capital:>12,} 円",
        f"累計売上      : {s.revenue:>12,} 円",
        f"累計経費      : {s.expenses:>12,} 円",
        f"累計利益      : {s.profit:>12,} 円",
        f"現金残高      : {s.cash:>12,} 円",
        f"目標（売上）  : {s.goal:>12,} 円",
        f"達成率        : [{bar}] {s.progress * 100:5.1f}%",
        f"直近90日売上  : {s.revenue_last_90d:>12,} 円（月あたり {s.monthly_pace:,.0f} 円）",
    ]
    if s.months_to_goal is None:
        lines.append("到達予測      : 直近90日の売上が無いため算出できない")
    elif s.months_to_goal == 0:
        lines.append("到達予測      : 達成済み")
    else:
        lines.append(f"到達予測      : 現在のペースなら約 {s.months_to_goal:.1f} か月後（{s.projected_goal_date}）")
    return "\n".join(lines)


def monthly_series(entries: list[Entry]) -> list[tuple[str, int, int]]:
    """(年月, 売上, 経費) の月次系列。"""
    buckets: dict[str, list[int]] = {}
    for e in entries:
        if e.kind == "capital":
            continue
        key = e.date.strftime("%Y-%m")
        b = buckets.setdefault(key, [0, 0])
        if e.kind == "income":
            b[0] += e.amount
        else:
            b[1] += e.amount
    return [(k, v[0], v[1]) for k, v in sorted(buckets.items())]


def render_dashboard_html(entries: list[Entry], s: Status) -> str:
    series = monthly_series(entries)
    max_v = max([1] + [max(r, c) for _, r, c in series])
    rows = "".join(
        f"<tr><td>{m}</td><td class='num'>{r:,}</td><td class='num'>{c:,}</td><td class='num'>{r - c:,}</td></tr>"
        for m, r, c in series
    )
    bars = "".join(
        f"<div class='bar'><div class='rev' style='height:{int(r / max_v * 160)}px' title='売上 {r:,}'></div>"
        f"<div class='exp' style='height:{int(c / max_v * 160)}px' title='経費 {c:,}'></div><span>{m[2:]}</span></div>"
        for m, r, c in series
    )
    recent = "".join(
        f"<tr><td>{e.date}</td><td>{ {'capital': '資本', 'income': '売上', 'expense': '経費'}[e.kind]}</td>"
        f"<td>{e.category}</td><td class='num'>{e.amount:,}</td><td>{e.memo}</td></tr>"
        for e in list(reversed(entries))[:20]
    )
    proj = (
        "算出不可（直近90日の売上なし）"
        if s.months_to_goal is None
        else ("達成済み" if s.months_to_goal == 0 else f"約 {s.months_to_goal:.1f} か月後（{s.projected_goal_date}）")
    )
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>進捗ダッシュボード</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e5e5e5;--acc:#2f6f9f;--acc2:#c76b3a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--fg:#eee;--muted:#aaa;--line:#333}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;max-width:900px;margin-inline:auto}}
h1{{font-size:1.3rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.card{{border:1px solid var(--line);border-radius:8px;padding:12px}}.card small{{color:var(--muted)}}.card b{{display:block;font-size:1.3rem;font-weight:600}}
.progress{{height:14px;background:var(--line);border-radius:7px;overflow:hidden;margin:8px 0}}.progress div{{height:100%;background:var(--acc)}}
.chart{{display:flex;gap:8px;align-items:flex-end;height:190px;border-bottom:1px solid var(--line);padding:0 4px;overflow-x:auto}}
.bar{{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;min-width:40px;height:100%;position:relative}}
.bar>div{{width:14px;display:inline-block}}.bar .rev{{background:var(--acc);margin-right:2px}}.bar .exp{{background:var(--acc2)}}
.bar{{flex-direction:row;align-items:flex-end}}.bar span{{position:absolute;bottom:-20px;font-size:.75rem;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:.9rem;margin-top:24px}}td,th{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.legend{{font-size:.8rem;color:var(--muted);margin-top:28px}}
</style></head><body>
<h1>進捗ダッシュボード（基準日 {s.as_of}）</h1>
<div class="grid">
<div class="card"><small>累計売上</small><b>{s.revenue:,} 円</b></div>
<div class="card"><small>累計利益</small><b>{s.profit:,} 円</b></div>
<div class="card"><small>現金残高</small><b>{s.cash:,} 円</b></div>
<div class="card"><small>月あたり売上ペース（直近90日）</small><b>{s.monthly_pace:,.0f} 円</b></div>
</div>
<div class="card" style="margin-top:12px"><small>目標 {s.goal:,} 円 に対する達成率</small>
<div class="progress"><div style="width:{s.progress * 100:.1f}%"></div></div>
<div>{s.progress * 100:.1f}%　／　到達予測：{proj}</div></div>
<h2 style="font-size:1.1rem;margin-top:24px">月次 売上・経費</h2>
<div class="chart">{bars or '<span style="color:var(--muted)">記録なし</span>'}</div>
<div class="legend">青＝売上、橙＝経費</div>
<table><thead><tr><th>年月</th><th class="num">売上</th><th class="num">経費</th><th class="num">利益</th></tr></thead><tbody>{rows}</tbody></table>
<h2 style="font-size:1.1rem;margin-top:24px">直近の記録</h2>
<table><thead><tr><th>日付</th><th>種別</th><th>区分</th><th class="num">金額</th><th>メモ</th></tr></thead><tbody>{recent}</tbody></table>
</body></html>"""


def entries_to_csv(entries: list[Entry]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    for e in entries:
        w.writerow({"date": e.date.isoformat(), "kind": e.kind, "category": e.category, "amount": e.amount, "memo": e.memo})
    return buf.getvalue()
