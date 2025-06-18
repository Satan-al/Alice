# news_fetcher.py
"""
Источники:
    • сегодня  – RSS (Агентство, Вёрстка, Интерфакс)
    • дата     – AstraPress посты за день
    • keyword  – AstraPress посты, содержащие слово (за 3 суток)

Публичные вызовы:
    today_news()                     -> dict | None
    news_by_date(datetime.date)      -> dict | None
    news_by_keyword(str)             -> dict | None
Каждый dict: {"title", "body", "kind"}  kind=="K" → текста нет
"""

from __future__ import annotations
import os, io, re, time, random, asyncio
from datetime import datetime, timedelta, date, timezone as tz
import requests, feedparser, pytz

# ── Telegram creds (env) ───────────────────────────────────
API_ID   = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_STR = os.getenv("TG_SESSION")
CHANNEL = "astrapress"

if not (API_ID and API_HASH and SESSION_STR):
    raise RuntimeError("TG_API_ID, TG_API_HASH или TG_SESSION не заданы")

# ── RSS источники (для «сегодня») ──────────────────────────
RSS_TODAY = [
    "https://agents.media/rss",
    "https://verstka.media/feed",
    "https://www.interfax.ru/rss.asp",
]

HTML_RE  = re.compile(r"<[^>]+>")
ASTRA_RE = re.compile(r"\bastra\b", re.I)
BOLD, ITAL = "bold", "italic"
tz_msk = pytz.timezone("Europe/Moscow")

CACHE_TTL = 300          # секунд
_cache: dict[str, dict] = {}   # key → {"ts":unix, "entries":[…]}


# ── helpers ────────────────────────────────────────────────
def _clean(html: str | None) -> str:
    return HTML_RE.sub("", html or "").strip()

def _split_title_body(text: str, entities):
    if entities:
        for e in entities:
            if getattr(e, "type", "") == BOLD:
                s, epos = e.offset, e.offset + e.length
                return text[s:epos].strip().rstrip(".") + ".", text[epos:].strip()
    first = text.splitlines()[0]
    dot   = first.find(".")
    if dot != -1:
        return first[:dot+1].strip(), text[dot+1:].strip()
    return first.strip(), text[len(first):].strip()

def _clean_ads(text: str, entities):
    if not entities:
        return text
    chars = list(text)
    for e in entities[::-1]:
        if getattr(e, "type", "") == ITAL and ASTRA_RE.search(text[e.offset:e.offset+e.length]):
            for i in range(e.offset, e.offset+e.length):
                chars[i] = ""
    return "".join(chars).strip()

def _cache_get(key: str):
    rec = _cache.get(key)
    if rec and time.time() - rec["ts"] < CACHE_TTL:
        return rec["entries"]
    return None

def _cache_set(key: str, entries: list[dict]):
    _cache[key] = {"ts": time.time(), "entries": entries}

def _get_client():
    try:
        from pyrogram import Client
        from pyrogram.session.string_session import StringSession
    except ImportError:
        raise RuntimeError("pyrogram не установлен")

    return Client(
        session_name=None,
        session=StringSession(SESSION_STR),
        api_id=API_ID,
        api_hash=API_HASH,
        workdir="/tmp"
    )

# ── RSS (today) ────────────────────────────────────────────
def _load_rss_today() -> list[dict]:
    today = datetime.utcnow().date()
    out   = []
    for url in RSS_TODAY:
        try:
            r = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            feed = feedparser.parse(io.BytesIO(r.content))
        except Exception as e:
            print("RSS_FAIL:", url, e)
            continue

        for ent in feed.entries:
            pub = ent.get("published_parsed") or ent.get("updated_parsed")
            if not pub or datetime(*pub[:6], tzinfo=tz.utc).date() != today:
                continue
            content = (ent.get("content", [{}])[0].get("value") or ent.get("summary", ""))
            out.append({
                "title": _clean(ent.get("title")),
                "body":  _clean(content),
                "kind":  "K" if not content else "F"
            })
    return out


# ── Astra (date) ───────────────────────────────────────────
async def _astra_day_async(d: date) -> list[dict]:
    from pyrogram.errors import FloodWait
    items: list[dict] = []
    start = tz_msk.localize(datetime.combine(d, datetime.min.time()))
    end   = tz_msk.localize(datetime.combine(d, datetime.max.time()))
    last  = 0

    async with _get_client() as app:
        await app.join_chat(CHANNEL)
        while True:
            try:
                batch = [m async for m in app.get_chat_history(CHANNEL,
                                                               offset_id=last,
                                                               limit=100)]
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                continue

            if not batch: break
            for m in batch:
                last = m.id
                msg_dt = m.date.replace(tzinfo=pytz.UTC).astimezone(tz_msk)
                if msg_dt < start: break
                if not (start <= msg_dt <= end): continue
                raw = (m.text or m.caption or "").strip()
                if not raw: continue
                raw = _clean_ads(raw, m.entities)
                title, body = _split_title_body(raw, m.entities)
                if ASTRA_RE.search(title): continue
                items.append({"title": title, "body": body, "kind": "K" if not body else "F"})
            else:
                continue
            break
    return items

def _astra_day(d: date) -> list[dict]:
    return asyncio.run(_astra_day_async(d))


# ── Astra (keyword, N days) ────────────────────────────────
async def _astra_kw_async(word: str, days: int = 3) -> list[dict]:
    from pyrogram.errors import FloodWait
    hits, last = [], 0
    word_re = re.compile(rf"\b{re.escape(word)}\b", re.I)
    limit_date = datetime.now(tz_msk) - timedelta(days=days)

    async with _get_client() as app:
        await app.join_chat(CHANNEL)
        while True:
            try:
                batch = [m async for m in app.get_chat_history(CHANNEL,
                                                               offset_id=last,
                                                               limit=100)]
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                continue

            if not batch: break
            for m in batch:
                last = m.id
                msg_dt = m.date.replace(tzinfo=pytz.UTC).astimezone(tz_msk)
                if msg_dt < limit_date: return hits
                raw = (m.text or m.caption or "")
                if not word_re.search(raw): continue
                raw = _clean_ads(raw, m.entities)
                title, body = _split_title_body(raw, m.entities)
                if ASTRA_RE.search(title): continue
                hits.append({"title": title, "body": body, "kind": "K" if not body else "F"})
                if len(hits) >= 40: return hits
            else:
                continue
            break
    return hits

def _astra_kw(word: str) -> list[dict]:
    return asyncio.run(_astra_kw_async(word))


# ── публичные функции ─────────────────────────────────────
def today_news() -> dict | None:
    key = "TODAY"
    pool = _cache_get(key)
    if pool is None:
        pool = _load_rss_today()
        _cache_set(key, pool)
    return random.choice(pool) if pool else None

def news_by_date(d: date) -> dict | None:
    key = f"D:{d.isoformat()}"
    pool = _cache_get(key)
    if pool is None:
        pool = _astra_day(d)
        _cache_set(key, pool)
    return random.choice(pool) if pool else None

def news_by_keyword(word: str) -> dict | None:
    key = f"K:{word.lower()}"
    pool = _cache_get(key)
    if pool is None:
        pool = _astra_kw(word)
        _cache_set(key, pool)
    return random.choice(pool) if pool else None
