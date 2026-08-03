from http.server import BaseHTTPRequestHandler
import os
import re
import json
import time
from io import BytesIO
from datetime import datetime, timedelta
import requests
from PIL import Image, ImageOps, ImageEnhance
import pytesseract

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
SEND_WARNINGS = os.getenv("SEND_WARNINGS", "false").lower().strip() == "true"
REQUIRE_PHOTO_TEMPLATE = os.getenv("REQUIRE_PHOTO_TEMPLATE", "false").lower().strip() == "true"
PHOTO_EXPIRY_DAYS = int(os.getenv("PHOTO_EXPIRY_DAYS", "3"))
OCR_FROM_IMAGE = os.getenv("OCR_FROM_IMAGE", "true").lower().strip() == "true"
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "").strip()
OCR_PREFER_CLOUD = os.getenv("OCR_PREFER_CLOUD", "true").lower().strip() == "true"

FLOOD_LIMIT = int(os.getenv("FLOOD_LIMIT", "5"))
FLOOD_SECONDS = int(os.getenv("FLOOD_SECONDS", "10"))
REPEAT_SECONDS = int(os.getenv("REPEAT_SECONDS", "60"))
PHOTO_FLOOD_LIMIT = int(os.getenv("PHOTO_FLOOD_LIMIT", "6"))
PHOTO_FLOOD_SECONDS = int(os.getenv("PHOTO_FLOOD_SECONDS", "10"))

user_message_times = {}
user_photo_times = {}
recent_texts = {}
seen_photos = {}

PHOTO_REPEAT_SECONDS = 3 * 24 * 60 * 60

LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|bit\.ly|tinyurl\.com|wa\.me/|whatsapp\.com|discord\.gg|fb\.com|facebook\.com|instagram\.com|youtube\.com|youtu\.be|x\.com|twitter\.com|snapchat\.com|vm\.tiktok\.com|tiktok\.com)",
    re.IGNORECASE,
)

BAD_WORDS = [
    "احا", "احه", "احاا", "احااا", "خول", "خوال", "خوله", "خولات",
    "متناك", "متناكه", "متناكة", "متناكين", "منيوك", "منيوكه", "منيوكة", "منايك",
    "شرموط", "شرموطه", "شرموطة", "شراميط", "عرص", "معرص", "معرصه", "معرصة", "معرصين",
    "كس", "كسم", "كسمك", "كسمه", "كسمها", "كسمين", "كس امك", "كس اختك",
    "زبر", "زب", "زبي", "زبرك", "طيز", "طيزك", "طيزه", "طيزها", "نيك", "انيك", "هنيك", "ينيك", "نيكك", "منيك",
    "لبوه", "لبوة", "قحبه", "قحبة", "قحاب", "وسخ", "وسخه", "وسخة", "اوساخ",
    "ابن كلب", "ابن الكلب", "ولاد الكلب", "ابن وسخه", "ابن وسخة", "ابن شرموطه", "ابن شرموطة",
    "ابن متناكه", "ابن متناكة", "يا حيوان", "حيوان ابن", "يا كلب", "كلب ابن", "يا عرص", "يا خول", "يا متناك",
    "يا منيوك", "يا شرموط", "مص", "مصمص", "لحس", "الحس", "خرا", "خرى", "خرا عليك", "تف عليك",
    "ديوث", "قرني", "نجس", "نجسه", "سافل", "سافله", "حقير", "حقيره", "جزمه", "جزمة", "حمار", "حماره",
    "غبي", "غبيه", "اهبل", "اهبله", "متخلف", "متخلفه", "kosom", "kos om", "kosomek", "kosomak", "ksmk",
    "sharmoot", "sharmota", "sharmouta", "metnak", "mtnak", "manyook", "mnyok", "5awal", "khawal", "3ars", "m3ars",
    "a7a", "e7a", "zeb", "zobr", "teez", "tyz", "fuck", "fucking", "motherfucker", "bitch", "son of a bitch",
]

