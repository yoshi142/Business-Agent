import json
from pathlib import Path

from bizagent import mini as M
from bizagent.cli import main

EX = Path(__file__).resolve().parent.parent / "examples"


def test_read_reviews_csv():
    rs = M.read_reviews_csv(EX / "mini_reviews.csv")
    assert len(rs) == 5 and rs[1].rating == 2 and rs[0].id == "1"


def test_dry_run_costs_are_small():
    shop = M.ShopInfo(**json.loads((EX / "mini_shop.json").read_text(encoding="utf-8")))
    usd, yen = M.run_sns(shop, dry_run=True)
    assert 0 < yen < 200
    biz = M.BusinessInfo(**json.loads((EX / "mini_business.json").read_text(encoding="utf-8")))
    assert 0 < M.run_inquiry(biz, dry_run=True)[1] < 200


def test_prompts_contain_inputs():
    shop = M.ShopInfo(name="喫茶ひだまり", business="カフェ", features="自家焙煎", month="2026-11")
    assert "2026-11" in M.build_sns_prompt(shop) and "自家焙煎" in M.build_sns_prompt(shop)
    p = M.build_review_prompt("店", "カフェ", "丁寧", M.read_reviews_csv(EX / "mini_reviews.csv"))
    assert "id=5 評価=1" in p


def _fake_call(system, user, output_model, purpose, model=None):
    if output_model is M.PostPlan:
        return M.PostPlan(
            shop_name="喫茶ひだまり",
            month="2026-11",
            posts=[M.Post(day=d, theme="t", text="本文", hashtags=["横浜カフェ", "#港北区"], image_idea="写真") for d in range(1, 31)],
            notes=["a", "b", "c"],
        )
    if output_model is M.ReviewReplyPlan:
        return M.ReviewReplyPlan(
            shop_name="喫茶ひだまり",
            replies=[M.ReviewReply(id="1", rating=5, reply="ありがとうございます", needs_attention=False, reason=""),
                     M.ReviewReply(id="5", rating=1, reply="申し訳ありません", needs_attention=True, reason="会計の確認")],
            summary="概ね好評",
            improvements=["待ち時間の案内"],
        )
    return M.InquiryTemplateSet(
        business_name="さくら整骨院",
        templates=[M.InquiryTemplate(situation=f"s{i}", subject=f"件名{i}", body="{{お名前}} 様", followup="") for i in range(10)],
        usage_notes=["x", "y", "z"],
    )


def test_cli_mini_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "_call", _fake_call)
    out = tmp_path / "d"
    assert main(["mini", "--out-dir", str(out), "sns", "--json", str(EX / "mini_shop.json")]) == 0
    csv_text = (out / "sns_posts.csv").read_text(encoding="utf-8-sig")
    assert csv_text.count("\n") == 31 and "#横浜カフェ #港北区" in csv_text
    assert "## 2026-11-01" in (out / "sns_posts.md").read_text(encoding="utf-8")

    assert main(["mini", "--out-dir", str(out), "reviews", "--csv", str(EX / "mini_reviews.csv"), "--name", "喫茶ひだまり", "--business", "カフェ"]) == 0
    md = (out / "review_replies.md").read_text(encoding="utf-8")
    assert "【要確認】会計の確認" in md and "## 改善候補" in md

    assert main(["mini", "--out-dir", str(out), "inquiry", "--json", str(EX / "mini_business.json")]) == 0
    assert (out / "inquiry_templates.md").read_text(encoding="utf-8").count("## ") == 11


def test_cli_dry_run_does_not_call_api(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("API が呼ばれた")

    monkeypatch.setattr(M, "_call", boom)
    assert main(["mini", "--dry-run", "sns", "--json", str(EX / "mini_shop.json")]) == 0
    assert "概算費用" in capsys.readouterr().out
