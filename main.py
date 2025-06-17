from flask import Flask, request, jsonify
from news_fetcher import get_random_news_today

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────
# Константы
MAX_LEN = 950          # запас, чтобы итог < 1024 + « Продолжить?»
# ─────────────────────────────────────────────────────────────

# Память сессий (для демо достаточно)
session_state: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────
# Хелперы
def ok(text: str) -> tuple:
    """Формирует правильный JSON-ответ для Алисы."""
    return jsonify({
        "response": {"text": text, "end_session": False},
        "version": "1.0"
    })


def chunk_text(full: str) -> tuple[str, str]:
    """
    Делит текст так, чтобы первая часть ≤ MAX_LEN и заканчивалась точкой.
    Возвращает (первая_часть, хвост).
    """
    if len(full) <= MAX_LEN:
        return full.strip(), ""

    cut = full[:MAX_LEN]
    last_dot = cut.rfind(".")
    if last_dot == -1:                      # нет точек – ищем последний пробел
        last_dot = cut.rfind(" ")
    head = cut[: last_dot + 1].strip()
    tail = full[last_dot + 1:].lstrip()
    return head, tail
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Пинг для Render (GET /)
@app.route("/", methods=["GET"])
def ping():
    return "ok", 200
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# Основной webhook
@app.route("/", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        session_id = req["session"]["session_id"]
        is_new     = req["session"]["new"]
        user_text  = req["request"]["original_utterance"].lower()

        # ─── новая сессия ────────────────────────────────────
        if is_new:
            session_state[session_id] = {"stage": "await_today"}
            return ok("Привет! Это навык «Обычные новости». "
                      "Скажи «сегодня», чтобы услышать свежие новости.")

        # текущее состояние
        state = session_state.get(session_id, {"stage": "await_today"})
        stage = state["stage"]

        # ─── пользователь сказал «сегодня» ──────────────────
        if "сегодня" in user_text and stage == "await_today":
            news = get_random_news_today()
            session_state[session_id] = {"stage": "detail_choice",
                                         "last_news": news}
            return ok(f"{news['title']} Хотите узнать подробнее?")

        # ─── ждём «да / нет» после заголовка ────────────────
        if stage == "detail_choice":
            if "да" in user_text:
                news = state["last_news"]
                head, tail = chunk_text(news["content"])

                if tail:
                    session_state[session_id] = {"stage": "continue_read",
                                                 "remaining": tail}
                    return ok(f"{head} Продолжить?")
                else:
                    session_state[session_id]["stage"] = "more_choice"
                    return ok(f"{head} Хотите ещё одну новость за сегодня?")

            if "нет" in user_text:
                news = get_random_news_today()
                session_state[session_id] = {"stage": "detail_choice",
                                             "last_news": news}
                return ok(f"Тогда вот ещё: {news['title']} "
                          "Хотите узнать подробнее?")

            return ok("Скажи «да» или «нет», пожалуйста.")

        # ─── продолжаем читать длинный текст ────────────────
        if stage == "continue_read":
            if "да" in user_text and state.get("remaining"):
                head, tail = chunk_text(state["remaining"])
                if tail:
                    session_state[session_id]["remaining"] = tail
                    return ok(f"{head} Продолжить?")
                else:
                    session_state[session_id]["stage"] = "more_choice"
                    return ok(f"{head} Хотите ещё одну новость за сегодня?")

            if "нет" in user_text:
                session_state[session_id]["stage"] = "more_choice"
                return ok("Окей. Хотите следующую новость?")

            return ok("Скажи «да» или «нет», пожалуйста.")

        # ─── после полного текста спрашиваем следующую ──────
        if stage == "more_choice":
            if "да" in user_text:
                news = get_random_news_today()
                session_state[session_id] = {"stage": "detail_choice",
                                             "last_news": news}
                return ok(f"{news['title']} Хотите узнать подробнее?")

            if "нет" in user_text:
                session_state[session_id]["stage"] = "await_today"
                return ok("Хорошо. Если понадобится ещё – скажи «сегодня».")

            return ok("Скажи «да» или «нет», пожалуйста.")

        # ─── fallback ───────────────────────────────────────
        return ok("Не понял. Скажи «сегодня», чтобы услышать новости.")

    except Exception as e:
        # Любая непойманная ошибка – не молчим, а отвечаем безопасно
        print("HANDLER_ERROR:", e)
        return ok("Упс, что-то сломалось. Попробуй ещё раз чуть позже.")
# ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    # локальная отладка
    app.run(host="0.0.0.0", port=5000, debug=True)
