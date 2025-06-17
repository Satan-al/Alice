import feedparser, requests, io, re, random, time, json
from datetime import datetime, timezone, date

# ――― RSS-источники только для «сегодня»
RSS_TODAY = [
    "https://agents.media/rss",              # Агентство
    "https://verstka.media/feed",            # Вёрстка
    "https://www.interfax.ru/rss.asp",       # Интерфакс
]

HTML_RE = re.compile(r"<[^>]+>")
HREF_RE = re.compile(r"https?://[^\s)\"'>]+")

CACHE_TTL = 300        # 5 минут
_cache: dict[str, dict] = {}   # key="YYYY-MM-DD" → {"ts":…, "entries":…}

# ─── утилиты ───────────────────────────────────────────────
def _clean(txt: str) -> str:
    return HTML_RE.sub("", txt or "").strip()

def _today_iso() -> str:
    return datetime.utcnow().date().isoformat()
# ───────────────────────────────────────────────────────────


# ─── загрузка RSS (для сегодняшнего дня) ───────────────────
def _load_rss_today() -> list[dict]:
    today = datetime.utcnow().date()
    entries = []
    for url in RSS_TODAY:
        try:
            r = requests.get(url, timeout=2,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            feed = feedparser.parse(io.BytesIO(r.content))
        except Exception as e:
            print("RSS_FAIL:", url, e)
            continue

        for e in feed.entries:
            pub = e.get("published_parsed") or e.get("updated_parsed")
            if not pub or datetime(*pub[:6], tzinfo=timezone.utc).date() != today:
                continue
            content = ""
            if e.get("content"):
                content = e["content"][0].get("value", "")
            elif e.get("summary"):
                content = e["summary"]

            entries.append({
                "title": _clean(e.get("title")),
                "content": _clean(content),
                "link": e.get("link", ""),
                "extra": HREF_RE.search(content).group(0)
                         if HREF_RE.search(content) else ""
            })
    return entries
# ───────────────────────────────────────────────────────────


# ─── Meduza API для любой даты ≠ сегодня ───────────────────
MEDUZA_SEARCH = "https://meduza.io/api/v3/search"
MEDUZA_DOC    = "https://meduza.io/api/v3/{}"     # slug

def _load_meduza(d: date) -> list[dict]:
    try:
        res = requests.get(MEDUZA_SEARCH, params={
            "chrono": "news",
            "from"  : d.isoformat(),
            "to"    : d.isoformat(),
            "limit" : 100
        }, timeout=4)
        res.raise_for_status()
        docs = res.json().get("documents", [])
    except Exception as e:
        print("MEDUZA_SEARCH_FAIL:", e)
        return []

    entries = []
    for doc in docs:
        slug = doc["id"]
        try:
            art = requests.get(MEDUZA_DOC.format(slug), timeout=4).json()
            body = art["root"]["content"]["body"]
            text = " ".join([p["text"] for p in body])
        except Exception as e:
            print("MEDUZA_DOC_FAIL:", slug, e)
            text = doc.get("description", "")
        entries.append({
            "title": _clean(doc.get("title")),
            "content": _clean(text),
            "link": f"https://meduza.io/{slug}",
            "extra": HREF_RE.search(text).group(0)
                     if HREF_RE.search(text) else ""
        })
    return entries
# ───────────────────────────────────────────────────────────


# ─── публичная точка входа ─────────────────────────────────
def _ensure(date_: date):
    key = date_.isoformat()
    rec = _cache.get(key)
    if rec and time.time() - rec["ts"] < CACHE_TTL:
        return
    if date_ == datetime.utcnow().date():
        entries = _load_rss_today()
    else:
        entries = _load_meduza(date_)
    _cache[key] = {"ts": time.time(), "entries": entries}
    print(f"CACHE {key}: {len(entries)} news")

def get_random_news(date_: date) -> dict:
    _ensure(date_)
    entries = _cache[date_.isoformat()]["entries"]
    if not entries:
        return {"title": f"За {date_.strftime('%d %B %Y')} новостей нет.",
                "content": "", "link": "", "extra": ""}
    return random.choice(entries)
