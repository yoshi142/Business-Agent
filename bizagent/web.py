"""Web 画面：サービス紹介ページと業務自動化診断フォーム。

起動: python -m bizagent serve  （http://127.0.0.1:8000）
"""

from __future__ import annotations

import html
import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .diagnose import DiagnosisInput, DiagnosisReport, diagnose, report_to_markdown

app = FastAPI(title="Business-Agent", docs_url=None, redoc_url=None)

SITE_DIR = Path(__file__).resolve().parent.parent / "site"

CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e5e5e5;--acc:#2f6f9f;--soft:#f3f6f9}
@media (prefers-color-scheme:dark){:root{--bg:#151515;--fg:#eee;--muted:#aaa;--line:#333;--soft:#1f2428}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.7}
.wrap{max-width:820px;margin:0 auto;padding:24px 16px}h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:32px}
label{display:block;margin-top:14px;font-weight:600}input,textarea,select{width:100%;padding:10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit}
textarea{min-height:90px}button{margin-top:18px;padding:12px 20px;border:0;border-radius:6px;background:var(--acc);color:#fff;font:inherit;font-weight:600;cursor:pointer}
.note{color:var(--muted);font-size:.9rem}.card{background:var(--soft);border-radius:8px;padding:14px 16px;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:.92rem}td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.num{text-align:right;white-space:nowrap}
a{color:var(--acc)}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:600px){.row{grid-template-columns:1fr}}
"""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body><div class="wrap">{body}</div></body></html>"""


FORM_HTML = """
<h1>業務自動化 無料診断</h1>
<p>普段の業務と困っている作業を書くだけで、自動化できる作業・削減できる時間・費用の目安を3〜5件にまとめて提示します。所要時間は1分です。</p>
<form method="post" action="/diagnose">
<div class="row">
<div><label>会社名・屋号</label><input name="company_name" required maxlength="100"></div>
<div><label>業種</label><input name="industry" required placeholder="例：飲食、建設、士業、小売、製造、介護" maxlength="50"></div>
</div>
<div class="row">
<div><label>従業員数（経営者含む）</label><input name="staff_count" type="number" min="1" max="500" value="5" required></div>
<div><label>1時間あたりの人件費の目安（円）</label><input name="hourly_cost" type="number" min="500" max="30000" value="2500" required></div>
</div>
<label>主な業務の流れ</label><textarea name="description" required maxlength="3000" placeholder="例：電話とメールで注文を受け、Excelで見積を作り、紙の請求書を郵送している"></textarea>
<label>時間がかかっている・困っている作業</label><textarea name="pain_points" required maxlength="3000" placeholder="例：問い合わせ返信に毎日1時間。月末の請求書入力に2日かかる"></textarea>
<label>使っているツール（任意）</label><input name="tools_in_use" maxlength="300" placeholder="例：Excel、LINE、freee、Googleカレンダー">
<button type="submit">診断する</button>
<p class="note">入力内容は診断のためだけに使います。数字は同規模企業の一般的な目安で、実測値ではありません。</p>
</form>
"""


def report_html(r: DiagnosisReport) -> str:
    e = html.escape
    rows = "".join(
        f"<tr><td>{i}</td><td>{e(c.title)}</td><td class='num'>{c.hours_saved_per_week}時間</td>"
        f"<td class='num'>{c.annual_saving_yen:,}円</td><td class='num'>{c.proposed_price_yen:,}円</td>"
        f"<td class='num'>{c.payback_months}か月</td><td>{'★' * c.difficulty}</td></tr>"
        for i, c in enumerate(r.candidates, 1)
    )
    details = "".join(
        f"<div class='card'><h3 style='margin:0 0 6px'>{i}. {e(c.title)}</h3>"
        f"<div><b>現状の課題</b>：{e(c.problem)}</div><div><b>自動化の内容</b>：{e(c.solution)}</div>"
        f"<div><b>使うツール</b>：{e('、'.join(c.tools))}</div><div><b>構築工数の目安</b>：{c.build_hours}時間</div>"
        f"<div class='note'>{e(c.rationale)}</div></div>"
        for i, c in enumerate(r.candidates, 1)
    )
    caveats = "".join(f"<li>{e(c)}</li>" for c in r.caveats)
    body = f"""
<h1>診断レポート：{e(r.company_name)}</h1>
<p class="note">作成日 {e(r.generated_on)}　／　{'AI診断' if r.engine == 'claude' else '簡易診断'}</p>
<div class="card">{e(r.summary)}<br><b>年間削減効果の合計（目安）：{r.total_annual_saving_yen:,}円</b></div>
<h2>自動化候補（優先度順）</h2>
<div style="overflow-x:auto"><table><thead><tr><th>#</th><th>施策</th><th class="num">週あたり削減</th><th class="num">年間効果</th><th class="num">提案価格（税抜）</th><th class="num">回収</th><th>難易度</th></tr></thead><tbody>{rows}</tbody></table></div>
{details}
<h2>最初の一歩</h2><p>{e(r.recommended_first_step)}</p>
<h2>前提と注意点</h2><ul>{caveats}</ul>
<p><a href="/">もう一度診断する</a>　／　<a href="/site">サービス案内へ</a></p>
"""
    return _page(f"診断レポート：{r.company_name}", body)


def _parse_form(**kw) -> DiagnosisInput:
    return DiagnosisInput(**kw)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _page("業務自動化 無料診断", FORM_HTML)


@app.get("/site", response_class=HTMLResponse)
def site() -> str:
    p = SITE_DIR / "index.html"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return _page("サービス案内", "<p>準備中</p>")


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.post("/diagnose", response_class=HTMLResponse)
def diagnose_form(
    company_name: str = Form(...),
    industry: str = Form(...),
    staff_count: int = Form(...),
    hourly_cost: int = Form(2500),
    description: str = Form(...),
    pain_points: str = Form(...),
    tools_in_use: str = Form(""),
) -> str:
    inp = _parse_form(
        company_name=company_name.strip(),
        industry=industry.strip(),
        staff_count=staff_count,
        hourly_cost=hourly_cost,
        description=description.strip(),
        pain_points=pain_points.strip(),
        tools_in_use=tools_in_use.strip(),
    )
    engine = os.environ.get("BIZAGENT_ENGINE")  # 未設定なら自動判定
    report = diagnose(inp, engine=engine)
    return report_html(report)


@app.post("/api/diagnose")
def diagnose_api(inp: DiagnosisInput, engine: str | None = None) -> JSONResponse:
    report = diagnose(inp, engine=engine)
    return JSONResponse(report.model_dump())


@app.post("/api/diagnose.md", response_class=PlainTextResponse)
def diagnose_api_md(inp: DiagnosisInput, engine: str | None = None) -> str:
    return report_to_markdown(diagnose(inp, engine=engine))
