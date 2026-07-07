from http.server import BaseHTTPRequestHandler
import os
import re
import json
import time
import requests


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
SEND_WARNINGS = os.getenv("SEND_WARNINGS", "false").lower().strip() == "true"

# إعدادات الاسبام
FLOOD_LIMIT = int(os.getenv("FLOOD_LIMIT", "5"))      # عدد الرسائل
FLOOD_SECONDS = int(os.getenv("FLOOD_SECONDS", "10")) # خلال كام ثانية
REPEAT_SECONDS = int(os.getenv("REPEAT_SECONDS", "60"))
PHOTO_FLOOD_LIMIT = int(os.getenv("PHOTO_FLOOD_LIMIT", "6"))
PHOTO_FLOOD_SECONDS = int(os.getenv("PHOTO_FLOOD_SECONDS", "10"))

# ذاكرة مؤقتة داخل Vercel
user_message_times = {}
user_photo_times = {}
recent_texts = {}
seen_photos = {}

PHOTO_REPEAT_SECONDS = 3 * 24 * 60 * 60

LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|bit\.ly|tinyurl\.com|wa\.me/|whatsapp\.com|discord\.gg|fb\.com|facebook\.com|instagram\.com|youtube\.com|youtu\.be|x\.com|twitter\.com|snapchat\.com|vm\.tiktok\.com|tiktok\.com)",
    re.IGNORECASE
)

# قاموس شتايم مصري/عربي بنسخ وكتابات مختلفة
BAD_WORDS = [
    # شتايم مصرية وعربية شائعة + تصريفات
    "احا", "احه", "احاا", "احااا",
    "خول", "خوال", "خوله", "خولات",
    "متناك", "متناكه", "متناكة", "متناكين", "متناكين",
    "منيوك", "منيوكه", "منيوكة", "منايك",
    "شرموط", "شرموطه", "شرموطة", "شراميط",
    "عرص", "معرص", "معرصه", "معرصة", "معرصين",
    "كس", "كسم", "كسمك", "كسمه", "كسمها", "كسمين", "كس امك", "كس اختك",
    "زبر", "زب", "زبي", "زبرك",
    "طيز", "طيزك", "طيزه", "طيزها",
    "نيك", "انيك", "هنيك", "ينيك", "نيكك", "منيك",
    "لبوه", "لبوة",
    "قحبه", "قحبة", "قحاب",
    "وسخ", "وسخه", "وسخة", "اوساخ",
    "ابن كلب", "ابن الكلب", "ولاد الكلب",
    "ابن وسخه", "ابن وسخة",
    "ابن شرموطه", "ابن شرموطة",
    "ابن متناكه", "ابن متناكة",
    "يا حيوان", "حيوان ابن",
    "يا كلب", "كلب ابن",
    "يا عرص", "يا خول", "يا متناك",
    "يا منيوك", "يا شرموط",
    "مص", "مصمص",
    "لحس", "الحس",
    "خرا", "خرى", "خرا عليك",
    "تف عليك",
    "ديوث", "قرني",
    "نجس", "نجسه",
    "سافل", "سافله",
    "حقير", "حقيره",
    "جزمه", "جزمة",
    "حمار", "حماره",
    "غبي", "غبيه",
    "اهبل", "اهبله",
    "متخلف", "متخلفه",
    # Arabizi / English evasions الشائعة
    "kosom", "kos om", "kosomek", "kosomak", "ksmk", "kسمك",
    "sharmoot", "sharmota", "sharmouta",
    "metnak", "mtnak", "manyook", "mnyok",
    "5awal", "khawal", "3ars", "m3ars",
    "a7a", "e7a",
    "zeb", "zobr", "teez", "tyz",
    "fuck", "fucking", "motherfucker", "bitch", "son of a bitch",
]


def normalize_arabic(text):
    text = text or ""
    text = text.lower()
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)

    # شيل التطويل والمسافات والرموز اللي الناس بتستخدمها للهروب
    text = text.replace("ـ", "")
    text = re.sub(r"[\s\-_.*~`'\"|\\/]+", "", text)
    return text


NORMALIZED_BAD_WORDS = [normalize_arabic(w) for w in BAD_WORDS]


def tg_api(method, payload=None):
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN is missing"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload or {}, timeout=10)
        return response.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def get_text(msg):
    return f"{msg.get('text') or ''}\n{msg.get('caption') or ''}".strip()


def message_has_link(msg):
    text = get_text(msg)

    if LINK_RE.search(text):
        return True

    entities = []
    entities.extend(msg.get("entities") or [])
    entities.extend(msg.get("caption_entities") or [])

    for ent in entities:
        if ent.get("type") in ("url", "text_link"):
            return True

    return False


def message_has_bad_word(msg):
    normalized = normalize_arabic(get_text(msg))

    if not normalized:
        return False

    for bad in NORMALIZED_BAD_WORDS:
        if bad and bad in normalized:
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
            "المسموح: كلام محترم وصور بطاقات ببجي ✅\n"
            "الممنوع: روابط / شتايم / سبام"
        )
    })


