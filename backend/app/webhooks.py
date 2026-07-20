"""
Receives live candle data from TradingView alerts.

Setup (per symbol, per timeframe you care about — see README for the full
Pine Script alert template):
  1. Open the symbol's chart on TradingView (e.g. OANDA:XAUUSD).
  2. Create an alert, condition "Once Per Bar Close", any timeframe.
  3. In the alert's "Message" field, paste the JSON template from the
     README (it uses TradingView's {{ticker}}/{{interval}}/{{open}}/...
     placeholders — TradingView fills them in before sending).
  4. In "Notifications" -> "Webhook URL", set this server's
     https://your-domain/webhook/tradingview

The alert message must include the shared secret (TRADINGVIEW_WEBHOOK_SECRET)
so random internet traffic can't inject fake candles.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException

from app import config
from app.db import upsert_candle

logger = logging.getLogger(__name__)
router = APIRouter()

# TradingView {{ticker}} -> our internal symbol key.
_TICKER_TO_SYMBOL = {
    meta["tradingview_symbol"]: symbol for symbol, meta in config.SYMBOL_META.items()
}
# Also accept the bare symbol (no exchange prefix), e.g. "XAUUSD".
for _symbol, _meta in config.SYMBOL_META.items():
    _bare = _meta["tradingview_symbol"].split(":")[-1]
    _TICKER_TO_SYMBOL.setdefault(_bare, _symbol)
_TICKER_TO_SYMBOL.setdefault("BTCUSDT", "BTCUSD")

# TradingView {{interval}} -> our internal timeframe key.
_INTERVAL_TO_TIMEFRAME = {
    "15": "15m", "60": "1h", "240": "4h", "D": "1d", "1D": "1d", "W": "1w", "1W": "1w",
}


def _parse_time(raw) -> int:
    if isinstance(raw, (int, float)):
        # TradingView {{time}} can also render as epoch millis.
        return int(raw / 1000) if raw > 10_000_000_000 else int(raw)
    if isinstance(raw, str):
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    return int(datetime.now(timezone.utc).timestamp())


@router.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
    body = await request.json()

    if body.get("secret") != config.TRADINGVIEW_WEBHOOK_SECRET or not config.TRADINGVIEW_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid or missing secret")

    raw_symbol = str(body.get("symbol", ""))
    symbol = _TICKER_TO_SYMBOL.get(raw_symbol, raw_symbol if raw_symbol in config.SYMBOLS else None)
    if symbol is None:
        raise HTTPException(status_code=400, detail=f"unknown symbol '{raw_symbol}'")

    raw_tf = str(body.get("timeframe", ""))
    timeframe = _INTERVAL_TO_TIMEFRAME.get(raw_tf, raw_tf if raw_tf in config.TIMEFRAMES else None)
    if timeframe is None:
        raise HTTPException(status_code=400, detail=f"unknown timeframe '{raw_tf}'")

    try:
        ts = _parse_time(body.get("time"))
        o, h, l, c = (float(body[k]) for k in ("open", "high", "low", "close"))
        v = float(body.get("volume", 0) or 0)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"malformed candle payload: {e}")

    upsert_candle(symbol=symbol, timeframe=timeframe, ts=ts, o=o, h=h, l=l, c=c, v=v, source="webhook")
    logger.info(f"webhook candle: {symbol}/{timeframe} @ {ts} close={c}")
    return {"ok": True, "symbol": symbol, "timeframe": timeframe, "ts": ts}
