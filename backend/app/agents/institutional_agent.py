"""
Institutional-view agent — "how does a big institutional/smart-money player
see this market", combining two independent signals:

1. COT positioning: net non-commercial (speculative/leveraged) position and
   how it's trending over the last several weekly reports — extreme or
   fast-changing readings often precede reversals.
2. Smart Money Concepts (SMC) price structure: swing structure to detect
   Break of Structure (BOS, trend continuation) vs Change of Character
   (CHOCH, potential reversal), plus the most recent order block (last
   opposite-direction candle before a strong impulse) and an equal
   highs/lows liquidity pool (a classic stop-hunt target).

Groq (see app/llm.py) turns the two signals into one short Hebrew
narrative, reusing the prompt style of news_bot/forex_factory.py's
morning briefing.
"""

import logging

from app import config, llm
from app.db import get_candles, get_cot_reports, upsert_institutional_view

logger = logging.getLogger(__name__)

SWING_WINDOW = 3


# ---- COT positioning ----------------------------------------------------

def _cot_bias(symbol: str) -> dict:
    reports = get_cot_reports(symbol, limit=12)
    if len(reports) < 2:
        return {"bias": "אין מספיק נתוני COT", "net_change": 0, "net_now": 0}

    def net(r):
        return r["noncommercial_long"] - r["noncommercial_short"]

    net_now = net(reports[-1])
    net_prev = net(reports[-2])
    net_series = [net(r) for r in reports]
    avg_abs = sum(abs(n) for n in net_series) / len(net_series)

    if net_now > avg_abs * 1.3:
        bias = "פוזיציה ספקולטיבית נטו-לונג קיצונית — סיכון לתיקון/מימוש רווחים"
    elif net_now < -avg_abs * 1.3:
        bias = "פוזיציה ספקולטיבית נטו-שורט קיצונית — סיכון לשורט-סקוויז"
    elif net_now > net_prev:
        bias = "כסף ספקולטיבי ממשיך לבנות פוזיציית לונג"
    elif net_now < net_prev:
        bias = "כסף ספקולטיבי ממשיך לבנות פוזיציית שורט"
    else:
        bias = "פוזיציה ספקולטיבית יציבה יחסית"

    return {"bias": bias, "net_change": net_now - net_prev, "net_now": net_now}


# ---- Smart Money Concepts price structure --------------------------------

def _swings(rows: list) -> list[dict]:
    swings = []
    n = len(rows)
    for i in range(SWING_WINDOW, n - SWING_WINDOW):
        window_high = [r["high"] for r in rows[i - SWING_WINDOW: i + SWING_WINDOW + 1]]
        window_low = [r["low"] for r in rows[i - SWING_WINDOW: i + SWING_WINDOW + 1]]
        if rows[i]["high"] == max(window_high):
            swings.append({"i": i, "type": "high", "price": rows[i]["high"]})
        if rows[i]["low"] == min(window_low):
            swings.append({"i": i, "type": "low", "price": rows[i]["low"]})
    swings.sort(key=lambda s: s["i"])
    return swings


