# news_fetcher.py
from __future__ import annotations
import os, io, re, time, random, asyncio
from datetime import datetime, timedelta, date, timezone as tz
import requests, feedparser, pytz
from pyrogram import Client

try:  # for IDE linting
    from pyrogram.session.string_session import StringSession
except ImportError:
    from typing import Any as StringSession  # type: ignore

# ── Telegram creds ─────────────────────────────────────────
API_ID   = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SESSION_STR = os.getenv("TG_SESSION")
if not (API_ID and API_HASH and SESSION_STR):
    raise RuntimeError("TG_API_ID, TG_API_HASH, TG_SESSION must be set in env")

CHANNEL  = "astrapress"

# ── RSS источники (сегодня) ───────────────────────────────
RSS_TODAY = [
    "https://agents.media/rss",
    "https://verstka.media/feed",
    "https://www.interfax.ru/rss.asp",
]

HTML_RE  = re.compile(r"<[^>]+>")
ASTRA_RE = re.compile(r"\bastra\b", re.I)
BOLD, ITAL = "bold", "italic"
tz_msk = pytz.timezone("Europe/Moscow")

CACHE_TTL = 300  # секунд
_cache: dict[str, dict] = {}   # key → {"ts":…, "entries":[…]}

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

def _clean_ads(txt: str, ents):
    if not ents: return txt
    chars = list(txt)
    for e in ents[::-1]:
        if getattr(e, "type", "") == ITAL and ASTRA_RE.search(txt[e.offset:e.offset+e.length]):
            for i in range(e.offset, e.offset+e.length):
                chars[i] = ""
    return "".join(chars).strip()

def _cache_get(k): return (c := _cache.get(k)) and (time.time()-c["ts"]<CACHE_TTL) and c["entries"]
def _cache_set(k,v): _cache[k]={"ts":time.time(),"entries":v}

# ── RSS (сегодня) ─────────────────────────────────────────
def _load_rss_today() -> list[dict]:
    today=datetime.utcnow().date(); out=[]
    for url in RSS_TODAY:
        try:
            r=requests.get(url, timeout=4, headers={"User-Agent":"Mozilla/5.0"})
            r.raise_for_status()
            feed=feedparser.parse(io.BytesIO(r.content))
        except Exception as e:
            print("RSS_FAIL:",url,e); continue
        for ent in feed.entries:
            pub=ent.get("published_parsed") or ent.get("updated_parsed")
            if not pub or datetime(*pub[:6],tzinfo=tz.utc).date()!=today: continue
            content=(ent.get("content",[{}])[0].get("value") or ent.get("summary",""))
            out.append({
                "title":_clean(ent.get("title")),
                "body": _clean(content),
                "kind": "K" if not content else "F"
            })
    return out

# ── Astra helpers (общий Client) ──────────────────────────
def _client():
    return Client(StringSession(SESSION_STR),
                  api_id=API_ID, api_hash=API_HASH,
                  workdir="/tmp")

# ── Astra by date ─────────────────────────────────────────
async def _astra_day_async(d: date)->list[dict]:
    items=[]; start=tz_msk.localize(datetime.combine(d,datetime.min.time()))
    end  =tz_msk.localize(datetime.combine(d,datetime.max.time()))
    last=0
    async with _client() as app:
        await app.join_chat(CHANNEL)
        while True:
            batch=[m async for m in app.get_chat_history(CHANNEL,offset_id=last,limit=100)]
            if not batch: break
            for m in batch:
                last=m.id
                dtm=m.date.replace(tzinfo=pytz.UTC).astimezone(tz_msk)
                if dtm<start: break
                if not (start<=dtm<=end): continue
                raw=(m.text or m.caption or "").strip()
                if not raw: continue
                raw=_clean_ads(raw,m.entities)
                title,body=_split_title_body(raw,m.entities)
                if ASTRA_RE.search(title): continue
                items.append({"title":title,"body":body,"kind":"K" if not body else "F"})
            else: continue
            break
    return items

def _astra_day(d:date): return asyncio.run(_astra_day_async(d))

# ── Astra by keyword ──────────────────────────────────────
async def _astra_kw_async(word:str,days:int=3)->list[dict]:
    hits=[]; last=0; wre=re.compile(rf"\b{re.escape(word)}\b",re.I)
    limit=datetime.now(tz_msk)-timedelta(days=days)
    async with _client() as app:
        await app.join_chat(CHANNEL)
        while True:
            batch=[m async for m in app.get_chat_history(CHANNEL,offset_id=last,limit=100)]
            if not batch: break
            for m in batch:
                last=m.id
                dtm=m.date.replace(tzinfo=pytz.UTC).astimezone(tz_msk)
                if dtm<limit: return hits
                raw=(m.text or m.caption or "")
                if not wre.search(raw): continue
                raw=_clean_ads(raw,m.entities)
                title,body=_split_title_body(raw,m.entities)
                if ASTRA_RE.search(title): continue
                hits.append({"title":title,"body":body,"kind":"K" if not body else "F"})
                if len(hits)>=40: return hits
            else: continue
            break
    return hits

def _astra_kw(w:str): return asyncio.run(_astra_kw_async(w))

# ── публичные обёртки ─────────────────────────────────────
def today_news():
    if (p:=_cache_get("TODAY")) is None:
        p=_load_rss_today(); _cache_set("TODAY",p)
    return random.choice(p) if p else None

def news_by_date(d:date):
    key=f"D:{d}"
    if (p:=_cache_get(key)) is None:
        p=_astra_day(d); _cache_set(key,p)
    return random.choice(p) if p else None

def news_by_keyword(w:str):
    k=f"K:{w.lower()}"
    if (p:=_cache_get(k)) is None:
        p=_astra_kw(w); _cache_set(k,p)
    return random.choice(p) if p else None
