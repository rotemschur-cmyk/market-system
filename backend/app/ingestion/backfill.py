"""
One-off / periodic historical backfill so charts, seasonality and zone
detection have years of data from day one instead of waiting weeks for
TradingView webhook alerts to accumulate.

Bitcoin uses CoinGecko (see coingecko.py) — reliable and keyless.

Gold/silver: Yahoo Finance (yfinance) needs no signup but is well known to
429-block cloud/VPS IP ranges (confirmed unreliable in testing). Twelve
Data (free key, https://twelvedata.com/pricing) is the primary source for
gold/silver; yfinance is still tried as a free opportunistic bonus (costs
nothing to attempt, sometimes works depending on the host's IP), but the
system doesn't depend on it. If neither source has data, the symbol simply
starts empty and fills in over time from live TradingView webhook candles
(see webhooks.py).
"""

import logging
from datetime import timezone

import yfinance as yf

from app import config
from app.db import upsert_candle, get_candles
from app.ingestion import coingecko, twelvedata

logger = logging.getLogger(__name__)

# yfinance interval + max lookback period per internal timeframe.
_YF_PARAMS = {
    "1d": {"interval": "1d", "period": "10y"},
    "1h": {"interval": "60m", "period": "730d"},
}


def _backfill_via_yfinance(symbol: str) -> bool:
    ticker = config.SYMBOL_META[symbol]["yfinance_ticker"]
    any_success = False
    for timeframe in config.BACKFILL_TIMEFRAMES:
        params = _YF_PARAMS[timeframe]
        try:
            df = yf.Ticker(ticker).history(
                interval=params["interval"], period=params["period"], auto_adjust=False
            )
        except Exception as e:
            logger.warning(f"yfinance fetch failed for {symbol}/{timeframe}: {e}")
            continue

        if df is None or df.empty:
            logger.warning(f"yfinance returned no data for {symbol}/{timeframe} ({ticker})")
            continue

        count = 0
        for idx, row in df.iterrows():
            ts = int(idx.tz_convert(timezone.utc).timestamp()) if idx.tzinfo else int(idx.timestamp())
            upsert_candle(
                symbol=symbol, timeframe=timeframe, ts=ts,
                o=float(row["Open"]), h=float(row["High"]), l=float(row["Low"]), c=float(row["Close"]),
                v=float(row.get("Volume", 0) or 0), source="backfill",
            )
            count += 1
        logger.info(f"yfinance: backfilled {count} {timeframe} candles for {symbol} ({ticker})")
        any_success = any_success or count > 0
    return any_success


def backfill_symbol(symbol: str):
    if symbol == "BTCUSD":
        coingecko.backfill_bitcoin()
        return

    got_data = False

    if config.TWELVE_DATA_API_KEY:
        twelvedata.backfill_symbol(symbol, config.TWELVE_DATA_API_KEY)
        got_data = has_history(symbol, "1d") or has_history(symbol, "1h")

    # Free opportunistic bonus — costs nothing to try even if Twelve Data
    # already succeeded, since yfinance may cover a timeframe Twelve Data's
    # free tier doesn't.
    yf_ok = _backfill_via_yfinance(symbol)
    got_data = got_data or yf_ok

    if not got_data:
        logger.warning(
            f"No historical backfill source available for {symbol} "
            "(yfinance blocked and TWELVE_DATA_API_KEY not set — get a free key at "
            "https://twelvedata.com/pricing). Will rely on live TradingView webhook "
            "data accumulating over time."
        )


def backfill_all():
    for symbol in config.SYMBOLS:
        backfill_symbol(symbol)


def has_history(symbol: str, timeframe: str = "1d") -> bool:
    return len(get_candles(symbol, timeframe, limit=1)) > 0