NORMALIZED_BAD_WORDS = []

CODE_HINT_PATTERNS = [
    re.compile(r"(?:رمز(?:\s+الاستبدال)?|رمز(?:\s+الاسترداد)?|redeem\s*code|code)\s*[:=\-]?\s*([A-Za-z0-9\-]{5,25})", re.IGNORECASE),
]
DATE_TEXT_PATTERNS = [
    re.compile(r"(?:تاريخ|date|expiry|expires?|ينتهي|انتهاء)\s*[:=\-]?\s*([0-9]{4}[./-][0-9]{1,2}[./-][0-9]{1,2}(?:\s+[0-9]{1,2}[:.][0-9]{2}(?::[0-9]{2})?)?)", re.IGNORECASE),
    re.compile(r"(?:تاريخ|date|expiry|expires?|ينتهي|انتهاء)\s*[:=\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4}(?:\s+[0-9]{1,2}[:.][0-9]{2}(?::[0-9]{2})?)?)", re.IGNORECASE),
]

CONFUSABLE_MAP = str.maketrans({
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1", "|": "1", "!": "1",
    "Z": "2",
    "S": "5", "$": "5",
    "G": "6",
    "T": "7",
    "B": "8",
})

ARABIC_DIGITS_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_arabic(text):
    text = text or ""
    text = text.lower()
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    text = text.replace("ـ", "")
    text = re.sub(r"[\s\-_.*~`'\"|\\/]+", "", text)
    return text


NORMALIZED_BAD_WORDS = [normalize_arabic(w) for w in BAD_WORDS]


def tg_api(method, payload=None):
    if not BOT_TOKEN:
        return {"ok": False, "description": "BOT_TOKEN is missing"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload or {}, timeout=20)
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
    result = tg_api("getChatMember", {"chat_id": chat_id, "user_id": user_id})
    try:
        status = result["result"]["status"]
        return status in ("administrator", "creator")
    except Exception:
        return False


