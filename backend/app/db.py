import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "market_system.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                ts INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL DEFAULT 0,
                source TEXT DEFAULT 'backfill',
                PRIMARY KEY (symbol, timeframe, ts)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_candles_lookup
            ON candles(symbol, timeframe, ts)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS cot_reports (
                symbol TEXT NOT NULL,
                report_date TEXT NOT NULL,
                commercial_long INTEGER,
                commercial_short INTEGER,
                noncommercial_long INTEGER,
                noncommercial_short INTEGER,
                open_interest INTEGER,
                PRIMARY KEY (symbol, report_date)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_hash TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                url TEXT,
                headline TEXT,
                analysis TEXT,
                importance_score INTEGER,
                urgency TEXT,
                gold_impact TEXT,
                silver_impact TEXT,
                bitcoin_impact TEXT,
                dollar_impact TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_created ON news_alerts(created_at)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                level REAL NOT NULL,
                kind TEXT NOT NULL,
                strength INTEGER NOT NULL,
                touches INTEGER NOT NULL,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_zones_lookup ON zones(symbol, timeframe)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS seasonality_cache (
                symbol TEXT NOT NULL,
                bucket_type TEXT NOT NULL,
                bucket_value TEXT NOT NULL,
                avg_return REAL NOT NULL,
                win_rate REAL NOT NULL,
                sample_size INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, bucket_type, bucket_value)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS institutional_view (
                symbol TEXT PRIMARY KEY,
                narrative TEXT NOT NULL,
                cot_bias TEXT,
                smc_structure TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


def upsert_candle(symbol: str, timeframe: str, ts: int, o: float, h: float,
                   l: float, c: float, v: float = 0, source: str = "backfill"):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO candles (symbol, timeframe, ts, open, high, low, close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, timeframe, ts) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume, source=excluded.source
        """, (symbol, timeframe, ts, o, h, l, c, v, source))
        conn.commit()


def get_candles(symbol: str, timeframe: str, limit: int = 1000) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM candles WHERE symbol = ? AND timeframe = ?
            ORDER BY ts DESC LIMIT ?
        """, (symbol, timeframe, limit)).fetchall()
        return list(reversed(rows))


def replace_zones(symbol: str, timeframe: str, zones: list[dict]):
    with get_connection() as conn:
        conn.execute("DELETE FROM zones WHERE symbol = ? AND timeframe = ?", (symbol, timeframe))
        for z in zones:
            conn.execute("""
                INSERT INTO zones (symbol, timeframe, level, kind, strength, touches)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (symbol, timeframe, z["level"], z["kind"], z["strength"], z["touches"]))
        conn.commit()


def get_zones(symbol: str, timeframe: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM zones WHERE symbol = ? AND timeframe = ? ORDER BY strength DESC
        """, (symbol, timeframe)).fetchall()


def upsert_seasonality(symbol: str, bucket_type: str, bucket_value: str,
                        avg_return: float, win_rate: float, sample_size: int):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO seasonality_cache (symbol, bucket_type, bucket_value, avg_return, win_rate, sample_size)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, bucket_type, bucket_value) DO UPDATE SET
                avg_return=excluded.avg_return, win_rate=excluded.win_rate,
                sample_size=excluded.sample_size, updated_at=CURRENT_TIMESTAMP
        """, (symbol, bucket_type, bucket_value, avg_return, win_rate, sample_size))
        conn.commit()


def get_seasonality(symbol: str, bucket_type: str) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM seasonality_cache WHERE symbol = ? AND bucket_type = ?
            ORDER BY bucket_value
        """, (symbol, bucket_type)).fetchall()


def upsert_cot_report(symbol: str, report_date: str, commercial_long: int,
                       commercial_short: int, noncommercial_long: int,
                       noncommercial_short: int, open_interest: int):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO cot_reports (symbol, report_date, commercial_long, commercial_short,
                noncommercial_long, noncommercial_short, open_interest)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, report_date) DO UPDATE SET
                commercial_long=excluded.commercial_long, commercial_short=excluded.commercial_short,
                noncommercial_long=excluded.noncommercial_long, noncommercial_short=excluded.noncommercial_short,
                open_interest=excluded.open_interest
        """, (symbol, report_date, commercial_long, commercial_short,
              noncommercial_long, noncommercial_short, open_interest))
        conn.commit()


def get_cot_reports(symbol: str, limit: int = 52) -> list[sqlite3.Row]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM cot_reports WHERE symbol = ? ORDER BY report_date DESC LIMIT ?
        """, (symbol, limit)).fetchall()
        return list(reversed(rows))


def is_news_seen(article_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM news_alerts WHERE article_hash = ?", (article_hash,)
        ).fetchone()
        return row is not None


def insert_news_alert(**kwargs) -> bool:
    with get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO news_alerts (article_hash, title, source, url, headline, analysis,
                    importance_score, urgency, gold_impact, silver_impact, bitcoin_impact, dollar_impact)
                VALUES (:article_hash, :title, :source, :url, :headline, :analysis,
                    :importance_score, :urgency, :gold_impact, :silver_impact, :bitcoin_impact, :dollar_impact)
            """, kwargs)
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def get_recent_news(limit: int = 50) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM news_alerts ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()


def upsert_institutional_view(symbol: str, narrative: str, cot_bias: str, smc_structure: str):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO institutional_view (symbol, narrative, cot_bias, smc_structure)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                narrative=excluded.narrative, cot_bias=excluded.cot_bias,
                smc_structure=excluded.smc_structure, updated_at=CURRENT_TIMESTAMP
        """, (symbol, narrative, cot_bias, smc_structure))
        conn.commit()


def get_institutional_view(symbol: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM institutional_view WHERE symbol = ?", (symbol,)
        ).fetchone()
