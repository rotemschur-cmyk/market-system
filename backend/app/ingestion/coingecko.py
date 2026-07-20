"""
Bitcoin backfill via the free, keyless CoinGecko public API.

Confirmed reliable (unlike Yahoo Finance, which frequently 429s cloud/VPS
IPs): https://api.coingecko.com/api/v3

Two calls are combined because CoinGecko's OHLC granularity auto-scales
with the `days` window and there's no way to request "daily OHLC over
years" directly on the free tier:
  - /market_chart (days=365) -> daily close prices, ~1 year. Good enough
    for seasonality (which only needs close-to-close daily returns).
    Stored as degenerate candles (open=high=low=close) on timeframe '1d'.
  - /ohlc (days=30) -> real OHLC candles at ~4h spacing, ~30 days. Stored
    on timeframe '4h' so the chart/zones agent has real wicks recently.
"""

import logging
import urllib.request
import json

from app.db import upsert_candle

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3/coins/bitcoin"
HEADERS = {"User-Agent": "market-system-backfill/1.0"}


def _get_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def backfill_bitcoin():
    try:
        data = _get_json(f"{BASE_URL}/market_chart?vs_currency=usd&days=365")
        for ts_ms, price in data.get("prices", []):
            ts = int(ts_ms // 1000)
            upsert_candle("BTCUSD", "1d", ts, price, price, price, price, 0, source="backfill")
        logger.info(f"CoinGecko: backfilled {len(data.get('prices', []))} daily BTCUSD closes")
    except Exception as e:
        logger.warning(f"CoinGecko market_chart backfill failed: {e}")

    try:
        candles = _get_json(f"{BASE_URL}/ohlc?vs_currency=usd&days=30")
        for ts_ms, o, h, l, c in candles:
            ts = int(ts_ms // 1000)
            upsert_candle("BTCUSD", "4h", ts, o, h, l, c, 0, source="backfill")
        logger.info(f"CoinGecko: backfilled {len(candles)} 4h BTCUSD OHLC candles")
    except Exception as e:
        logger.warning(f"CoinGecko ohlc backfill failed: {e}")
