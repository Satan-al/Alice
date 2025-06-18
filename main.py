from datetime import datetime, timedelta, date
import re
import random               # ← добавь эту строку
from flask import Flask, request, jsonify
from news_fetcher import today_news, news_by_date, news_by_keyword
if os.getenv("CHECK_ENV", "false").lower() == "true":
    import check_env
    check_env.check_env()

app = Flask(__name__)
MAX_LEN = 950
state: dict[str, dict] = {}

# ───── пропись дат ─────────────────────────────────────────
NUM = {1:"первого",2:"второго",3:"третьего",4:"четвёртого",5:"пятого",
       6:"шестого",7:"седьмого",8:"восьмого",9:"девятого",10:"десятого",
       11:"одиннадцатого",12:"двенадцатого",13:"тринадцатого",14:"четырнадцатого",
       15:"пятнадцатого",16:"шестнадцатого",17:"семнадцатого",18:"восемнадцатого",
       19:"девятнадцатого",20:"двадцатого",21:"двадцать первого",22:"двадцать второго",
       23:"двадцать третьего",24:"двадцать четвёртого",25:"двадцать пятого",
       26:"двадцать шестого",27:"двадцать седьмого",28:"двадцать восьмого",
       29:"двадцать девятого",30:"тридцатого",31:"тридцать первого"}
MON = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",
       7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}
YR  = {2024:"две тысячи двадцать четвёртого",
       2025:"две тысячи двадцать пятого"}
def human(d: date)->str: return f"{NUM[d.day]} {MON[d.month]} {YR.get(d.year,str(d.year))} года"
# ───────────────────────────────────────────────────────────

def ok(text:str): 
    return jsonify({"response":{"text":text,"end_session":False},"version":"1.0"})

def chunk(t:str):
    if len(t)<=MAX_LEN: return t.strip(),""
    cut=t[:MAX_LEN]; end=cut.rfind("."); 
    end=end if end!=-1 else cut.rfind(" ")
    return cut[:end+1].strip(), t[end+1:].lstrip()

# ───── разбор даты ─────────────────────────────────────────
def parse_date(req)->tuple[bool,date|None]:
    ent=req["request"]["nlu"].get("entities",[])
    today=datetime.utcnow().date()
    for e in ent:
        if e["type"]!="YANDEX.DATETIME": continue
        v=e["value"]
        if v.get("day_is_relative"):
            d= today+timedelta(days=int(v["day"]))
            return d>today,d
        d,m,y=v.get("day"),v.get("month"),v.get("year")
        if d and m:
            if y is None:
                d_=date(today.year,m,d)
                if d_>today: d_=date(today.year-1,m,d)
            else: d_=date(y,m,d)
            return d_>today,d_
    return False,None
# ───── ключевое слово (первое без цифр) ────────────────────
def extract_kw(utt:str)->str|None:
    for w in re.findall(r"[а-яёa-zA-Z\-]+",utt.lower()):
        if not any(ch.isdigit() for ch in w):
            return w
    return None
# ───────────────────────────────────────────────────────────

@app.route("/",methods=["GET"])
def ping(): return "ok",200

@app.route("/",methods=["POST"])
def webhook():
    try:
        req=request.get_json(force=True)
        sid=req["session"]["session_id"]
        utt=req["request"]["original_utterance"].lower()
        if req["session"]["new"]:
            state[sid]={"stage":"await"}
            return ok("Привет! Назови дату или слово — я зачитаю одну новость.")
        
        st=state.get(sid,{"stage":"await"})
        if st["stage"]=="await":
            future,dt=parse_date(req)
            kw=extract_kw(utt)
            today=datetime.utcnow().date()

            # ―― выбираем источник
            if kw and not dt:
                post=news_by_keyword(kw)
                if not post: return ok(f"Свежих новостей со словом «{kw}» нет.")
            elif dt:
                if future: return ok("Будущие новости мы не предсказываем 😉")
                if kw:
                    pool=[]
                    daily=news_by_date(dt)
                    if daily and kw.lower() in (daily["title"]+daily["body"]).lower():
                        pool=[daily]
                    if not pool:
                        return ok(f"За {human(dt)} новостей со словом «{kw}» нет.")
                    post=random.choice(pool)
                else:
                    post=news_by_date(dt) if dt!=today else today_news()
                    if not post: return ok(f"За {human(dt)} у меня нет публикаций.")
            else:
                post=today_news()
                if not post: return ok("За сегодня новостей пока нет.")

            state[sid]={"stage":"detail","post":post}
            if post["kind"]=="K":
                state[sid]["stage"]="more"
                return ok(f"{post['title']} Хотите ещё новость?")
            return ok(f"{post['title']} Хотите узнать подробнее?")

        if st["stage"]=="detail":
            if "да" in utt:
                head,tail=chunk(st["post"]["body"])
                if tail:
                    state[sid]={"stage":"cont","remain":tail}
                    return ok(f"{head} Продолжить?")
                state[sid]={"stage":"more"}
                return ok(f"{head} Хотите ещё новость?")
            if "нет" in utt:
                state[sid]={"stage":"more"}
                return ok("Окей. Хотите следующую новость?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        if st["stage"]=="cont":
            if "да" in utt:
                head,tail=chunk(st["remain"])
                if tail:
                    st["remain"]=tail
                    return ok(f"{head} Продолжить?")
                state[sid]={"stage":"more"}
                return ok(f"{head} Хотите ещё новость?")
            if "нет" in utt:
                state[sid]={"stage":"more"}
                return ok("Окей. Хотите следующую новость?")
            return ok("Скажи «да» или «нет», пожалуйста.")

        if st["stage"]=="more":
            if "да" in utt:
                state[sid]={"stage":"await"}  # запрашиваем новое слово/дату
                return ok("Назови дату или слово.")
            if "нет" in utt:
                state[sid]={"stage":"await"}
                return ok("Хорошо. Если захочешь ещё — просто скажи.")
            return ok("Скажи «да» или «нет», пожалуйста.")
        
        return ok("Не понял. Попробуй ещё раз.")
    except Exception as e:
        print("ERR:",e)
        return ok("Что-то сломалось. Попробуйте позже.")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000,debug=True)
