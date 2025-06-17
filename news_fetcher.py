import feedparser
from datetime import datetime
import random
import re

FEEDS = [
    "https://meduza.io/rss/all",
    "https://theins.ru/feed",
    "https://data.ovdinfo.org/ru/rss.xml",
    "https://agentstvo.media/feed",
    "https://www.currenttime.tv/rss",
    "https://www.bbc.com/russian/index.xml",
    "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "https://www.interfax.ru/rss.asp"
]

def clean_html(text):
    return re.sub('<[^<]+?>', '', text or '')

def get_today_entries():
    today = datetime.utcnow().date()
    entries = []

    for url in FEEDS:
        d = feedparser.parse(url)
        for entry in d.entries:
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            if not pub:
                continue
            pub_date = datetime(*pub[:6]).date()
            if pub_date != today:
                continue
            content = ""
            if entry.get("content"):
                content = entry["content"][0].get("value", "")
            elif entry.get("summary"):
                content = entry["summary"]

            entries.append({
                "title": clean_html(entry.get("title")),
                "summary": clean_html(entry.get("summary")),
                "content": clean_html(content),
                "link": entry.get("link")
            })

    return entries

def get_random_news_today():
    entries = get_today_entries()
    if not entries:
        return {
            "title": "На сегодня новостей пока нет.",
            "summary": "",
            "content": "",
            "link": ""
        }
    return random.choice(entries)
