# -*- coding: utf-8 -*-
"""Telegram-бот: контент-план по дням.

Працює на чистому Python 3.9+, нічого встановлювати не треба.
Налаштування беруться зі змінних середовища (див. інструкцію):
  BOT_TOKEN      токен від @BotFather (обов'язково)
  TIMEZONE       часовий пояс, за замовчуванням Europe/Kyiv
  SEND_TIME      година ранкової розсилки, за замовчуванням 08:00
  CHAT_IDS       номери чатів для розсилки, через кому (необов'язково)
  ALLOWED_USERS  номери людей, яким можна користуватися ботом, через кому
                 (порожньо = можуть усі, хто знайшов бота)
План береться з файлу plan.txt: рядок, у якому є лише дата (наприклад 3.11),
починає новий день.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Kyiv").strip())
SEND_TIME = os.environ.get("SEND_TIME", "08:00").strip()
CHAT_IDS = [c.strip() for c in os.environ.get("CHAT_IDS", "").split(",") if c.strip()]
ALLOWED = {c.strip() for c in os.environ.get("ALLOWED_USERS", "").split(",") if c.strip()}
API = "https://api.telegram.org/bot%s/" % TOKEN
PLAN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan.txt")
DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\s*$")


def api(method, **params):
    req = urllib.request.Request(
        API + method,
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=70) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("Помилка Telegram", method, e.code, e.read()[:300])
    except Exception as e:  # мережа тимчасово недоступна тощо
        print("Помилка зв'язку", method, e)
    return None


def load_plan():
    """Повертає {(місяць, день): текст}."""
    with open(PLAN_FILE, encoding="utf-8") as f:
        lines = f.read().splitlines()
    plan, key, buf = {}, None, []
    for line in lines:
        m = DATE_RE.match(line)
        if m:
            if key:
                plan[key] = clean("\n".join(buf))
            key, buf = (int(m.group(2)), int(m.group(1))), []
        elif key:
            buf.append(line)
    if key:
        plan[key] = clean("\n".join(buf))
    return plan


def clean(text):
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def label(key):
    return "%d.%02d" % (key[1], key[0])


def chunks(text, limit=3800):
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def send_text(chat_id, text, markup=None):
    parts = chunks(text) or ["—"]
    for i, part in enumerate(parts):
        params = {"chat_id": chat_id, "text": part, "disable_web_page_preview": True}
        if markup and i == len(parts) - 1:
            params["reply_markup"] = markup
        api("sendMessage", **params)


def btn(text, data):
    return {"text": text, "callback_data": data}


def day_data(key):
    return "d:%d:%d" % key


def days_markup(plan):
    keys = sorted(plan)
    rows = [
        [btn(label(k), day_data(k)) for k in keys[i:i + 4]]
        for i in range(0, len(keys), 4)
    ]
    rows.append([btn("📅 Сьогодні", "t")])
    return {"inline_keyboard": rows}


def nav_markup(plan, key):
    keys = sorted(plan)
    i = keys.index(key)
    row = []
    if i > 0:
        row.append(btn("◀ " + label(keys[i - 1]), day_data(keys[i - 1])))
    if i < len(keys) - 1:
        row.append(btn(label(keys[i + 1]) + " ▶", day_data(keys[i + 1])))
    rows = [row] if row else []
    rows.append([btn("📅 Сьогодні", "t"), btn("🗓 Усі дні", "m")])
    return {"inline_keyboard": rows}


def send_day(chat_id, key):
    plan = load_plan()
    if key not in plan:
        send_text(chat_id, "На цю дату в плані нічого немає. Оберіть день:", days_markup(plan))
        return
    send_text(chat_id, "📅 План на %s\n\n%s" % (label(key), plan[key]), nav_markup(plan, key))


def send_today(chat_id):
    now = datetime.now(TZ)
    key = (now.month, now.day)
    plan = load_plan()
    if key in plan:
        send_day(chat_id, key)
    else:
        send_text(
            chat_id,
            "На сьогодні (%s) у плані нічого немає. Оберіть день:" % label(key),
            days_markup(plan),
        )


def send_menu(chat_id):
    send_text(chat_id, "Оберіть день:", days_markup(load_plan()))


def send_start(chat_id):
    send_text(
        chat_id,
        "Привіт! Це контент-план Лейли по днях.\n\n"
        "📅 Сьогодні — план на сьогоднішню дату\n"
        "🗓 Усі дні — вибрати будь-який день",
        {"inline_keyboard": [[btn("📅 Сьогодні", "t"), btn("🗓 Усі дні", "m")]]},
    )


def allowed(user_id):
    return not ALLOWED or str(user_id) in ALLOWED


def deny(chat_id, user_id):
    send_text(
        chat_id,
        "Немає доступу. Ваш номер: %s\nНадішліть його тому, хто налаштовує бота." % user_id,
    )


def handle(update):
    if "callback_query" in update:
        q = update["callback_query"]
        api("answerCallbackQuery", callback_query_id=q["id"])
        chat_id = q["message"]["chat"]["id"]
        if not allowed(q["from"]["id"]):
            return deny(chat_id, q["from"]["id"])
        data = q.get("data", "")
        if data == "t":
            send_today(chat_id)
        elif data == "m":
            send_menu(chat_id)
        elif data.startswith("d:"):
            _, month, day = data.split(":")
            send_day(chat_id, (int(month), int(day)))
        return

    msg = update.get("message")
    if not msg or "text" not in msg:
        return
    chat_id = msg["chat"]["id"]
    user_id = msg.get("from", {}).get("id")
    words = msg["text"].strip().split()
    if not words:
        return
    cmd = words[0].split("@")[0].lower()

    if cmd == "/id":
        send_text(chat_id, "Номер цього чату: %s\nВаш номер: %s" % (chat_id, user_id))
        return
    if not allowed(user_id):
        return deny(chat_id, user_id)
    if cmd == "/start":
        send_start(chat_id)
    elif cmd == "/today":
        send_today(chat_id)
    elif cmd in ("/days", "/menu"):
        send_menu(chat_id)
    elif cmd.startswith("/"):
        send_start(chat_id)


def scheduler():
    """Щодня о SEND_TIME надсилає план на сьогодні у чати з CHAT_IDS."""
    last_sent = None
    while True:
        try:
            now = datetime.now(TZ)
            if CHAT_IDS and now.strftime("%H:%M") == SEND_TIME and last_sent != now.date():
                last_sent = now.date()
                key = (now.month, now.day)
                if key in load_plan():
                    for chat_id in CHAT_IDS:
                        send_day(chat_id, key)
        except Exception as e:
            print("Помилка розсилки:", e)
        time.sleep(20)


def main():
    if not TOKEN:
        raise SystemExit("Не задано BOT_TOKEN. Додайте його у змінних середовища.")
    api("deleteWebhook")
    api("setMyCommands", commands=[
        {"command": "today", "description": "План на сьогодні"},
        {"command": "days", "description": "Обрати день"},
        {"command": "id", "description": "Показати номер чату"},
    ])
    threading.Thread(target=scheduler, daemon=True).start()
    print("Бот запущено. План днів:", len(load_plan()))
    offset = None
    while True:
        res = api("getUpdates", offset=offset, timeout=50,
                  allowed_updates=["message", "callback_query"])
        if not res or not res.get("ok"):
            time.sleep(5)
            continue
        for update in res["result"]:
            offset = update["update_id"] + 1
            try:
                handle(update)
            except Exception as e:
                print("Помилка обробки:", e)


if __name__ == "__main__":
    main()
