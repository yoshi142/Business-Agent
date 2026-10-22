from datetime import date

from bizagent import ledger as L
from bizagent import usage as U


def test_sprint_counts_only_window_and_passes_at_goal():
    entries = [
        L.Entry(date(2026, 10, 22), "capital", "元手", 100000),
        L.Entry(date(2026, 10, 1), "income", "旧", 50000),  # 期間外
        L.Entry(date(2026, 11, 10), "income", "入口商品", 10000),
        L.Entry(date(2026, 12, 1), "income", "入口商品", 20000),
        L.Entry(date(2026, 11, 3), "expense", "AI利用料", 1200),
    ]
    sp = L.compute_sprint(entries, as_of=date(2026, 12, 2), api_usage_yen=900)
    assert sp.revenue == 30000 and sp.passed
    assert sp.day == 42 and sp.days_left == (date(2027, 1, 20) - date(2026, 12, 2)).days
    assert sp.ai_spent_yen == 1200  # 台帳と概算の大きい方
    assert "達成" in L.format_sprint(sp)


def test_sprint_warns_over_budget():
    sp = L.compute_sprint([], as_of=date(2026, 11, 1), api_usage_yen=31000)
    assert not sp.passed and "警告" in L.format_sprint(sp)


def test_usage_estimate_and_record(tmp_path, monkeypatch):
    monkeypatch.setenv("BIZAGENT_JPY_PER_USD", "150")
    usd, yen = U.estimate_cost("claude-opus-5-5", 10000, 5000)
    assert usd == 0.14 and yen == 21

    class Usage:
        input_tokens = 10000
        output_tokens = 5000
        cache_read_input_tokens = 0

    p = tmp_path / "u.csv"
    assert U.record_usage("test", "claude-opus-5-5", Usage(), p) == 21
    U.record_usage("test", "claude-opus-5-5", Usage(), p)
    assert U.total_yen(p) == 42