def delete_message(chat_id, message_id):
    return tg_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


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
    return bool(
        msg.get("forward_origin") or msg.get("forward_date") or msg.get("forward_from") or msg.get("forward_from_chat") or msg.get("forward_sender_name")
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


def parse_date_string(value):
    value = (value or "").strip()
    if not value:
        return None
    value = value.translate(ARABIC_DIGITS_MAP).replace("/", "-").replace(".", "-")
    value = re.sub(r"\s+", " ", value)
    candidates = [
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d-%m-%Y",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            pass
    return None


def format_datetime(dt):
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def sender_display_name(user):
    username = (user.get("username") or "").strip()
    if username:
        return username
    full = f"{user.get('first_name') or ''} {user.get('last_name') or ''}".strip()
    return full or "غير معروف"


def get_file_bytes(file_id):
    result = tg_api("getFile", {"file_id": file_id})
    try:
        file_path = result["result"]["file_path"]
    except Exception:
        return None
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    try:
        res = requests.get(url, timeout=25)
        if res.status_code == 200:
            return res.content
    except Exception:
        return None
    return None



def run_ocr_space(image_bytes):
    if not OCR_SPACE_API_KEY:
        return []
    try:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            data={
                "apikey": OCR_SPACE_API_KEY,
                "language": "eng",
                "OCREngine": "2",
                "isOverlayRequired": "false",
                "scale": "true",
            },
            files={"filename": ("card.png", image_bytes)},
            timeout=40,
        )
        data = response.json()
        results = []
        for item in data.get("ParsedResults") or []:
            parsed = (item.get("ParsedText") or "").strip()
            if parsed:
                results.append(parsed)
        return results
    except Exception:
        return []


def build_ocr_variants(img):
    img = img.convert("RGB")
    w, h = img.size
    gray = ImageOps.grayscale(img)
    variants = []
    variants.append(("full_psm6", gray.resize((w * 2, h * 2))))
    variants.append(("full_psm11", gray.resize((w * 2, h * 2))))

    sharp = ImageEnhance.Contrast(gray.resize((w * 2, h * 2))).enhance(2.2)
    variants.append(("sharp_psm6", sharp))

    thresh = ImageEnhance.Contrast(gray.resize((w * 2, h * 2))).enhance(2.5).point(lambda p: 255 if p > 160 else 0)
    variants.append(("thresh_psm6", thresh))

    low = gray.crop((int(w * 0.10), int(h * 0.46), int(w * 0.85), int(h * 0.82)))
    low = ImageEnhance.Contrast(low.resize((max(low.width * 3, 1), max(low.height * 3, 1)))).enhance(2.5)
    variants.append(("low_psm11", low))

    code_band = gray.crop((int(w * 0.16), int(h * 0.48), int(w * 0.78), int(h * 0.64)))
    code_band = ImageEnhance.Contrast(code_band.resize((max(code_band.width * 4, 1), max(code_band.height * 4, 1)))).enhance(3.0)
    variants.append(("code_psm7", code_band))

    return variants


def run_ocr_on_image_bytes(image_bytes):
    texts = []

    if OCR_PREFER_CLOUD:
        texts.extend(run_ocr_space(image_bytes))

    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception:
        return texts

    for name, variant in build_ocr_variants(img):
        config = "--psm 6"
        if name.endswith("psm11"):
            config = "--psm 11"
        elif name == "code_psm7":
            config = "--psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ:-"
        try:
            txt = pytesseract.image_to_string(variant, lang="eng", config=config)
            if txt and txt.strip():
                texts.append(txt.strip())
        except Exception:
            pass

    if not OCR_PREFER_CLOUD and OCR_SPACE_API_KEY:
        texts.extend(run_ocr_space(image_bytes))

    # remove duplicates while preserving order
    deduped = []
    seen = set()
    for t in texts:
        key = t.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def normalize_ocr_token(token):
    token = (token or "").upper().translate(ARABIC_DIGITS_MAP)
    token = re.sub(r"[^A-Z0-9\-]", "", token)
    token = token.replace("-", "")
    return token.translate(CONFUSABLE_MAP)


def extract_code_from_text(text):
    if not text:
        return None
    raw = text.translate(ARABIC_DIGITS_MAP)

    candidates = []

    for pattern in CODE_HINT_PATTERNS:
        for match in pattern.finditer(raw):
            candidate = normalize_ocr_token(match.group(1))
            if candidate:
                candidates.append((20, candidate))

    # candidate before ':' near Arabic text in many card screenshots
    for match in re.finditer(r"\b([A-Z0-9]{6,20})\b\s*[:：]", raw.upper()):
        candidate = normalize_ocr_token(match.group(1))
        if candidate:
            candidates.append((15, candidate))

    for match in re.finditer(r"\b[A-Z0-9\-]{6,20}\b", raw.upper()):
        original = match.group(0)
        candidate = normalize_ocr_token(original)
        if not candidate:
            continue
        if re.fullmatch(r"20\d{6}", candidate):  # غالبًا تاريخ YYYYMMDD وليس كود
            continue
        digit_count = sum(ch.isdigit() for ch in candidate)
        score = digit_count
        if 7 <= len(candidate) <= 12:
            score += 4
        if candidate.isdigit():
            score += 2
        candidates.append((score, candidate))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], sum(ch.isdigit() for ch in item[1]), len(item[1])), reverse=True)
    best = candidates[0][1]
    return best


