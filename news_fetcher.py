import feedparser, requests, io, re, random, time, datetime, json
from datetime import datetime as dt, timezone, date

# ——— RSS ИСТОЧНИКИ ТОЛЬКО ДЛЯ «СЕГОДНЯ» ———
RSS_TODAY = [
    "https://agents.media/rss",        # Агентство
    "https://verstka.media/feed",      # Вёрстка
    "https://www.interfax.ru/rss.asp", # Интерфакс
]

HTML_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"https?://[^\s)\"'>]+")

CACHE_TTL = 300          # 5 минут
_cache: dict[str, dict] = {}   # key="YYYY-MM-DD" → {"ts":…, "entries":…}

# ——— УТИЛИТЫ ————————————————————————————————————
def _clean(txt: str) -> str:
    return HTML_RE.sub("", txt or "").strip()

def _iso(d: date) -> str:
    return d.isoformat()
# ——————————————————————————————————————————————


# ——— ЧТЕНИЕ RSS (СЕГОДНЯ) ————————————————
def _load_rss_today() -> list[dict]:
    today = dt.utcnow().date()
    entries = []
    for url in RSS_TODAY:
        try:
            r = requests.get(url, timeout=2, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            feed = feedparser.parse(io.BytesIO(r.content))
        except Exception as e:
            print("RSS_FAIL:", url, e)
            continue

        for e in feed.entries:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            if not pub or dt(*pub[:6], tzinfo=timezone.utc).date() != today:
                continue

            content = (e.get("content", [{}])[0].get("value") or e.get("summary", ""))

            entries.append({
                "title":   _clean(e.get("title")),
                "content": _clean(content),
                "link":    e.get("link", ""),
                "extra":   (m := HREF_RE.search(content)) and m.group(0) or ""
            })
    return entries
# ——————————————————————————————————————————————


# ——— ЧТЕНИЕ MEDUZA API (ЛЮБАЯ ДАТА ≠ СЕГОДНЯ) ——  
MEDUZA_SEARCH = "https://meduza.io/api/v3/search"
MEDUZA_DOC    = "https://meduza.io/api/v3/{}"   # slug

def _load_meduza(d: date) -> list[dict]:
    """Берём 100 публикаций, фильтруем вручную по UTC+3."""
    try:
        res = requests.get(MEDUZA_SEARCH, params={
            "chrono": "news",
            "from":   d.isoformat(),
            "to":     (d + datetime.timedelta(days=1)).isoformat(),
            "limit":  100
        }, timeout=4)
        res.raise_for_status()
        docs = res.json()["documents"]
    except Exception as e:
        print("MEDUZA_SEARCH_FAIL:", e)
        return []

    entries = []
    for doc in docs:
        ts = doc.get("published_at", 0) / 1000  # миллисекунды
        local_day = dt.fromtimestamp(ts, tz=timezone.utc).astimezone(
                    datetime.timezone(datetime.timedelta(hours=3))).date()
        if local_day != d:
            continue

        slug = doc["id"]
        # вытаскиваем полный текст
        try:
            art = requests.get(MEDUZA_DOC.format(slug), timeout=4).json()
            body = art["root"]["content"]["body"]
            text = " ".join(p["text"] for p in body if p.get("text"))
        except Exception:
            text = doc.get("description", "")

        entries.append({
            "title":   _clean(doc.get("title")),
            "content": _clean(text),
            "link":    f"https://meduza.io/{slug}",
            "extra":   (m := HREF_RE.search(text)) and m.group(0) or ""
        })
    return entries
# ——————————————————————————————————————————————


# ——— КЭШ/ОБЁРТКИ ——————————
def _ensure(d: date):
    key = _iso(d)
    rec = _cache.get(key)
    if rec and time.time() - rec["ts"] < CACHE_TTL:
        return
    entries = _load_rss_today() if d == dt.utcnow().date() else _load_meduza(d)
    _cache[key] = {"ts": time.time(), "entries": entries}
    print(f"CACHE {key}: {len(entries)} news")

def get_random_news(d: date) -> dict:
    _ensure(d)
    e = _cache[_iso(d)]["entries"]
    if not e:
        return {"title": "", "content": "", "link": "", "extra": ""}
    return random.choice(e)
