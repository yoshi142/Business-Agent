from fastapi.testclient import TestClient

from bizagent.web import app

client = TestClient(app)

PAYLOAD = {
    "company_name": "テスト整骨院",
    "industry": "医療",
    "staff_count": 3,
    "hourly_cost": 2000,
    "description": "予約はLINEと電話。問い合わせ返信とシフト作成を院長がやっている",
    "pain_points": "口コミ返信が追いつかない。求人応募の対応が遅れる",
    "tools_in_use": "LINE, Googleカレンダー",
}


def test_index_and_health():
    assert client.get("/health").text == "ok"
    r = client.get("/")
    assert r.status_code == 200 and "業務自動化 無料診断" in r.text


def test_form_post_renders_report(monkeypatch):
    monkeypatch.setenv("BIZAGENT_ENGINE", "heuristic")
    r = client.post("/diagnose", data=PAYLOAD)
    assert r.status_code == 200
    assert "診断レポート：テスト整骨院" in r.text
    assert "口コミ" in r.text


def test_api_json():
    r = client.post("/api/diagnose?engine=heuristic", json=PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "heuristic" and 3 <= len(body["candidates"]) <= 5


def test_api_markdown():
    r = client.post("/api/diagnose.md?engine=heuristic", json=PAYLOAD)
    assert r.status_code == 200 and r.text.startswith("# 業務自動化 診断レポート")


def test_validation_error():
    bad = dict(PAYLOAD, staff_count=0)
    assert client.post("/api/diagnose?engine=heuristic", json=bad).status_code == 422
