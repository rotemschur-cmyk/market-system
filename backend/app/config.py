import os
from dotenv import load_dotenv

load_dotenv()

# Groq (not Gemini) — genuinely free, no billing/card required, unlike every
# Gemini free-tier key tested (all returned 429 limit:0 without billing
# enabled). Get a free key at https://console.groq.com/keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Shared secret TradingView must include in the alert message so /webhook/tradingview
# can reject requests that didn't actually come from our Pine Script alerts.
TRADINGVIEW_WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")

# Primary source for gold/silver historical backfill — Yahoo Finance (yfinance)
# is unreliable on cloud/VPS IPs (confirmed 429s in testing), so the system
# depends on this instead. Free, no card, instant signup:
# https://twelvedata.com/pricing
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

# Optional token to enable the manual /api/admin/run/{agent} trigger endpoints
# (useful for testing/ops). Left empty by default -> those endpoints are disabled.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

# Internal symbol keys used throughout the system.
SYMBOLS = ["XAUUSD", "XAGUSD", "BTCUSD"]

SYMBOL_META = {
    "XAUUSD": {
        "label": "זהב",
        "yfinance_ticker": "GC=F",
        "tradingview_symbol": "OANDA:XAUUSD",
    },
    "XAGUSD": {
        "label": "כסף",
        "yfinance_ticker": "SI=F",
        "tradingview_symbol": "OANDA:XAGUSD",
    },
    "BTCUSD": {
        "label": "ביטקוין",
        "yfinance_ticker": "BTC-USD",
        "tradingview_symbol": "BINANCE:BTCUSDT",
    },
}

# CFTC COT report codes (Legacy Futures-Only report, CME Group).
COT_CFTC_CODES = {
    "XAUUSD": "088691",  # Gold - Commodity Exchange Inc.
    "XAGUSD": "084691",  # Silver - Commodity Exchange Inc.
    "BTCUSD": "133741",  # Bitcoin - Chicago Mercantile Exchange
}

TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"]
BACKFILL_TIMEFRAMES = ["1h", "1d"]

# How often each background agent runs.
NEWS_INTERVAL_MINUTES = int(os.getenv("NEWS_INTERVAL_MINUTES", "15"))
ZONES_INTERVAL_MINUTES = int(os.getenv("ZONES_INTERVAL_MINUTES", "60"))
SEASONALITY_INTERVAL_MINUTES = int(os.getenv("SEASONALITY_INTERVAL_MINUTES", "720"))
BACKFILL_INTERVAL_MINUTES = int(os.getenv("BACKFILL_INTERVAL_MINUTES", "360"))
COT_INTERVAL_MINUTES = int(os.getenv("COT_INTERVAL_MINUTES", "1440"))
INSTITUTIONAL_INTERVAL_MINUTES = int(os.getenv("INSTITUTIONAL_INTERVAL_MINUTES", "180"))

MAX_ARTICLES_PER_CYCLE = int(os.getenv("MAX_ARTICLES_PER_CYCLE", "20"))
MIN_IMPORTANCE_SCORE = int(os.getenv("MIN_IMPORTANCE_SCORE", "7"))

NEWS_SOURCES = [
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "weight": 10},
    {"name": "Reuters Markets", "url": "https://feeds.reuters.com/reuters/USmarketsnews", "weight": 10},
    {"name": "WSJ Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "weight": 9},
    {"name": "WSJ Economy", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "weight": 8},
    {"name": "CNBC Markets", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "weight": 9},
    {"name": "CNBC Economy", "url": "https://www.cnbc.com/id/20910274/device/rss/rss.html", "weight": 8},
    {"name": "CNBC Finance", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "weight": 8},
    {"name": "MarketWatch Top", "url": "https://www.marketwatch.com/rss/topstories", "weight": 8},
    {"name": "MarketWatch Economy", "url": "https://www.marketwatch.com/rss/economy", "weight": 9},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex", "weight": 7},
    {"name": "AP Business", "url": "https://apnews.com/apf-business", "weight": 8},
    {"name": "Investing.com Commodities", "url": "https://www.investing.com/rss/news_14.rss", "weight": 9},
    {"name": "Investing.com Economy", "url": "https://www.investing.com/rss/news_25.rss", "weight": 8},
    {"name": "FXStreet", "url": "https://www.fxstreet.com/rss/news", "weight": 8},
    {"name": "Federal Reserve News", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "weight": 10},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "weight": 8},
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "weight": 7},
]

HIGH_PRIORITY_KEYWORDS = [
    "fed", "federal reserve", "interest rate", "inflation", "cpi", "pce",
    "gdp", "recession", "gold", "xau", "silver", "xag", "precious metals",
    "dollar", "usd", "treasury", "yields", "fomc", "powell", "rate hike",
    "rate cut", "tariff", "trade war", "sanctions", "geopolitical", "war",
    "crisis", "oil", "crude", "commodities", "debt ceiling", "default",
    "jobs report", "unemployment", "nonfarm payroll", "pmi", "ism",
    "retail sales", "bank crisis", "china", "japan", "euro", "stagflation",
    "quantitative easing", "qe", "qt", "tightening", "safe haven",
    "risk off", "risk on", "trump", "bitcoin", "crypto", "cryptocurrency",
    "btc", "etf", "sec", "halving", "blackrock", "coinbase", "binance",
]
