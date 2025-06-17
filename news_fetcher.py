import feedparser, requests, io, re, random, time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

FEEDS = [
    "https://meduza.io/rss/all",
    "https://theins.ru/feed",
    "https://data.ovdinfo.org/ru/rss.xml",
    "https://agentstvo.media/feed",
    "https://www.currenttime.tv/rss",
    "https://www.bbc.com/russian/index.xml",
    "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "https://www.interfax.ru/rss.asp",
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
CACHE_TTL = 300          # секунд (5 мин)
_cache = {"ts": 0, "entries": []}


def _clean(txt: str) -> str:
    return HTML_TAG_RE.sub("", txt or "").strip()


def _fetch_one(url: str, timeout=4):
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
        return feedparser.parse(io.BytesIO(resp.content))
    except Exception as e:
        print("FEED_FAIL:", url, e)
        return feedparser.parse("")


def _refresh_cache():
    today = datetime.now(timezone.utc).date()
    entries = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, url): url for url in FEEDS}
        for fut in as_completed(futures):
            d = fut.result()
            for e in d.entries:
                pub = e.get("published_parsed") or e.get("updated_parsed")
                if not pub or datetime(*pub[:6], tzinfo=timezone.utc).date() != today:
                    continue
                content = ""
                if e.get("content"):
                    content = e["content"][0].get("value", "")
                elif e.get("summary"):
                    content = e["summary"]

                entries.append(
                    {
                        "title": _clean(e.get("title")),
                        "content": _clean(content),
                        "link": e.get("link", ""),
                    }
                )

    _cache["ts"] = time.time()
    _cache["entries"] = entries
    print(f"CACHE_REFRESH: {len(entries)} news")


def _ensure_cache():
    if time.time() - _cache["ts"] > CACHE_TTL or not _cache["entries"]:
        _refresh_cache()


def get_random_news_today() -> dict:
    try:
        _ensure_cache()
        if not _cache["entries"]:
            return {
                "title": "На сегодня свежих новостей пока нет.",
                "content": "",
                "link": "",
            }
        return random.choice(_cache["entries"])
    except Exception as e:
        print("NEWS_FETCH_ERROR:", e)
        return {
            "title": "Сейчас не удалось загрузить новости.",
            "content": "",
            "link": "",
        }
