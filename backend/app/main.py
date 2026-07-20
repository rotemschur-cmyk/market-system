import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import json

from app import config, webhooks, scheduler
from app.db import (
    init_db, get_candles, get_zones, get_seasonality, get_cot_reports,
    get_institutional_view, get_recent_news,
)
from app.ingestion import backfill, cot
from app.agents import news_agent, zones_agent, seasonality_agent, institutional_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Market Intelligence System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router)


@app.on_event("startup")
async def on_startup():
    init_db()
    logger.info("DB initialized. Symbols: %s", config.SYMBOLS)

    # First-boot bootstrap: seed history + COT + one pass of the derived
    # agents so the dashboard isn't empty before the scheduler's first tick.
    if not backfill.has_history("BTCUSD"):
        logger.info("No history yet — running initial backfill + COT ingest")
        await asyncio.to_thread(backfill.backfill_all)
        await asyncio.to_thread(cot.ingest_all)
        await asyncio.to_thread(zones_agent.run_all, config.SYMBOLS, config.TIMEFRAMES)
        await asyncio.to_thread(seasonality_agent.run_all, config.SYMBOLS)

    scheduler.start()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/symbols")
def api_symbols():
    return [{"symbol": s, **config.SYMBOL_META[s]} for s in config.SYMBOLS]


@app.get("/api/candles/{symbol}/{timeframe}")
def api_candles(symbol: str, timeframe: str, limit: int = 500):
    return [dict(r) for r in get_candles(symbol, timeframe, limit=limit)]


@app.get("/api/zones/{symbol}/{timeframe}")
def api_zones(symbol: str, timeframe: str):
    return [dict(r) for r in get_zones(symbol, timeframe)]


@app.get("/api/seasonality/{symbol}/{bucket_type}")
def api_seasonality(symbol: str, bucket_type: str):
    return [dict(r) for r in get_seasonality(symbol, bucket_type)]


@app.get("/api/cot/{symbol}")
def api_cot(symbol: str, limit: int = 26):
    return [dict(r) for r in get_cot_reports(symbol, limit=limit)]


@app.get("/api/institutional/{symbol}")
def api_institutional(symbol: str):
    row = get_institutional_view(symbol)
    return dict(row) if row else {}


@app.get("/api/news")
def api_news(limit: int = 50):
    return [dict(r) for r in get_recent_news(limit=limit)]


@app.get("/stream/news")
async def stream_news():
    async def event_generator():
        last_id = 0
        rows = get_recent_news(limit=1)
        if rows:
            last_id = rows[0]["id"]
        while True:
            await asyncio.sleep(3)
            rows = get_recent_news(limit=20)
            new_rows = [r for r in rows if r["id"] > last_id]
            for r in reversed(new_rows):
                last_id = max(last_id, r["id"])
                yield f"data: {json.dumps(dict(r), default=str)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---- Manual admin triggers (disabled unless ADMIN_TOKEN is set) ----------

def _require_admin(x_admin_token: str | None):
    if not config.ADMIN_TOKEN or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=404)


@app.post("/api/admin/run/news")
async def run_news(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    count = await news_agent.run_news_cycle()
    return {"posted": count}


@app.post("/api/admin/run/zones")
def run_zones(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    zones_agent.run_all(config.SYMBOLS, config.TIMEFRAMES)
    return {"ok": True}


@app.post("/api/admin/run/seasonality")
def run_seasonality(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    seasonality_agent.run_all(config.SYMBOLS)
    return {"ok": True}


@app.post("/api/admin/run/institutional")
def run_institutional(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    institutional_agent.run_all(config.SYMBOLS)
    return {"ok": True}


@app.post("/api/admin/run/backfill")
def run_backfill(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    backfill.backfill_all()
    cot.ingest_all()
    return {"ok": True}


# ---- Static dashboard (must be mounted last so it doesn't shadow the API
# routes above) — lets the whole system run as a single container/process
# on any host (Railway/Render/Fly/VPS) with no separate web server needed. ----

_FRONTEND_CANDIDATES = [
    Path(__file__).parent.parent / "frontend",          # Docker image layout
    Path(__file__).parent.parent.parent / "frontend",    # local dev (repo layout)
]
_frontend_dir = next((p for p in _FRONTEND_CANDIDATES if p.exists()), None)
if _frontend_dir:
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
else:
    logger.warning("Frontend directory not found — dashboard will not be served")