def _smc_structure(symbol: str, timeframe: str = "1h") -> dict:
    rows = get_candles(symbol, timeframe, limit=500)
    if len(rows) < SWING_WINDOW * 2 + 5:
        return {"structure": "אין מספיק נתונים למבנה מחיר", "order_block": None, "liquidity": None}

    swings = _swings(rows)
    highs = [s for s in swings if s["type"] == "high"]
    lows = [s for s in swings if s["type"] == "low"]

    structure = "לא ברור"
    if len(highs) >= 2 and len(lows) >= 2:
        last_close = rows[-1]["close"]
        prev_high = highs[-2]["price"]
        prev_low = lows[-2]["price"]
        if last_close > prev_high:
            structure = "BOS כלפי מעלה — המשך מגמת עלייה"
        elif last_close < prev_low:
            structure = "BOS כלפי מטה — המשך מגמת ירידה"
        elif highs[-1]["price"] < prev_high and lows[-1]["price"] < prev_low:
            structure = "CHOCH פוטנציאלי — סימני חולשה במגמת העלייה"
        elif lows[-1]["price"] > prev_low and highs[-1]["price"] > prev_high:
            structure = "CHOCH פוטנציאלי — סימני התחזקות במגמת הירידה"
        else:
            structure = "מבנה מחיר בטווח (consolidation)"

    # Order block: last opposite-colour candle before the strongest recent impulse move.
    order_block = None
    if len(rows) > 10:
        moves = [(i, rows[i]["close"] - rows[i]["open"]) for i in range(len(rows) - 10, len(rows))]
        idx, move = max(moves, key=lambda m: abs(m[1]))
        impulse_up = move > 0
        for j in range(idx - 1, max(idx - 6, -1), -1):
            candle_up = rows[j]["close"] > rows[j]["open"]
            if candle_up != impulse_up:
                order_block = {
                    "kind": "bullish" if impulse_up else "bearish",
                    "low": rows[j]["low"], "high": rows[j]["high"],
                }
                break

    # Equal highs/lows liquidity pool (classic stop-hunt target).
    liquidity = None
    tolerance = 0.0015
    for group, kind in ((highs, "buy-side"), (lows, "sell-side")):
        prices = [s["price"] for s in group[-6:]]
        for a in range(len(prices)):
            for b in range(a + 1, len(prices)):
                if prices[a] != 0 and abs(prices[a] - prices[b]) / prices[a] <= tolerance:
                    liquidity = {"kind": kind, "level": round((prices[a] + prices[b]) / 2, 4)}
                    break

    return {"structure": structure, "order_block": order_block, "liquidity": liquidity}


# ---- Groq narrative ---------------------------------------------------------

SYSTEM_PROMPT = """אתה סוחר מוסדי ותיק (Smart Money) שמסביר איך גופים גדולים - בנקים, קרנות גידור,
market makers - כנראה רואים את השוק כרגע. אתה כותב בעברית, תמציתי ומקצועי, לא סתם ריטייל."""

PROMPT_TEMPLATE = """נכס: {label}

**נתוני COT (פוזיציונינג ספקולטיבי, {report_date}):**
{cot_bias}
שינוי נטו משבוע קודם: {net_change}

**מבנה מחיר (Smart Money Concepts, {timeframe}):**
{structure}
Order Block אחרון: {order_block}
Liquidity Pool קרוב: {liquidity}

כתוב ניתוח קצר (3-4 משפטים) בעברית שמסביר איך "הכסף החכם" כנראה רואה את השוק כרגע,
ומה זה אומר לגבי התרחיש הסביר הבא. אל תיתן המלצת השקעה ישירה, רק פרשנות מבנית."""


def _llm_narrative(symbol: str, label: str, cot: dict, smc: dict, report_date: str) -> str:
    if not config.GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY לא מוגדר — לא ניתן להפיק ניתוח."
    try:
        user_prompt = PROMPT_TEMPLATE.format(
            label=label, report_date=report_date, cot_bias=cot["bias"], net_change=cot["net_change"],
            timeframe="1h", structure=smc["structure"],
            order_block=smc["order_block"] or "אין", liquidity=smc["liquidity"] or "אין",
        )
        return llm.chat(SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        logger.error(f"Institutional narrative error for {symbol}: {e}")
        return "לא ניתן ליצור ניתוח כרגע."


def run_for_symbol(symbol: str):
    label = config.SYMBOL_META[symbol]["label"]
    cot = _cot_bias(symbol)
    smc = _smc_structure(symbol)
    reports = get_cot_reports(symbol, limit=1)
    report_date = reports[-1]["report_date"] if reports else "לא זמין"

    narrative = _llm_narrative(symbol, label, cot, smc, report_date)
    upsert_institutional_view(symbol, narrative, cot["bias"], smc["structure"])
    logger.info(f"Institutional agent updated for {symbol}")


def run_all(symbols: list[str]):
    for symbol in symbols:
        run_for_symbol(symbol)