def extract_issue_datetime_from_text(texts):
    if not texts:
        return None

    def valid_dt(y, mo, d, t=None):
        try:
            if t:
                t = t.replace('.', ':')
                if t.count(':') == 1:
                    fmt = "%Y-%m-%d %H:%M"
                else:
                    fmt = "%Y-%m-%d %H:%M:%S"
                return datetime.strptime(f"{y}-{int(mo):02d}-{int(d):02d} {t}", fmt)
            return datetime.strptime(f"{y}-{int(mo):02d}-{int(d):02d}", "%Y-%m-%d")
        except Exception:
            return None

    for text in texts:
        raw = text.translate(ARABIC_DIGITS_MAP)
        # separated date + optional time
        for m in re.finditer(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?:\s+(\d{1,2}[:.]\d{2}(?::\d{2})?))?", raw):
            dt = valid_dt(m.group(1), m.group(2), m.group(3), m.group(4))
            if dt:
                return dt
        # time before date
        for m in re.finditer(r"(\d{1,2}[:.]\d{2}(?::\d{2})?)\s+(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", raw):
            dt = valid_dt(m.group(2), m.group(3), m.group(4), m.group(1))
            if dt:
                return dt
    return None


def parse_card_info_from_caption(msg, user):
    text = (msg.get("caption") or msg.get("text") or "").strip()
    if not text:
        return None

    code = None
    for pattern in CODE_HINT_PATTERNS:
        match = pattern.search(text)
        if match:
            code = normalize_ocr_token(match.group(1))
            break
    if not code:
        generic = re.search(r"\b([A-Za-z0-9\-]{6,20})\b", text)
        if generic:
            code = normalize_ocr_token(generic.group(1))

    issue_dt = None
    for pattern in DATE_TEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            issue_dt = parse_date_string(match.group(1))
            if issue_dt:
                break

    if code:
        issue_dt = issue_dt or datetime.utcfromtimestamp(msg.get("date", int(time.time())))
        return {
            "name": sender_display_name(user),
            "code": code,
            "issued_at": issue_dt,
            "expiry_at": issue_dt + timedelta(days=PHOTO_EXPIRY_DAYS),
            "source": "caption",
        }
    return None


def parse_card_info_from_photo(msg, user):
    photos = msg.get("photo") or []
    if not photos:
        return None
    file_id = photos[-1].get("file_id")
    if not file_id:
        return None
    image_bytes = get_file_bytes(file_id)
    if not image_bytes:
        return None

    texts = run_ocr_on_image_bytes(image_bytes)
    if not texts:
        return None
    combined = "\n".join(texts)
    code = extract_code_from_text(combined)
    if not code:
        return None

    issue_dt = extract_issue_datetime_from_text(texts)
    if not issue_dt:
        issue_dt = datetime.utcfromtimestamp(msg.get("date", int(time.time())))

    return {
        "name": sender_display_name(user),
        "code": code,
        "issued_at": issue_dt,
        "expiry_at": issue_dt + timedelta(days=PHOTO_EXPIRY_DAYS),
        "source": "ocr",
    }


def send_card_summary(chat_id, reply_to_message_id, info):
    name = info.get("name")
    code = info.get("code")
    issued_at = info.get("issued_at")
    expiry_at = info.get("expiry_at")

    text = (
        "done ✅\n\n"
        f"👤 = {name}\n"
        f"🎟️ = <code>{code}</code>\n"
        f"📅 = {format_datetime(issued_at)}\n"
        f"⏳ = {format_datetime(expiry_at)}"
    )

    return tg_api("sendMessage", {
        "chat_id": chat_id,
        "reply_to_message_id": reply_to_message_id,
        "text": text,
        "parse_mode": "HTML",
    })


def send_photo_ocr_help(chat_id, reply_to_message_id=None):
    text = (
        "الصورة اتمسحت لأن البوت معرفش يقرأ الكود منها بدقة ❌\n\n"
        "ابعت الصورة كاملة وواضحة، ويظهر فيها:\n"
        "- رمز الاسترداد\n"
        "- التاريخ أو وقت الصورة لو موجود\n\n"
        "ولو القراءة لسه صعبة، اكتب الكود في الكابشن بالشكل ده:\n"
        "كود: ABC123456"
    )
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    return tg_api("sendMessage", payload)


