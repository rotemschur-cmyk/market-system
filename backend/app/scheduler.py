import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app import config
from app.agents import news_agent, zones_agent, seasonality_agent, institutional_agent
from app.ingestion import backfill, cot

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


def _run_zones():
    zones_agent.run_all(config.SYMBOLS, config.TIMEFRAMES)


def _run_seasonality():
    seasonality_agent.run_all(config.SYMBOLS)


def _run_institutional():
    institutional_agent.run_all(config.SYMBOLS)


def _run_backfill():
    backfill.backfill_all()


def _run_cot():
    cot.ingest_all()


def start():
    scheduler.add_job(news_agent.run_news_cycle, trigger=IntervalTrigger(minutes=config.NEWS_INTERVAL_MINUTES),
                       id="news_cycle", replace_existing=True)
    scheduler.add_job(_run_zones, trigger=IntervalTrigger(minutes=config.ZONES_INTERVAL_MINUTES),
                       id="zones_cycle", replace_existing=True)
    scheduler.add_job(_run_seasonality, trigger=IntervalTrigger(minutes=config.SEASONALITY_INTERVAL_MINUTES),
                       id="seasonality_cycle", replace_existing=True)
    scheduler.add_job(_run_institutional, trigger=IntervalTrigger(minutes=config.INSTITUTIONAL_INTERVAL_MINUTES),
                       id="institutional_cycle", replace_existing=True)
    scheduler.add_job(_run_backfill, trigger=IntervalTrigger(minutes=config.BACKFILL_INTERVAL_MINUTES),
                       id="backfill_cycle", replace_existing=True)
    scheduler.add_job(_run_cot, trigger=IntervalTrigger(minutes=config.COT_INTERVAL_MINUTES),
                       id="cot_cycle", replace_existing=True)
    scheduler.start()
    logger.info(
        "Scheduler started: news=%dmin zones=%dmin seasonality=%dmin "
        "institutional=%dmin backfill=%dmin cot=%dmin",
        config.NEWS_INTERVAL_MINUTES, config.ZONES_INTERVAL_MINUTES,
        config.SEASONALITY_INTERVAL_MINUTES, config.INSTITUTIONAL_INTERVAL_MINUTES,
        config.BACKFILL_INTERVAL_MINUTES, config.COT_INTERVAL_MINUTES,
    )
