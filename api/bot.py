from http.server import BaseHTTPRequestHandler
import os
import re
import json
import time
import requests


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
SEND_WARNINGS = os.getenv("SEND_WARNINGS", "false").lower().strip() == "true"

KEEP_SECONDS = 3 * 24 * 60 * 60  # 3 أيام - منع تكرار مؤقت قدر الإمكان
seen_photos = {}

LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|bit\.ly|tinyurl\.com|wa\.me/|whatsapp\.com|discord\.gg|fb\.com|facebook\.com|instagram\.com|youtube\.com|youtu\.be)",
    re.IGNORECASE
)


def tg_api(method, payload=None):
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN is missing"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload or {}, timeout=10)
        return response.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def message_has_link(msg):
    text = f"{msg.get('text') or ''}\n{msg.get('caption') or ''}"

    if LINK_RE.search(text):
        return True

    entities = []
    entities.extend(msg.get("entities") or [])
    entities.extend(msg.get("caption_entities") or [])

    for ent in entities:
        if ent.get("type") in ("url", "text_link"):
            return True

    return False


def is_group(chat):
    return chat.get("type") in ("group", "supergroup")


def user_is_admin(chat_id, user_id):
    result = tg_api("getChatMember", {
        "chat_id": chat_id,
        "user_id": user_id
    })

    try:
        status = result["result"]["status"]
        return status in ("administrator", "creator")
    except Exception:
        return False


def delete_message(chat_id, message_id):
    return tg_api("deleteMessage", {
        "chat_id": chat_id,
        "message_id": message_id
    })


def send_warning(chat_id, reason):
    if not SEND_WARNINGS:
        return

    tg_api("sendMessage", {
        "chat_id": chat_id,
        "text": (
            "تم حذف الرسالة ❌\n\n"
            f"{reason}\n\n"
            "المسموح هنا: صور بطاقات ببجي فقط ✅\n"
            "ممنوع الروابط او الكلام العشوائي"
        )
    })


def clean_seen_photos():
    now = int(time.time())
    old_keys = [
        key for key, ts in seen_photos.items()
        if now - ts > KEEP_SECONDS
    ]

    for key in old_keys:
        del seen_photos[key]


def handle_message(msg):
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}

    if not is_group(chat):
        return

    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    user_id = user.get("id")

    if not chat_id or not message_id or not user_id:
        return

    # سيب الادمنز عادي
    if user_is_admin(chat_id, user_id):
        return

    # منع الروابط في النص او الكابشن
    if message_has_link(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع نشر روابط في الجروب")
        return

    # السماح بالصور فقط
    photos = msg.get("photo") or []
    if not photos:
        delete_message(chat_id, message_id)
        send_warning(chat_id, "الجروب مخصص لصور بطاقات ببجي فقط")
        return

    # منع تكرار نفس ملف الصورة قدر الإمكان
    # ملاحظة: على Vercel التخزين مؤقت وليس مضمون 100٪ بين كل تشغيل
    clean_seen_photos()
    photo_unique_id = photos[-1].get("file_unique_id")

    if photo_unique_id:
        if photo_unique_id in seen_photos:
            delete_message(chat_id, message_id)
            send_warning(chat_id, "الصورة دي اتبعت قبل كده")
            return

        seen_photos[photo_unique_id] = int(time.time())


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        self._send_json(200, {
            "ok": True,
            "message": "Fr3oon Helper Bot is running"
        })

    def do_POST(self):
        # حماية اختيارية لو حطيت WEBHOOK_SECRET في Vercel
        if WEBHOOK_SECRET:
            incoming_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if incoming_secret != WEBHOOK_SECRET:
                self._send_json(403, {"ok": False, "error": "Forbidden"})
                return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            update = json.loads(body.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return

        msg = update.get("message") or update.get("edited_message")
        if msg:
            handle_message(msg)

        self._send_json(200, {"ok": True})
