"""
Key-zone agent — detects support/resistance zones worth watching.

Approach: find local swing highs/lows (fractal pivots: a bar whose high/low
is the most extreme within a +/- window), then cluster nearby pivot prices
together (within a tolerance % of price) into zones. A zone's strength is
how many times price has touched it — more touches = more significant.
"""

import logging

from app.db import get_candles, replace_zones

logger = logging.getLogger(__name__)

PIVOT_WINDOW = 5          # bars on each side that must be less extreme
CLUSTER_TOLERANCE_PCT = 0.006   # 0.6% — pivots within this % of each other merge into one zone
MIN_TOUCHES = 2


def _find_pivots(rows: list) -> tuple[list[float], list[float]]:
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    n = len(rows)

    pivot_highs, pivot_lows = [], []
    for i in range(PIVOT_WINDOW, n - PIVOT_WINDOW):
        window_high = highs[i - PIVOT_WINDOW: i + PIVOT_WINDOW + 1]
        window_low = lows[i - PIVOT_WINDOW: i + PIVOT_WINDOW + 1]
        if highs[i] == max(window_high):
            pivot_highs.append(highs[i])
        if lows[i] == min(window_low):
            pivot_lows.append(lows[i])
    return pivot_highs, pivot_lows


def _cluster(levels: list[float], kind: str) -> list[dict]:
    if not levels:
        return []
    levels = sorted(levels)
    clusters: list[list[float]] = [[levels[0]]]
    for level in levels[1:]:
        cluster_avg = sum(clusters[-1]) / len(clusters[-1])
        if abs(level - cluster_avg) / cluster_avg <= CLUSTER_TOLERANCE_PCT:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    zones = []
    for cluster in clusters:
        touches = len(cluster)
        if touches < MIN_TOUCHES:
            continue
        zones.append({
            "level": round(sum(cluster) / len(cluster), 4),
            "kind": kind,
            "touches": touches,
            "strength": min(10, touches),
        })
    return zones


def detect_zones(symbol: str, timeframe: str) -> list[dict]:
    rows = get_candles(symbol, timeframe, limit=1000)
    if len(rows) < PIVOT_WINDOW * 2 + 1:
        logger.info(f"Not enough {symbol}/{timeframe} candles for zone detection ({len(rows)})")
        return []

    pivot_highs, pivot_lows = _find_pivots(rows)
    zones = _cluster(pivot_highs, "resistance") + _cluster(pivot_lows, "support")
    zones.sort(key=lambda z: z["strength"], reverse=True)
    return zones


def run_zones_for_symbol(symbol: str, timeframes: list[str]):
    for timeframe in timeframes:
        zones = detect_zones(symbol, timeframe)
        replace_zones(symbol, timeframe, zones)
        logger.info(f"Zones agent: {len(zones)} zones for {symbol}/{timeframe}")


def run_all(symbols: list[str], timeframes: list[str]):
    for symbol in symbols:
        run_zones_for_symbol(symbol, timeframes)