def handle_message(msg):
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}

    if not is_group(chat):
        return

    # منشور القناة المرتبطة الخاص بالتعليقات
    if msg.get("is_automatic_forward") is True:
        return

    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    user_id = user.get("id")

    if not chat_id or not message_id or not user_id:
        return

    is_admin = user_is_admin(chat_id, user_id)

    clean_old_memory()

<<<<<<< HEAD
    if not is_admin and is_flood(user_id):
=======
    if is_flood(user_id):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع السبام والرسائل الكتير ورا بعض")
        return

<<<<<<< HEAD
    if not is_admin and is_forwarded(msg):
=======
    if is_forwarded(msg):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع الرسائل المعاد توجيهها في الجروب")
        return

    forbidden_media = msg.get("video") or msg.get("animation") or msg.get("document") or msg.get("audio") or msg.get("voice") or msg.get("video_note") or msg.get("sticker")
<<<<<<< HEAD
    if not is_admin and forbidden_media:
=======
    if forbidden_media:
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "المسموح من الميديا هو الصور فقط")
        return

<<<<<<< HEAD
    if not is_admin and is_photo_flood(user_id, msg):
=======
    if is_photo_flood(user_id, msg):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع ارسال صور كتير بسرعة")
        return

<<<<<<< HEAD
    if not is_admin and message_has_link(msg):
=======
    if message_has_link(msg):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع نشر روابط في الجروب")
        return

<<<<<<< HEAD
    if not is_admin and message_has_bad_word(msg):
=======
    if message_has_bad_word(msg):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع الشتيمة في الجروب")
        return

    text = get_text(msg)
<<<<<<< HEAD
    if not is_admin and is_repeated_text(chat_id, user_id, text):
=======
    if is_repeated_text(chat_id, user_id, text):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع تكرار نفس الرسالة")
        return

<<<<<<< HEAD
    if not is_admin and is_repeated_photo(msg):
=======
    if is_repeated_photo(msg):
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
        delete_message(chat_id, message_id)
        send_warning(chat_id, "الصورة دي اتبعت قبل كده")
        return

    # الصور: جرّب OCR من الصورة أولًا، ثم الكابشن كحل احتياطي
    if msg.get("photo"):
        info = None
        if OCR_FROM_IMAGE:
            info = parse_card_info_from_photo(msg, user)
        if not info:
            info = parse_card_info_from_caption(msg, user)
        if info:
            send_card_summary(chat_id, message_id, info)
            return
        if REQUIRE_PHOTO_TEMPLATE or OCR_FROM_IMAGE:
            delete_message(chat_id, message_id)
            send_photo_ocr_help(chat_id)
            return
        return

    # الكلام المحترم مسموح


def set_webhook():
    if not BOT_TOKEN:
        return 500, {"ok": False, "error": "BOT_TOKEN is missing"}
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    vercel_url = os.getenv("VERCEL_URL", "").strip()
    if not webhook_url and vercel_url:
        webhook_url = f"https://{vercel_url}/api/bot"
    if not webhook_url:
        return 500, {"ok": False, "error": "WEBHOOK_URL is missing. Add WEBHOOK_URL=https://your-project.vercel.app/api/bot"}
    payload = {"url": webhook_url, "allowed_updates": ["message", "edited_message"], "drop_pending_updates": True}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    try:
        response = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json=payload, timeout=10)
        data = response.json()
    except Exception as e:
        return 500, {"ok": False, "error": str(e)}
    return 200, {"requested_webhook_url": webhook_url, "telegram_response": data}


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
<<<<<<< HEAD
            "message": "Fr3oon Helper Bot V8 OCR is running",
=======
            "message": "Fr3oon Helper Bot V7 OCR is running",
>>>>>>> 349db093dd13ca8146bc168ae35834124113968c
            "rules": "text/photos allowed; OCR on images; other media/links/profanity/spam/photo-flood/forwards blocked",
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
