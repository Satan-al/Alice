import feedparser, requests, io, re, random, time
from datetime import datetime, timezone

# порядок = приоритет
FEEDS = [
    "https://meduza.io/rss/all",
    "https://agents.media/rss",                       # зеркало «Агентства»
    "https://ovdinfo.org/feed",
    "https://www.currenttime.tv/api/zrzkqp$rss",
    "https://www.bbc.com/russian/index.xml",
    "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "https://www.interfax.ru/rss.asp",
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
CACHE_TTL = 300      # 5 мин
_cache = {"ts": 0, "entries": []}


def _clean(txt: str) -> str:
    return HTML_TAG_RE.sub("", txt or "").strip()


def _fetch(url: str, timeout: int = 2):
    """Скачиваем фид с таймаутом 2 с. Возвращаем список записей-сегодня."""
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = feedparser.parse(io.BytesIO(r.content))
    except Exception as e:
        print("FEED_FAIL:", url, e)
        return []

    today = datetime.now(timezone.utc).date()
    fresh = []
    for e in data.entries:
        pub = e.get("published_parsed") or e.get("updated_parsed")
        if not pub or datetime(*pub[:6], tzinfo=timezone.utc).date() != today:
            continue

        content = ""
        if e.get("content"):
            content = e["content"][0].get("value", "")
        elif e.get("summary"):
            content = e["summary"]

        fresh.append(
            {
                "title": _clean(e.get("title")),
                "content": _clean(content),
                "link": e.get("link", ""),
            }
        )
    return fresh


def _refresh_cache():
    """Идём по списку; берём первый фид, у которого сегодня есть новости."""
    for url in FEEDS:
        entries = _fetch(url)
        if entries:                     # нашли – сохраняем и выходим
            _cache["entries"] = entries
            _cache["ts"] = time.time()
            print(f"CACHE_REFRESH: {len(entries)} news from {url}")
            return
    # ни один фид не дал новостей
    _cache["entries"] = []
    _cache["ts"] = time.time()
    print("CACHE_REFRESH: 0 news")


def _ensure_cache():
    if time.time() - _cache["ts"] > CACHE_TTL:
        _refresh_cache()


def get_random_news_today() -> dict:
    try:
        _ensure_cache()
        if not _cache["entries"]:
            return {"title": "На сегодня свежих новостей пока нет.",
                    "content": "", "link": ""}
        return random.choice(_cache["entries"])
    except Exception as e:
        print("NEWS_FETCH_ERROR:", e)
        return {"title": "Сейчас не удалось загрузить новости.",
                "content": "", "link": ""}
