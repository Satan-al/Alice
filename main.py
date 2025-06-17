from news_fetcher import get_random_news_today
from flask import Flask, request, jsonify

news = get_random_news_today()
title = news["title"]
content = news["content"]



app = Flask(__name__)

# Просто в памяти, для демонстрации (не для продакшна)
session_state = {}

@app.route("/", methods=["POST"])
def webhook():
    req = request.get_json()
    session_id = req['session']['session_id']
    is_new_session = req['session']['new']
    user_utterance = req['request']['original_utterance'].lower()

    if is_new_session:
        # Приветствие
        response_text = (
            "Привет! Это навык «Обычные новости». Скажи, за какой день тебе интересны новости — например, «сегодня», «вчера» или назови конкретную дату. "
            "Пока я понимаю только «сегодня». Хочешь узнать новости за сегодня?"
        )
        session_state[session_id] = {
            "last_news": None,
            "stage": "awaiting_confirmation"
        }
    else:
        state = session_state.get(session_id, {"stage": None})

        if state["stage"] == "awaiting_confirmation":
            if "да" in user_utterance:
                news = get_random_news_today()
                session_state[session_id] = {
                    "last_news": news,
                    "stage": "read_more"
                }
                response_text = f"{news['title']} Вы хотите узнать подробнее?"
            else:
                # отказ, подставляем новую новость
                news = get_random_news_today()
                session_state[session_id] = {
                    "last_news": news,
                    "stage": "read_more"
                }
                response_text = f"Хорошо, тогда вот другая новость. {news['title']} Хотите узнать подробнее?"
        elif state["stage"] == "read_more":
            if "да" in user_utterance and state.get("last_news"):
                news = state["last_news"]
                response_text = f"{news['content']} Хотите узнать ещё одну новость за сегодня?"
                session_state[session_id]["stage"] = "awaiting_confirmation"
            elif "нет" in user_utterance:
                news = get_random_news_today()
                session_state[session_id] = {
                    "last_news": news,
                    "stage": "read_more"
                }
                response_text = f"Тогда вот ещё одна. {news['title']} Хотите узнать подробнее?"
            else:
                response_text = "Прости, я не понял. Скажи «да» или «нет»."
        else:
            response_text = "Привет! Скажи «сегодня», чтобы узнать свежие новости."

    return jsonify({
        "response": {
            "text": response_text,
            "end_session": False
        },
        "version": req.get("version", "1.0")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
