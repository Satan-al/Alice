from news_fetcher import get_random_news_today

news = get_random_news_today()
title = news["title"]
content = news["content"]
