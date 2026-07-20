"""
Seasonality agent — computes recurring calendar patterns (which month tends
to be bullish/bearish, which weekday) from daily close-to-close returns.
"""

import logging
from datetime import datetime, timezone

from app.db import get_candles, upsert_seasonality

logger = logging.getLogger(__name__)

MONTH_NAMES = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
               "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
WEEKDAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def _daily_returns(symbol: str) -> list[tuple[datetime, float]]:
    rows = get_candles(symbol, "1d", limit=10_000)
    returns = []
    prev_close = None
    for r in rows:
        dt = datetime.fromtimestamp(r["ts"], tz=timezone.utc)
        if prev_close is not None and prev_close != 0:
            returns.append((dt, (r["close"] - prev_close) / prev_close))
        prev_close = r["close"]
    return returns


def _bucket_stats(returns: list[tuple[datetime, float]], key_fn) -> dict[str, dict]:
    buckets: dict[str, list[float]] = {}
    for dt, ret in returns:
        key = key_fn(dt)
        buckets.setdefault(key, []).append(ret)

    stats = {}
    for key, rets in buckets.items():
        wins = sum(1 for r in rets if r > 0)
        stats[key] = {
            "avg_return": sum(rets) / len(rets),
            "win_rate": wins / len(rets),
            "sample_size": len(rets),
        }
    return stats


def run_for_symbol(symbol: str):
    returns = _daily_returns(symbol)
    if len(returns) < 30:
        logger.info(f"Not enough daily history for {symbol} seasonality ({len(returns)} days)")
        return

    month_stats = _bucket_stats(returns, lambda dt: MONTH_NAMES[dt.month - 1])
    for month, s in month_stats.items():
        upsert_seasonality(symbol, "month", month, s["avg_return"], s["win_rate"], s["sample_size"])

    weekday_stats = _bucket_stats(returns, lambda dt: WEEKDAY_NAMES[dt.weekday()])
    for weekday, s in weekday_stats.items():
        upsert_seasonality(symbol, "weekday", weekday, s["avg_return"], s["win_rate"], s["sample_size"])

    logger.info(f"Seasonality agent: updated month+weekday stats for {symbol} "
                f"({len(returns)} daily returns)")


def run_all(symbols: list[str]):
    for symbol in symbols:
        run_for_symbol(symbol)
