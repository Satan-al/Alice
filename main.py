
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    req = request.get_json()

    response_text = "Привет! Это навык 'Обычные новости'. В скором времени я буду рассказывать тебе свежие заголовки, а пока — протест связи прошёл успешно."

    return jsonify({
        "response": {
            "text": response_text,
            "end_session": False
        },
        "version": req.get("version", "1.0")
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
