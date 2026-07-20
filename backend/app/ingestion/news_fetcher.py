"""
RSS fetching for the news agent — ported from news_bot/news_fetcher.py,
generalized so keyword scoring also covers silver/bitcoin, and dedup goes
through the new news_alerts table instead of Telegram's posted_articles.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

import hashlib

from app import config
from app.db import is_news_seen

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def make_hash(title: str, url: str = "") -> str:
    content = f"{title}{url}".lower().strip()
    return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Article:
    title: str
    source: str
    url: str
    summary: str
    published: Optional[datetime]
    keyword_score: int


def _keyword_score(text: str) -> int:
    text_lower = text.lower()
    return sum(1 for kw in config.HIGH_PRIORITY_KEYWORDS if kw in text_lower)


def _parse_entry(entry, source_name: str) -> Optional[Article]:
    title = getattr(entry, "title", "").strip()
    url = getattr(entry, "link", "").strip()
    if not title:
        return None

    summary = ""
    if hasattr(entry, "summary"):
        soup = BeautifulSoup(entry.summary, "lxml")
        summary = soup.get_text(separator=" ", strip=True)[:800]
    elif hasattr(entry, "content"):
        soup = BeautifulSoup(entry.content[0].value, "lxml")
        summary = soup.get_text(separator=" ", strip=True)[:800]

    published = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass

    score = _keyword_score(title + " " + summary)
    return Article(title=title, source=source_name, url=url, summary=summary,
                    published=published, keyword_score=score)


async def _fetch_feed(client: httpx.AsyncClient, source: dict) -> list[Article]:
    articles = []
    try:
        response = await client.get(source["url"], timeout=15, follow_redirects=True)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        for entry in feed.entries[:15]:
            article = _parse_entry(entry, source["name"])
            if article and not is_news_seen(make_hash(article.title, article.url)):
                articles.append(article)
    except Exception as e:
        logger.warning(f"Failed to fetch {source['name']}: {e}")
    return articles


async def fetch_all_news() -> list[Article]:
    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [_fetch_feed(client, src) for src in config.NEWS_SOURCES]
        results = await asyncio.gather(*tasks)

    all_articles: list[Article] = []
    for articles in results:
        all_articles.extend(articles)

    seen_titles: set[str] = set()
    unique: list[Article] = []
    for art in all_articles:
        key = art.title.lower()[:80]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(art)

    unique.sort(
        key=lambda a: (a.keyword_score, a.published or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    return unique[:config.MAX_ARTICLES_PER_CYCLE]
