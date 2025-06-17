from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    req = request.get_json()

    is_new_session = req["session"]["new"]
    user_utterance = req["request"]["original_utterance"]

    # Приветствие, если новая сессия
    if is_new_session:
        response_text = (
            "Привет! Это навык 'Обычные новости'. "
            "Скажи, за какой день тебе интересны новости — например, 'за сегодня', 'вчера' или конкретную дату."
        )
    else:
        # Пока на любую фразу возвращаем одно и то же (заглушка)
        response_text = (
            "Скоро я начну зачитывать тебе свежие заголовки. Пока можешь попробовать сказать: 'новости за вчера'."
        )

    return jsonify({
        "response": {
            "text": response_text,
            "end_session": False
        },
        "version": req.get("version", "1.0")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
