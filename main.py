from datetime import datetime, timedelta, date
from flask     import Flask, request, jsonify
from news_fetcher import get_random_news

app      = Flask(__name__)
MAX_LEN  = 950

session_state: dict[str, dict] = {}

# ─── helpers ───────────────────────────────────────────────
def ok(text: str):
    return jsonify({"response": {"text": text, "end_session": False},
                    "version": "1.0"})

def chunk(text: str):
    if len(text) <= MAX_LEN:
        return text.strip(), ""
    cut = text[:MAX_LEN]
    end = cut.rfind(".")
    if end == -1: end = cut.rfind(" ")
    head = cut[:end+1].strip()
    tail = text[end+1:].lstrip()
    return head, tail

def parse_date(req) -> tuple[bool, date]:
    """Возвращает (is_future, дата)."""
    ent = req["request"]["nlu"].get("entities", [])
    today = datetime.utcnow().date()

    for e in ent:
        if e["type"] != "YANDEX.DATETIME":
            continue
        v = e["value"]

        # относительный день
        if v.get("day_is_relative"):
            dt = today + timedelta(days=int(v["day"]))
            return dt > today, dt

        d, m, y = v.get("day"), v.get("month"), v.get("year")
        if d and m:
            if y is None:
                dt = date(today.year, m, d)
                if dt > today:          # «24 сентября» в будущем → прошлый год
                    dt = date(today.year - 1, m, d)
            else:
                dt = date(y, m, d)
            return dt > today, dt

    # ни одной даты → трактуем «сегодня»
    return False, today
# ───────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def ping():
    return "ok", 200

@app.route("/", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        sid = req["session"]["session_id"]
        is_new = req["session"]["new"]
        utt = req["request"]["original_utterance"].lower().strip()

        if is_new:
            session_state[sid] = {"stage": "await_date"}
            return ok("Привет! Скажи «сегодня», «вчера» или дату — "
                      "и я зачитаю новости.")

        state = session_state.get(sid, {"stage": "await_date"})
        stage = state["stage"]

        # ―── пользователь произнёс дату
        if stage == "await_date":
            is_future, dt = parse_date(req)
            if is_future:
                return ok("Мы честные, поэтому заранее новости не знаем. "
                          "Попробуй спросить про вчера или сегодня.")
            news = get_random_news(dt)
            title = news["title"].rstrip(".") + "."
            session_state[sid] = {"stage": "detail",
                                  "news": news,
                                  "date": dt}
            return ok(f"{title} Хотите узнать подробнее?")

        # ―── читаем подробности
        if stage == "detail":
            if "да" in utt:
                news = state["news"]
                head, tail = chunk(news["content"])
                if tail:
                    session_state[sid] = {"stage": "continue",
                                          "remain": tail,
                                          "extra": news["extra"],
                                          "date": state["date"]}
                    return ok(f"{head} Продолжить?")
                # статья короткая
                if news["extra"]:
                    session_state[sid] = {"stage": "extra_offer",
                                          "extra": news["extra"],
                                          "date": state["date"]}
                    return ok(f"{head} Хотите узнать и об этом?")
                session_state[sid]["stage"] = "more"
                return ok(f"{head} Хотите ещё новость?")

            if "нет" in utt:
                news = get_random_news(state["date"])
                title = news["title"].rstrip(".") + "."
                session_state[sid] = {"stage": "detail",
                                      "news": news,
                                      "date": state["date"]}
                return ok(f"Тогда вот ещё: {title} Хотите узнать подробнее?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        # ―── продолжаем длинную статью
        if stage == "continue":
            if "да" in utt:
                head, tail = chunk(state["remain"])
                if tail:
                    session_state[sid]["remain"] = tail
                    return ok(f"{head} Продолжить?")
                if state.get("extra"):
                    session_state[sid] = {"stage": "extra_offer",
                                          "extra": state["extra"],
                                          "date": state["date"]}
                    return ok(f"{head} Хотите узнать и об этом?")
                session_state[sid]["stage"] = "more"
                return ok(f"{head} Хотите ещё новость?")
            if "нет" in utt:
                session_state[sid]["stage"] = "more"
                return ok("Окей. Хотите следующую новость?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        # ―── предлагаем перейти по ссылке
        if stage == "extra_offer":
            if "да" in utt:
                # читаем допматериал как отдельную новость (заглушка)
                news = get_random_news(datetime.utcnow().date())
                head, tail = chunk(news["content"])
                session_state[sid]["stage"] = "more"
                return ok(f"{news['title']}. {head} Хотите ещё новость?")
            if "нет" in utt:
                session_state[sid]["stage"] = "more"
                return ok("Окей. Хотите следующую новость?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        # ―── хотим ещё новость
        if stage == "more":
            if "да" in utt:
                news = get_random_news(state["date"])
                title = news["title"].rstrip(".") + "."
                session_state[sid] = {"stage": "detail",
                                      "news": news,
                                      "date": state["date"]}
                return ok(f"{title} Хотите узнать подробнее?")
            if "нет" in utt:
                session_state[sid]["stage"] = "await_date"
                return ok("Хорошо. Если захочешь ещё — задай дату.")
            return ok("Скажи «да» или «нет», пожалуйста.")

        return ok("Не понял. Попробуй ещё раз.")
    except Exception as e:
        print("ERR:", e)
        return ok("Кажется, что-то сломалось. Попробуйте позже.")
# ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