def clean_old_memory():
    now = int(time.time())

    for user_id, times in list(user_message_times.items()):
        user_message_times[user_id] = [t for t in times if now - t <= FLOOD_SECONDS]
        if not user_message_times[user_id]:
            del user_message_times[user_id]

    for user_id, times in list(user_photo_times.items()):
        user_photo_times[user_id] = [t for t in times if now - t <= PHOTO_FLOOD_SECONDS]
        if not user_photo_times[user_id]:
            del user_photo_times[user_id]

    for key, ts in list(recent_texts.items()):
        if now - ts > REPEAT_SECONDS:
            del recent_texts[key]

    for key, ts in list(seen_photos.items()):
        if now - ts > PHOTO_REPEAT_SECONDS:
            del seen_photos[key]


def is_flood(user_id):
    now = int(time.time())
    times = user_message_times.setdefault(str(user_id), [])
    times.append(now)
    user_message_times[str(user_id)] = [t for t in times if now - t <= FLOOD_SECONDS]
    return len(user_message_times[str(user_id)]) > FLOOD_LIMIT



def is_photo_flood(user_id, msg):
    photos = msg.get("photo") or []
    if not photos:
        return False

    now = int(time.time())
    key = str(user_id)
    times = user_photo_times.setdefault(key, [])
    times.append(now)
    user_photo_times[key] = [t for t in times if now - t <= PHOTO_FLOOD_SECONDS]
    return len(user_photo_times[key]) > PHOTO_FLOOD_LIMIT


def is_forwarded(msg):
    # Telegram Bot API الحديث والقديم
    return bool(
        msg.get("forward_origin")
        or msg.get("forward_date")
        or msg.get("forward_from")
        or msg.get("forward_from_chat")
        or msg.get("forward_sender_name")
    )


def is_repeated_text(chat_id, user_id, text):
    text = (text or "").strip()
    if not text:
        return False

    normalized = normalize_arabic(text)
    if len(normalized) < 4:
        return False

    key = f"{chat_id}:{user_id}:{normalized}"
    now = int(time.time())

    if key in recent_texts and now - recent_texts[key] <= REPEAT_SECONDS:
        return True

    recent_texts[key] = now
    return False


def is_repeated_photo(msg):
    photos = msg.get("photo") or []
    if not photos:
        return False

    photo_unique_id = photos[-1].get("file_unique_id")
    if not photo_unique_id:
        return False

    now = int(time.time())
    if photo_unique_id in seen_photos and now - seen_photos[photo_unique_id] <= PHOTO_REPEAT_SECONDS:
        return True

    seen_photos[photo_unique_id] = now
    return False


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

    if user_is_admin(chat_id, user_id):
        return

    clean_old_memory()

    # منع الاسبام السريع
    if is_flood(user_id):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع السبام والرسائل الكتير ورا بعض")
        return

    # منع الرسائل المعاد توجيهها Forward
    if is_forwarded(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع الرسائل المعاد توجيهها في الجروب")
        return

    # المسموح من الميديا: الصور فقط
    # الكلام العادي وصورة + كابشن مسموحين
    forbidden_media = (
        msg.get("video")
        or msg.get("animation")
        or msg.get("document")
        or msg.get("audio")
        or msg.get("voice")
        or msg.get("video_note")
        or msg.get("sticker")
    )
    if forbidden_media:
        delete_message(chat_id, message_id)
        send_warning(chat_id, "المسموح من الميديا هو الصور فقط")
        return

    # منع سبام الصور فقط، وليس الصورة العادية
    if is_photo_flood(user_id, msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع ارسال صور كتير بسرعة")
        return

    # منع الروابط
    if message_has_link(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع نشر روابط في الجروب")
        return

    # منع الشتايم
    if message_has_bad_word(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع الشتيمة في الجروب")
        return

    text = get_text(msg)

    # منع تكرار نفس الكلام
    if is_repeated_text(chat_id, user_id, text):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع تكرار نفس الرسالة")
        return

    # الصور مسموحة، بس نفس ملف الصورة لو اتكرر يتحذف
    if is_repeated_photo(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "الصورة دي اتبعت قبل كده")
        return

    # غير كده مسموح: كلام محترم وصور


def set_webhook():
    if not BOT_TOKEN:
        return 500, {"ok": False, "error": "BOT_TOKEN is missing"}

    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    vercel_url = os.getenv("VERCEL_URL", "").strip()

    if not webhook_url and vercel_url:
        webhook_url = f"https://{vercel_url}/api/bot"

    if not webhook_url:
        return 500, {
            "ok": False,
            "error": "WEBHOOK_URL is missing. Add WEBHOOK_URL=https://your-project.vercel.app/api/bot"
        }

    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "edited_message"],
        "drop_pending_updates": True
    }

    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
            json=payload,
            timeout=10
        )
        data = response.json()
    except Exception as e:
        return 500, {"ok": False, "error": str(e)}

    return 200, {
        "requested_webhook_url": webhook_url,
        "telegram_response": data
    }


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        if path.endswith("/api/set_webhook"):
            status, data = set_webhook()
            self._send_json(status, data)
            return

        self._send_json(200, {
            "ok": True,
            "message": "Fr3oon Helper Bot V4 is running",
            "rules": "text/photos allowed; other media/links/profanity/spam/photo-flood/forwards blocked"
        })

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")

        if not path.endswith("/api/bot"):
            self._send_json(404, {"ok": False, "error": "Not found"})
            return

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
