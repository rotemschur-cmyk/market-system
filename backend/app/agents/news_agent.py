"""
News alert agent — ported from news_bot/analyzer.py, but using Groq
(see app/llm.py) instead of Gemini. market_impact now covers
gold/silver/bitcoin/dollar (instead of gold/stocks/dollar/bonds) since
those are this system's 3 tracked assets. Results are stored in
news_alerts (no Telegram) and served to the dashboard's live feed via SSE
(see main.py's /stream/news).
"""

import logging
import time
from typing import Optional

from app import config, llm
from app.db import insert_news_alert
from app.ingestion.news_fetcher import Article, fetch_all_news, make_hash

logger = logging.getLogger(__name__)

LLM_DELAY_SECONDS = 2  # small courtesy delay between calls

SYSTEM_PROMPT = """אתה אנליסט פיננסי מומחה המתמחה בזהב, כסף וביטקוין.
תפקידך לנתח חדשות ולהסביר כיצד הן משפיעות על:
1. מחיר הזהב (XAU/USD)
2. מחיר הכסף (XAG/USD)
3. ביטקוין (BTC/USD)
4. הדולר האמריקאי (DXY)

כתוב תמיד בעברית. היה תמציתי, מקצועי וממוקד. אתה עונה תמיד ב-JSON תקין בלבד."""

ANALYSIS_PROMPT = """נתח את החדשה הבאה והערך את השפעתה על השווקים:

**כותרת:** {title}
**מקור:** {source}
**תקציר:** {summary}

ענה בפורמט JSON בלבד (ללא טקסט נוסף):
{{
  "importance_score": <מספר 1-10, כאשר 10 = חשוב ביותר>,
  "should_post": <true/false>,
  "headline": "<כותרת קצרה בעברית, עד 80 תווים>",
  "market_impact": {{
    "gold": "<bullish/bearish/neutral>",
    "silver": "<bullish/bearish/neutral>",
    "bitcoin": "<bullish/bearish/neutral>",
    "dollar": "<bullish/bearish/neutral>"
  }},
  "analysis": "<ניתוח קצר בעברית, 2-3 משפטים>",
  "urgency": "<high/medium/low>"
}}

שים לב:
- should_post = true רק אם importance_score >= {min_score}
- importance_score גבוה = חדשות מאקרו-כלכליות גדולות, החלטות ריבית, משברים, נתוני תעסוקה/אינפלציה, אירועי רגולציה/ETF לביטקוין, הצהרות פוליטיות גדולות (כמו טראמפ)
"""

_last_error: str = ""


def analyze_article(article: Article) -> Optional[dict]:
    global _last_error
    if not config.GROQ_API_KEY:
        _last_error = "GROQ_API_KEY not configured"
        return None

    try:
        user_prompt = ANALYSIS_PROMPT.format(
            title=article.title, source=article.source,
            summary=article.summary or "אין תקציר זמין",
            min_score=config.MIN_IMPORTANCE_SCORE,
        )
        time.sleep(LLM_DELAY_SECONDS)
        data = llm.chat_json(SYSTEM_PROMPT, user_prompt)
        _last_error = ""

        impact = data.get("market_impact", {})
        return {
            "importance_score": int(data.get("importance_score", 0)),
            "should_post": bool(data.get("should_post", False)),
            "headline": data.get("headline", article.title),
            "gold_impact": impact.get("gold", "neutral"),
            "silver_impact": impact.get("silver", "neutral"),
            "bitcoin_impact": impact.get("bitcoin", "neutral"),
            "dollar_impact": impact.get("dollar", "neutral"),
            "analysis": data.get("analysis", ""),
            "urgency": data.get("urgency", "low"),
        }
    except Exception as e:
        _last_error = str(e)
        logger.error(f"Analysis error for '{article.title}': {e}")
    return None


async def run_news_cycle() -> int:
    logger.info("=== Starting news cycle ===")
    posted = 0
    try:
        articles = await fetch_all_news()
        logger.info(f"Fetched {len(articles)} candidate articles.")
        for article in articles:
            result = analyze_article(article)
            if result is None:
                continue
            logger.info(
                f"[{article.source}] Score={result['importance_score']} "
                f"Post={result['should_post']} | {article.title[:60]}"
            )
            if result["should_post"]:
                inserted = insert_news_alert(
                    article_hash=make_hash(article.title, article.url),
                    title=article.title, source=article.source, url=article.url,
                    headline=result["headline"], analysis=result["analysis"],
                    importance_score=result["importance_score"], urgency=result["urgency"],
                    gold_impact=result["gold_impact"], silver_impact=result["silver_impact"],
                    bitcoin_impact=result["bitcoin_impact"], dollar_impact=result["dollar_impact"],
                )
                if inserted:
                    posted += 1
    except Exception as e:
        logger.exception(f"Error in news cycle: {e}")
    logger.info(f"=== Cycle complete. Posted {posted} alerts. ===")
    return posted
