from datetime import date

from bizagent import ledger as L


def test_append_and_read(tmp_path):
    p = tmp_path / "l.csv"
    L.append_entry(L.Entry(date(2026, 10, 22), "capital", "元手", 100000), p)
    L.append_entry(L.Entry(date(2026, 11, 5), "income", "診断", 30000, "A社"), p)
    L.append_entry(L.Entry(date(2026, 11, 6), "expense", "ドメイン", 1500), p)
    entries = L.read_entries(p)
    assert [e.kind for e in entries] == ["capital", "income", "expense"]
    s = L.compute_status(entries, as_of=date(2026, 11, 30))
    assert s.capital == 100000 and s.revenue == 30000 and s.expenses == 1500
    assert s.profit == 28500 and s.cash == 128500
    assert s.revenue_last_90d == 30000
    assert s.monthly_pace == 10000
    assert s.months_to_goal is not None and s.months_to_goal > 900


def test_status_without_income():
    s = L.compute_status([L.Entry(date(2026, 10, 22), "capital", "元手", 100000)], as_of=date(2026, 10, 22))
    assert s.months_to_goal is None and s.projected_goal_date is None
    assert "算出できない" in L.format_status(s)


def test_goal_reached():
    entries = [L.Entry(date(2026, 10, 22), "capital", "元手", 100000), L.Entry(date(2027, 1, 1), "income", "構築", 10_000_000)]
    s = L.compute_status(entries, as_of=date(2027, 1, 2))
    assert s.progress == 1.0 and s.months_to_goal == 0


def test_rejects_bad_entries(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        L.append_entry(L.Entry(date(2026, 1, 1), "income", "x", 0), tmp_path / "l.csv")
    with pytest.raises(ValueError):
        L.append_entry(L.Entry(date(2026, 1, 1), "bogus", "x", 10), tmp_path / "l.csv")


def test_dashboard_html(tmp_path):
    entries = [
        L.Entry(date(2026, 10, 22), "capital", "元手", 100000),
        L.Entry(date(2026, 11, 5), "income", "診断", 30000, "A社"),
    ]
    s = L.compute_status(entries, as_of=date(2026, 11, 30))
    html = L.render_dashboard_html(entries, s)
    assert "<!doctype html>" in html and "2026-11" in html and "30,000" in html


def test_repo_ledger_is_readable():
    entries = L.read_entries()
    assert entries and entries[0].kind == "capital" and entries[0].amount == 100000
