from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify
from news_fetcher import get_random_news

app = Flask(__name__)
MAX_LEN = 950
session_state: dict[str, dict] = {}

# ——— Пропись дат
NUM_WORDS = {
    1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого", 5: "пятого",
    6: "шестого", 7: "седьмого", 8: "восьмого", 9: "девятого", 10: "десятого",
    11: "одиннадцатого", 12: "двенадцатого", 13: "тринадцатого", 14: "четырнадцатого",
    15: "пятнадцатого", 16: "шестнадцатого", 17: "семнадцатого", 18: "восемнадцатого",
    19: "девятнадцатого", 20: "двадцатого", 21: "двадцать первого", 22: "двадцать второго",
    23: "двадцать третьего", 24: "двадцать четвёртого", 25: "двадцать пятого",
    26: "двадцать шестого", 27: "двадцать седьмого", 28: "двадцать восьмого",
    29: "двадцать девятого", 30: "тридцатого", 31: "тридцать первого"
}
MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}
YEARS = {
    2020: "две тысячи двадцатого", 2021: "две тысячи двадцать первого",
    2022: "две тысячи двадцать второго", 2023: "две тысячи двадцать третьего",
    2024: "две тысячи двадцать четвёртого", 2025: "две тысячи двадцать пятого"
}
def human_date(d: date) -> str:
    return f"{NUM_WORDS[d.day]} {MONTHS[d.month]} {YEARS.get(d.year, str(d.year))} года"


# ——— Вспомогательные
def ok(text: str):
    return jsonify({"response": {"text": text, "end_session": False}, "version": "1.0"})

def chunk(txt: str):
    if len(txt) <= MAX_LEN:
        return txt.strip(), ""
    cut = txt[:MAX_LEN]
    end = cut.rfind(".")
    if end == -1: end = cut.rfind(" ")
    return cut[:end+1].strip(), txt[end+1:].lstrip()

def parse_date(req) -> tuple[bool, date]:
    ent = req["request"]["nlu"].get("entities", [])
    today = datetime.utcnow().date()
    for e in ent:
        if e["type"] != "YANDEX.DATETIME": continue
        v = e["value"]
        if v.get("day_is_relative"):
            d = today + timedelta(days=int(v["day"]))
            return d > today, d
        d, m, y = v.get("day"), v.get("month"), v.get("year")
        if d and m:
            if y is None:
                d_ = date(today.year, m, d)
                if d_ > today:
                    d_ = date(today.year - 1, m, d)
            else:
                d_ = date(y, m, d)
            return d_ > today, d_
    return False, today


# ——— Методы
@app.route("/", methods=["GET"])
def ping():
    return "ok", 200

@app.route("/", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        sid = req["session"]["session_id"]
        utt = req["request"]["original_utterance"].lower().strip()
        is_new = req["session"]["new"]

        if is_new:
            session_state[sid] = {"stage": "await"}
            return ok("Привет! Назови дату — сегодня, вчера, или например шестнадцатое мая.")

        state = session_state.get(sid, {"stage": "await"})
        stage = state["stage"]

        if stage == "await":
            future, dt_req = parse_date(req)
            if future:
                return ok("Мы честные: будущие новости не рассказываем. Это же не выборы в России.")
            news = get_random_news(dt_req)
            if not news["title"]:
                return ok(f"За {human_date(dt_req)} у меня нет публикаций.")
            session_state[sid] = {"stage": "detail", "news": news, "date": dt_req}
            return ok(f"{news['title'].rstrip('.')}. Хотите узнать подробнее?")

        if stage == "detail":
            if "да" in utt:
                news = state["news"]
                head, tail = chunk(news["content"])
                if tail:
                    session_state[sid] = {"stage": "cont", "remain": tail, "extra": news["extra"], "date": state["date"]}
                    return ok(f"{head} Продолжить?")
                if news["extra"]:
                    session_state[sid] = {"stage": "extra", "extra": news["extra"], "date": state["date"]}
                    return ok(f"{head} Хотите узнать и об этом?")
                session_state[sid]["stage"] = "more"
                return ok(f"{head} Хотите ещё новость?")
            if "нет" in utt:
                new = get_random_news(state["date"])
                session_state[sid] = {"stage": "detail", "news": new, "date": state["date"]}
                return ok(f"Тогда вот ещё: {new['title'].rstrip('.')}. Хотите узнать подробнее?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        if stage == "cont":
            if "да" in utt:
                head, tail = chunk(state["remain"])
                if tail:
                    session_state[sid]["remain"] = tail
                    return ok(f"{head} Продолжить?")
                if state.get("extra"):
                    session_state[sid] = {"stage": "extra", "extra": state["extra"], "date": state["date"]}
                    return ok(f"{head} Хотите узнать и об этом?")
                session_state[sid]["stage"] = "more"
                return ok(f"{head} Хотите ещё новость?")
            if "нет" in utt:
                session_state[sid]["stage"] = "more"
                return ok("Окей. Хотите следующую новость?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        if stage == "extra":
            if "да" in utt:
                extra = get_random_news(datetime.utcnow().date())
                head, _ = chunk(extra["content"])
                session_state[sid]["stage"] = "more"
                return ok(f"{extra['title'].rstrip('.')}. {head} Хотите ещё новость?")
            if "нет" in utt:
                session_state[sid]["stage"] = "more"
                return ok("Окей. Хотите следующую новость?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        if stage == "more":
            if "да" in utt:
                new = get_random_news(state["date"])
                session_state[sid] = {"stage": "detail", "news": new, "date": state["date"]}
                return ok(f"{new['title'].rstrip('.')}. Хотите узнать подробнее?")
            if "нет" in utt:
                session_state[sid]["stage"] = "await"
                return ok("Хорошо. Скажи дату, если захочешь ещё.")
            return ok("Скажи «да» или «нет», пожалуйста.")

        return ok("Не понял. Попробуй ещё раз.")
    except Exception as e:
        print("ERR:", e)
        return ok("Что-то пошло не так. Попробуйте позже.")
