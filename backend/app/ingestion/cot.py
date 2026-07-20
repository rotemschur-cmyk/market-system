"""
CFTC Commitment of Traders (COT) ingestion — free, public, no auth.

Gold/Silver use the Legacy Futures-Only report (Socrata dataset 6dca-aqww),
which reports simple commercial vs non-commercial long/short.

Bitcoin (CME futures) only appears in the newer Traders in Financial
Futures report (gpe5-46if), which splits positions into
dealer/asset-manager/leveraged-funds/other instead of commercial/
non-commercial. We map that onto the same schema as a proxy:
  - "commercial"    ~= dealer + asset manager (hedgers/institutions)
  - "non-commercial" ~= leveraged funds (speculative money, hedge funds)
"""

import logging
import urllib.request
import urllib.parse
import json

from app import config
from app.db import upsert_cot_report

logger = logging.getLogger(__name__)

LEGACY_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
HEADERS = {"User-Agent": "market-system/1.0"}


def _query(base_url: str, code: str, limit: int) -> list[dict]:
    params = {
        "$where": f"cftc_contract_market_code='{code}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(limit),
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _ingest_legacy(symbol: str, code: str, limit: int):
    rows = _query(LEGACY_URL, code, limit)
    for row in rows:
        upsert_cot_report(
            symbol=symbol,
            report_date=row["report_date_as_yyyy_mm_dd"][:10],
            commercial_long=int(row["comm_positions_long_all"]),
            commercial_short=int(row["comm_positions_short_all"]),
            noncommercial_long=int(row["noncomm_positions_long_all"]),
            noncommercial_short=int(row["noncomm_positions_short_all"]),
            open_interest=int(row["open_interest_all"]),
        )
    logger.info(f"COT: ingested {len(rows)} legacy reports for {symbol}")


def _ingest_tff(symbol: str, code: str, limit: int):
    rows = _query(TFF_URL, code, limit)
    for row in rows:
        commercial_long = int(row["dealer_positions_long_all"]) + int(row["asset_mgr_positions_long"])
        commercial_short = int(row["dealer_positions_short_all"]) + int(row["asset_mgr_positions_short"])
        upsert_cot_report(
            symbol=symbol,
            report_date=row["report_date_as_yyyy_mm_dd"][:10],
            commercial_long=commercial_long,
            commercial_short=commercial_short,
            noncommercial_long=int(row["lev_money_positions_long"]),
            noncommercial_short=int(row["lev_money_positions_short"]),
            open_interest=int(row["open_interest_all"]),
        )
    logger.info(f"COT: ingested {len(rows)} TFF reports for {symbol}")


def ingest_symbol(symbol: str, limit: int = 104):
    code = config.COT_CFTC_CODES.get(symbol)
    if not code:
        return
    try:
        if symbol == "BTCUSD":
            _ingest_tff(symbol, code, limit)
        else:
            _ingest_legacy(symbol, code, limit)
    except Exception as e:
        logger.warning(f"COT ingestion failed for {symbol}: {e}")


def ingest_all():
    for symbol in config.SYMBOLS:
        ingest_symbol(symbol)
