"""
Primary backfill source for gold/silver historical candles.

Yahoo Finance (yfinance) needs no signup but is well known for
429-blocking cloud/VPS IPs (confirmed unreliable in testing), so this is
the source the system actually depends on. Get a free API key (no credit
card, ~10 seconds) at https://twelvedata.com/pricing and set
TWELVE_DATA_API_KEY in .env.

NOTE: spot XAG/USD (silver) 404s on Twelve Data's free "Basic" plan —
"available starting with the Grow or Venture plan" (confirmed in testing;
spot XAU/USD gold, oddly, IS included free). We use SLV (iShares Silver
Trust ETF) as a free proxy instead — it tracks silver spot price closely,
but its own share price (~$50) is what gets stored/displayed, not the
per-ounce spot price. Good enough for charting/seasonality/zones, which
only care about relative price movement, but worth knowing if the number
on screen doesn't match "silver spot price" you see elsewhere.
"""

import logging
import urllib.request
import json
from datetime import datetime, timezone

from app.db import upsert_candle

logger = logging.getLogger(__name__)

_SYMBOL_MAP = {"XAUUSD": "XAU/USD", "XAGUSD": "SLV"}
_INTERVAL_MAP = {"1d": "1day", "1h": "1h"}


def backfill_symbol(symbol: str, api_key: str):
    td_symbol = _SYMBOL_MAP.get(symbol)
    if not td_symbol:
        return

    for timeframe, td_interval in _INTERVAL_MAP.items():
        url = (
            "https://api.twelvedata.com/time_series"
            f"?symbol={td_symbol}&interval={td_interval}&outputsize=5000&apikey={api_key}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "market-system/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)

            if data.get("status") == "error":
                logger.warning(f"Twelve Data error for {symbol}/{timeframe}: {data.get('message')}")
                continue

            values = data.get("values", [])
            count = 0
            for v in values:
                dt = datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S") if " " in v["datetime"] \
                    else datetime.strptime(v["datetime"], "%Y-%m-%d")
                ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
                upsert_candle(
                    symbol=symbol, timeframe=timeframe, ts=ts,
                    o=float(v["open"]), h=float(v["high"]), l=float(v["low"]), c=float(v["close"]),
                    v=float(v.get("volume") or 0), source="backfill",
                )
                count += 1
            logger.info(f"Twelve Data: backfilled {count} {timeframe} candles for {symbol}")
        except Exception as e:
            logger.warning(f"Twelve Data backfill failed for {symbol}/{timeframe}: {e}")
