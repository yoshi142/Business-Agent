"""API 利用量の記録：1回の呼び出しごとにトークン数と概算費用（円）を CSV に追記する。

上限（3万円）に対する消化状況は ledger status に表示される。
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

USAGE_PATH = Path(__file__).resolve().parent.parent / "ledger" / "api_usage.csv"
FIELDS = ["timestamp", "purpose", "model", "input_tokens", "output_tokens", "cache_read_tokens", "usd", "yen"]

# 100万トークンあたりの米ドル価格（2026-10 時点の Claude API 価格表。変更時はここを直す）
PRICES_USD_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
DEFAULT_PRICE = (4.00, 20.00, 0.20)


def usd_per_yen_rate() -> float:
    return float(os.environ.get("BIZAGENT_JPY_PER_USD", "150"))


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0) -> tuple[float, int]:
    pin, pout, pcache = PRICES_USD_PER_MTOK.get(model, DEFAULT_PRICE)
    usd = (input_tokens * pin + output_tokens * pout + cache_read_tokens * pcache) / 1_000_000
    return round(usd, 5), int(round(usd * usd_per_yen_rate()))


def record_usage(purpose: str, model: str, usage, path: Path = USAGE_PATH) -> int:
    """response.usage を受け取り記録する。概算の円を返す。"""
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    usd, yen = estimate_cost(model, input_tokens, output_tokens, cache_read)
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "purpose": purpose,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read,
                "usd": usd,
                "yen": yen,
            }
        )
    return yen


def total_yen(path: Path = USAGE_PATH) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8", newline="") as f:
        return sum(int(float(r["yen"])) for r in csv.DictReader(f))
