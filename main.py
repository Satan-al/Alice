from flask import Flask, request, jsonify
from news_fetcher import get_random_news_today

app = Flask(__name__)

# Простое хранилище состояния в памяти (подойдёт для демо)
session_state: dict[str, dict] = {}

# ─────────────────────────────────────────────────────────────
# Render регулярно пингует GET /.  Отдаём «ok», чтобы считался живым
@app.route("/", methods=["GET"])
def ping():
    return "ok", 200
# ─────────────────────────────────────────────────────────────


@app.route("/", methods=["POST"])
def webhook():
    try:
        req = request.get_json(force=True)
        session_id = req["session"]["session_id"]
        is_new = req["session"]["new"]
        user_text = req["request"]["original_utterance"].lower()

        # Инициализация новой сессии
        if is_new:
            session_state[session_id] = {"stage": "await_today"}
            answer = ("Привет! Это навык «Обычные новости». "
                      "Скажи «сегодня», чтобы услышать свежие новости.")
            return ok(answer)

        # Работа со «старыми» сессиями
        state = session_state.get(session_id, {"stage": "await_today"})
        stage = state["stage"]

        # Пользователь сказал "сегодня" (или близко)
        if "сегодня" in user_text and stage == "await_today":
            news = get_random_news_today()
            session_state[session_id] = {
                "stage": "detail_choice",
                "last_news": news
            }
            answer = f"{news['title']} Хотите узнать подробнее?"
            return ok(answer)

        # Мы ждём «да / нет» после заголовка
        if stage == "detail_choice":
            if "да" in user_text:
                news = state["last_news"]
                answer = (f"{news['content']} "
                          "Хотите ещё одну новость за сегодня?")
                session_state[session_id]["stage"] = "more_choice"
                return ok(answer)

            if "нет" in user_text:
                news = get_random_news_today()
                session_state[session_id] = {
                    "stage": "detail_choice",
                    "last_news": news
                }
                answer = f"Тогда вот ещё: {news['title']} Хотите узнать подробнее?"
                return ok(answer)

            return ok("Скажи «да» или «нет», пожалуйста.")

        # После полного текста спрашиваем, читать ли следующую
        if stage == "more_choice":
            if "да" in user_text:
                news = get_random_news_today()
                session_state[session_id] = {
                    "stage": "detail_choice",
                    "last_news": news
                }
                return ok(f"{news['title']} Хотите узнать подробнее?")

            if "нет" in user_text:
                session_state[session_id]["stage"] = "await_today"
                return ok("Хорошо. Если понадобится ещё — просто скажи «сегодня».")

            return ok("Скажи «да» или «нет», пожалуйста.")

        # Фолбэк
        return ok("Не понял. Скажи «сегодня», чтобы услышать новости.")
    except Exception as e:
        # Любая непойманная ошибка → безопасный ответ
        print("HANDLER_ERROR:", e)
        return ok("Упс, что-то сломалось. Попробуй ещё раз чуть позже.")


# ─────────────────────────────────────────────────────────────
def ok(text: str) -> tuple:
    """Формируем правильный JSON для Алисы."""
    return jsonify({
        "response": {
            "text": text,
            "end_session": False
        },
        "version": "1.0"
    })
# ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    # Локальный запуск для отладки
    app.run(host="0.0.0.0", port=5000, debug=True)
