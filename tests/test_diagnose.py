from bizagent.diagnose import (
    DiagnosisInput,
    annual_saving,
    diagnose_heuristic,
    load_recipes,
    payback_months,
    report_to_markdown,
)


def _inp(**kw):
    base = dict(
        company_name="テスト工務店",
        industry="建設",
        staff_count=8,
        description="住宅リフォームの見積と現場管理。日報はLINEで受け取り、請求書はExcelで作成",
        pain_points="見積作成に時間がかかる。請求書の入力と経理が月末に集中する",
        tools_in_use="Excel, LINE, freee",
    )
    base.update(kw)
    return DiagnosisInput(**base)


def test_recipes_are_well_formed():
    recipes = load_recipes()
    assert len(recipes) >= 10
    ids = [r["id"] for r in recipes]
    assert len(ids) == len(set(ids))
    for r in recipes:
        assert r["difficulty"] in (1, 2, 3)
        assert r["price_band"][0] < r["price_band"][1]
        assert all(len(k) >= 2 for k in r["keywords"]), r["id"]


def test_math_helpers():
    assert annual_saving(2.0, 2500) == 250_000
    assert payback_months(250_000, 250_000) == 12.0
    assert payback_months(100_000, 0) == 99.0


def test_heuristic_matches_described_work():
    r = diagnose_heuristic(_inp())
    titles = [c.title for c in r.candidates]
    assert 3 <= len(titles) <= 5
    assert any("見積" in t for t in titles)
    assert any("請求書" in t for t in titles)
    assert any("日報" in t for t in titles)
    assert r.total_annual_saving_yen == sum(c.annual_saving_yen for c in r.candidates)
    assert r.engine == "heuristic"
    # 「リフォーム」が「フォーム」に誤一致しない
    assert not any("問い合わせ" in t for t in titles)


def test_heuristic_falls_back_to_industry_defaults():
    r = diagnose_heuristic(_inp(company_name="カフェ", industry="飲食", staff_count=4, description="カフェ営業", pain_points="特になし", tools_in_use=""))
    assert len(r.candidates) == 3
    assert any("口コミ" in c.title or "SNS" in c.title for c in r.candidates)


def test_candidates_scale_with_staff():
    small = diagnose_heuristic(_inp(staff_count=2))
    large = diagnose_heuristic(_inp(staff_count=40))
    assert small.total_annual_saving_yen < large.total_annual_saving_yen
    assert all(c.proposed_price_yen % 10000 == 0 for c in large.candidates)


def test_markdown_render():
    md = report_to_markdown(diagnose_heuristic(_inp()))
    assert md.startswith("# 業務自動化 診断レポート：テスト工務店")
    assert "| # | 施策 |" in md
    assert "## 最初の一歩" in md
