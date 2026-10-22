"""コマンドライン入口。

  bizagent diagnose --json input.json [--engine heuristic|claude] [--out report.md]
  bizagent diagnose --interactive
  bizagent ledger add --kind income --category 診断 --amount 30000 --memo "A社"
  bizagent ledger status
  bizagent ledger dashboard [--out ledger/dashboard.html]
  bizagent serve [--port 8000]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import ledger as L
from .diagnose import DiagnosisInput, diagnose, report_to_markdown


def _cmd_diagnose(args: argparse.Namespace) -> int:
    if args.interactive:
        data = {
            "company_name": input("会社名・屋号: "),
            "industry": input("業種: "),
            "staff_count": int(input("従業員数: ") or "1"),
            "hourly_cost": int(input("時間あたり人件費（円、空なら2500）: ") or "2500"),
            "description": input("主な業務の流れ: "),
            "pain_points": input("困っている作業: "),
            "tools_in_use": input("使っているツール: "),
        }
    else:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    inp = DiagnosisInput(**data)
    report = diagnose(inp, engine=args.engine)
    text = report.model_dump_json(indent=2) if args.format == "json" else report_to_markdown(report)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"書き出しました: {args.out}")
    else:
        print(text)
    return 0


def _cmd_ledger(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else L.DEFAULT_PATH
    if args.ledger_cmd == "add":
        d = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        L.append_entry(L.Entry(d, args.kind, args.category, args.amount, args.memo or ""), path)
        print("記録しました。")
        entries = L.read_entries(path)
        print(L.format_sprint(L.compute_sprint(entries)))
        print()
        print(L.format_status(L.compute_status(entries)))
        return 0
    entries = L.read_entries(path)
    status = L.compute_status(entries)
    if args.ledger_cmd == "status":
        print(L.format_sprint(L.compute_sprint(entries)))
        print()
        print(L.format_status(status))
        return 0
    if args.ledger_cmd == "sprint":
        print(L.format_sprint(L.compute_sprint(entries)))
        return 0
    if args.ledger_cmd == "dashboard":
        out = Path(args.out) if args.out else path.parent / "dashboard.html"
        out.write_text(L.render_dashboard_html(entries, status), encoding="utf-8")
        print(f"書き出しました: {out}")
        return 0
    return 1


def _cmd_mini(args: argparse.Namespace) -> int:
    from . import mini as M

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mini_cmd == "sns":
        shop = M.ShopInfo(**json.loads(Path(args.json).read_text(encoding="utf-8")))
        if args.dry_run:
            usd, yen = M.run_sns(shop, dry_run=True)
            print(f"入力OK: {shop.name} / {shop.month}。概算費用 約{yen}円（${usd}）")
            return 0
        plan = M.run_sns(shop)
        (out_dir / "sns_posts.csv").write_text(M.posts_to_csv(plan), encoding="utf-8-sig")
        (out_dir / "sns_posts.md").write_text(M.posts_to_markdown(plan), encoding="utf-8")
        print(f"書き出しました: {out_dir}/sns_posts.csv, sns_posts.md（{len(plan.posts)}本）")
        return 0

    if args.mini_cmd == "reviews":
        reviews = M.read_reviews_csv(args.csv)
        if args.dry_run:
            usd, yen = M.run_reviews(args.name, args.business, args.tone, reviews, dry_run=True)
            print(f"入力OK: 口コミ{len(reviews)}件。概算費用 約{yen}円（${usd}）")
            return 0
        plan = M.run_reviews(args.name, args.business, args.tone, reviews)
        (out_dir / "review_replies.csv").write_text(M.replies_to_csv(plan), encoding="utf-8-sig")
        (out_dir / "review_replies.md").write_text(M.replies_to_markdown(plan), encoding="utf-8")
        print(f"書き出しました: {out_dir}/review_replies.csv, review_replies.md（{len(plan.replies)}件）")
        return 0

    if args.mini_cmd == "inquiry":
        biz = M.BusinessInfo(**json.loads(Path(args.json).read_text(encoding="utf-8")))
        if args.dry_run:
            usd, yen = M.run_inquiry(biz, dry_run=True)
            print(f"入力OK: {biz.name}。概算費用 約{yen}円（${usd}）")
            return 0
        ts = M.run_inquiry(biz)
        (out_dir / "inquiry_templates.md").write_text(M.templates_to_markdown(ts), encoding="utf-8")
        print(f"書き出しました: {out_dir}/inquiry_templates.md（{len(ts.templates)}種）")
        return 0
    return 1


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("bizagent.web:app", host=args.host, port=args.port, reload=False)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bizagent", description="AI業務自動化サービス事業の運営ツール")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="業務自動化診断を実行する")
    d.add_argument("--json", help="入力 JSON ファイル")
    d.add_argument("--interactive", action="store_true", help="対話形式で入力する")
    d.add_argument("--engine", choices=["heuristic", "claude"], default=None)
    d.add_argument("--format", choices=["md", "json"], default="md")
    d.add_argument("--out", help="出力先ファイル")
    d.set_defaults(func=_cmd_diagnose)

    lg = sub.add_parser("ledger", help="台帳の記録と集計")
    lg.add_argument("--file", help="台帳 CSV のパス（既定: ledger/ledger.csv）")
    lsub = lg.add_subparsers(dest="ledger_cmd", required=True)
    a = lsub.add_parser("add")
    a.add_argument("--kind", choices=L.KINDS, required=True)
    a.add_argument("--category", required=True)
    a.add_argument("--amount", type=int, required=True)
    a.add_argument("--memo")
    a.add_argument("--date", help="YYYY-MM-DD（既定: 今日）")
    lsub.add_parser("status")
    lsub.add_parser("sprint", help="90日スプリントの判定だけを表示")
    db = lsub.add_parser("dashboard")
    db.add_argument("--out")
    lg.set_defaults(func=_cmd_ledger)

    m = sub.add_parser("mini", help="入口商品（1万円・当日納品）の納品物を生成する")
    m.add_argument("--out-dir", default="deliverables", help="出力先ディレクトリ")
    m.add_argument("--dry-run", action="store_true", help="API を呼ばず入力確認と概算費用だけ表示")
    msub = m.add_subparsers(dest="mini_cmd", required=True)
    ms = msub.add_parser("sns", help="SNS 投稿案30本")
    ms.add_argument("--json", required=True, help="店舗情報 JSON（examples/mini_shop.json 参照）")
    mr = msub.add_parser("reviews", help="口コミ返信案")
    mr.add_argument("--csv", required=True, help="口コミ CSV（列: id,rating,text,date）")
    mr.add_argument("--name", required=True, help="店名")
    mr.add_argument("--business", required=True, help="業態")
    mr.add_argument("--tone", default="丁寧で温かい")
    mi = msub.add_parser("inquiry", help="問い合わせ返信テンプレート10種")
    mi.add_argument("--json", required=True, help="事業者情報 JSON（examples/mini_business.json 参照）")
    m.set_defaults(func=_cmd_mini)

    s = sub.add_parser("serve", help="Web 画面（診断フォーム）を起動する")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=_cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "diagnose" and not (args.json or args.interactive):
        print("--json か --interactive を指定してください", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
