from http.server import BaseHTTPRequestHandler
import os
import re
import json
import time
from io import BytesIO
from datetime import datetime, timedelta, timezone
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

# إعدادات إدارة الجروب العامة
ENABLE_GROUP_TOOLS = os.getenv("ENABLE_GROUP_TOOLS", "true").lower().strip() == "true"
REQUIRE_RULES_ACCEPTANCE = os.getenv("REQUIRE_RULES_ACCEPTANCE", "true").lower().strip() == "true"
WELCOME_DELETE_SECONDS = int(os.getenv("WELCOME_DELETE_SECONDS", "60"))
WARNING_DELETE_SECONDS = int(os.getenv("WARNING_DELETE_SECONDS", "30"))
DEFAULT_MUTE_MINUTES = int(os.getenv("DEFAULT_MUTE_MINUTES", "10"))
ADMIN_CONTACT_USERNAME = os.getenv("ADMIN_CONTACT_USERNAME", "Mofr3oon").strip().lstrip("@")

FLOOD_LIMIT = int(os.getenv("FLOOD_LIMIT", "5"))
FLOOD_SECONDS = int(os.getenv("FLOOD_SECONDS", "10"))
REPEAT_SECONDS = int(os.getenv("REPEAT_SECONDS", "60"))
PHOTO_FLOOD_LIMIT = int(os.getenv("PHOTO_FLOOD_LIMIT", "6"))
PHOTO_FLOOD_SECONDS = int(os.getenv("PHOTO_FLOOD_SECONDS", "10"))

user_message_times = {}
user_photo_times = {}
recent_texts = {}
seen_photos = {}
seen_codes = {}
stats = {"accepted": 0, "duplicate": 0, "expired": 0, "ocr_failed": 0, "marked_used": 0}
user_warnings = {}
accepted_rules = set()
slow_mode_seconds = {}
last_group_message = {}
locked_chats = set()

PHOTO_REPEAT_SECONDS = 3 * 24 * 60 * 60
CAIRO_TZ = timezone(timedelta(hours=3))
CODE_MEMORY_SECONDS = 7 * 24 * 60 * 60

LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|bit\.ly|tinyurl\.com|wa\.me/|whatsapp\.com|discord\.gg|fb\.com|facebook\.com|instagram\.com|youtube\.com|youtu\.be|x\.com|twitter\.com|snapchat\.com|vm\.tiktok\.com|tiktok\.com)",
    re.IGNORECASE,
)

SALE_RE = re.compile(r"(?:للبيع|بيع\s+حساب|حساب\s+للبيع|بكام|سعره?|تحويل|فودافون\s*كاش|انستا\s*باي|كلمني\s+خاص|ادفع|دفع\s+مقدم)", re.IGNORECASE)
CREDENTIAL_RE = re.compile(r"(?:الباسورد|كلمة\s+السر|الايميل|الإيميل|كود\s+التحقق|رمز\s+التحقق|otp|بيانات\s+الحساب|رقم\s+الموبايل|رقم\s+الهاتف)", re.IGNORECASE)
SEVERE_CREDENTIAL_RE = re.compile(r"(?:هات|ابعت|ارسل|اديني).{0,20}(?:الباسورد|كلمة\s+السر|كود\s+التحقق|رمز\s+التحقق|otp)", re.IGNORECASE)
FAQ_EXCHANGE_RE = re.compile(r"(?:ابادل\s+ازاي|التبادل\s+ازاي|اعمل\s+تبادل\s+ازاي)", re.IGNORECASE)
FAQ_CODE_RE = re.compile(r"(?:الكود\s+بيتحط\s+فين|احط\s+الكود\s+فين|استبدل\s+الكود\s+ازاي)", re.IGNORECASE)

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
    for code, item in list(seen_codes.items()):
        if now - item.get("ts", 0) > CODE_MEMORY_SECONDS:
            del seen_codes[code]


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


def cairo_now():
    return datetime.now(CAIRO_TZ).replace(tzinfo=None)


def telegram_local_datetime(msg):
    ts = msg.get("date", int(time.time()))
    return datetime.fromtimestamp(ts, CAIRO_TZ).replace(tzinfo=None)


def human_remaining(expiry_at):
    delta = expiry_at - cairo_now()
    total_minutes = max(0, int(delta.total_seconds() // 60))
    days, rem = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem, 60)
    if days:
        return f"{days} يوم و{hours} ساعة"
    if hours:
        return f"{hours} ساعة و{minutes} دقيقة"
    return f"{minutes} دقيقة"


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



def run_ocr_space(image_bytes, filename="card.png", engine="2"):
    if not OCR_SPACE_API_KEY:
        return []
    try:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            data={
                "apikey": OCR_SPACE_API_KEY,
                "language": "eng",
                "OCREngine": engine,
                "isOverlayRequired": "false",
                "scale": "true",
                "detectOrientation": "true",
            },
            files={"filename": (filename, image_bytes)},
            timeout=45,
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


def image_to_png_bytes(img):
    output = BytesIO()
    img.save(output, format="PNG", optimize=True)
    return output.getvalue()


def build_cloud_crops(image_bytes):
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return []

    w, h = img.size
    crops = []

    # موضع رقم رمز الاستبدال ثابت تقريبًا في صور بطاقات PUBG.
    # نقص سطر الأرقام فقط بعيدًا عن التاريخ والنص العربي.
    crop_boxes = [
        (0.345, 0.615, 0.555, 0.735),
        (0.365, 0.625, 0.535, 0.725),
        (0.385, 0.635, 0.515, 0.715),
    ]

    for idx, box in enumerate(crop_boxes, start=1):
        crop = img.crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))
        crop = crop.resize((max(crop.width * 7, 1), max(crop.height * 7, 1)))
        crop = ImageEnhance.Sharpness(crop).enhance(2.0)
        crops.append((f"code-tight-{idx}.png", image_to_png_bytes(crop)))

        # عزل اللون البرتقالي الخاص بالأرقام، وتحويله لأسود على خلفية بيضاء.
        pixels = crop.load()
        masked = Image.new("L", crop.size, 255)
        mask_pixels = masked.load()
        for y in range(crop.height):
            for x in range(crop.width):
                r, g, b = pixels[x, y]
                is_orange = (
                    r >= 120
                    and g >= 45
                    and g <= 190
                    and b <= 130
                    and r >= g + 25
                    and g >= b + 10
                )
                if is_orange:
                    mask_pixels[x, y] = 0
        masked = ImageEnhance.Contrast(masked).enhance(2.0)
        crops.append((f"code-orange-{idx}.png", image_to_png_bytes(masked)))

    return crops


def build_date_crops(image_bytes):
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return []
    w, h = img.size
    boxes = [
        (0.30, 0.70, 0.70, 0.82),
        (0.34, 0.72, 0.66, 0.80),
        (0.25, 0.66, 0.75, 0.84),
    ]
    crops = []
    for idx, box in enumerate(boxes, start=1):
        crop = img.crop((int(w*box[0]), int(h*box[1]), int(w*box[2]), int(h*box[3])))
        crop = crop.resize((max(crop.width*6, 1), max(crop.height*6, 1)))
        crop = ImageEnhance.Contrast(crop).enhance(2.2)
        crop = ImageEnhance.Sharpness(crop).enhance(2.5)
        crops.append((f"date-{idx}.png", image_to_png_bytes(crop)))
    return crops

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

    # OCR الصورة كاملة للتاريخ فقط.
    if OCR_PREFER_CLOUD:
        for text in run_ocr_space(image_bytes, "card-full.png", "2"):
            texts.append(("full", text))

        # الأكواد تُقرأ فقط من قصاصات سطر الرقم، ولا نعتمد على أرقام باقي الصورة.
        for filename, crop_bytes in build_cloud_crops(image_bytes):
            for engine in ("2", "1"):
                for text in run_ocr_space(crop_bytes, filename, engine):
                    texts.append((filename, text))
        for filename, crop_bytes in build_date_crops(image_bytes):
            for engine in ("2", "1"):
                for text in run_ocr_space(crop_bytes, filename, engine):
                    texts.append((filename, text))

    try:
        img = Image.open(BytesIO(image_bytes))
    except Exception:
        return texts

    # القراءة المحلية احتياطيًا، مع تمييز مصدرها.
    for name, variant in build_ocr_variants(img):
        config = "--psm 6"
        if name.endswith("psm11"):
            config = "--psm 11"
        elif name == "code_psm7":
            config = "--psm 7 -c tessedit_char_whitelist=0123456789"
        try:
            txt = pytesseract.image_to_string(variant, lang="eng", config=config)
            if txt and txt.strip():
                texts.append((name, txt.strip()))
        except Exception:
            pass

    if not OCR_PREFER_CLOUD and OCR_SPACE_API_KEY:
        for text in run_ocr_space(image_bytes, "card-full.png", "2"):
            texts.append(("full", text))
        for filename, crop_bytes in build_cloud_crops(image_bytes):
            for engine in ("2", "1"):
                for text in run_ocr_space(crop_bytes, filename, engine):
                    texts.append((filename, text))
        for filename, crop_bytes in build_date_crops(image_bytes):
            for engine in ("2", "1"):
                for text in run_ocr_space(crop_bytes, filename, engine):
                    texts.append((filename, text))

    deduped = []
    seen = set()
    for source, text in texts:
        key = (source, text.strip())
        if text.strip() and key not in seen:
            seen.add(key)
            deduped.append((source, text.strip()))
    return deduped

def normalize_ocr_token(token):
    token = (token or "").upper().translate(ARABIC_DIGITS_MAP)
    token = re.sub(r"[^A-Z0-9\-]", "", token)
    token = token.replace("-", "")
    return token.translate(CONFUSABLE_MAP)


def extract_code_from_ocr_results(results):
    if not results:
        return None

    votes = {}
    sources_by_code = {}

    for source, text in results:
        # لا نستخدم الصورة الكاملة لاستخراج الكود حتى لا نلتقط التاريخ أو أرقامًا أخرى.
        if source == "full" or source.startswith("full_") or source in ("low_psm11", "sharp_psm6", "thresh_psm6"):
            continue

        raw = text.translate(ARABIC_DIGITS_MAP).upper()
        for token in re.findall(r"[A-Z0-9]{7,13}", raw):
            normalized = normalize_ocr_token(token)
            if not normalized.isdigit() or len(normalized) != 9:
                continue
            if normalized.startswith(("2026", "2027", "2028", "2029")):
                continue

            # قصاصات اللون البرتقالي لها وزن أعلى لأنها لا تحتوي غالبًا إلا على الكود.
            weight = 4 if "orange" in source else 2
            votes[normalized] = votes.get(normalized, 0) + weight
            sources_by_code.setdefault(normalized, set()).add(source)

    if not votes:
        return None

    ranked = sorted(votes.items(), key=lambda item: (item[1], len(sources_by_code[item[0]])), reverse=True)
    best_code, best_score = ranked[0]
    best_sources = sources_by_code[best_code]

    # لا ننشر أي كود إلا إذا ظهر في مصدرين مستقلين على الأقل، أو حصل على تصويت قوي جدًا.
    if len(best_sources) < 2 and best_score < 6:
        return None

    # لو يوجد منافس قريب جدًا، نرفض التخمين بدل إرسال رقم غلط.
    if len(ranked) > 1 and ranked[1][1] >= best_score - 1:
        return None

    return best_code

def extract_issue_datetime_from_text(texts):
    if not texts:
        return None

    def normalize_digits(text):
        text = text.translate(ARABIC_DIGITS_MAP)
        return (text.replace("O", "0").replace("o", "0")
                    .replace("I", "1").replace("l", "1").replace("|", "1"))

    def valid_dt(y, mo, d, hh=0, mm=0, ss=0):
        try:
            y, mo, d, hh, mm, ss = map(int, (y, mo, d, hh, mm, ss))
            if not (2020 <= y <= 2035 and 1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
                return None
            return datetime(y, mo, d, hh, mm, ss)
        except Exception:
            return None

    candidates = []
    for item in texts:
        source, text = item if isinstance(item, tuple) else ("", item)
        raw = normalize_digits(text)
        weight = 4 if source.startswith("date-") else 1

        # الوقت قبل التاريخ: 14:25:13 2026.08.06
        for m in re.finditer(r"(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?\s+(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", raw):
            dt = valid_dt(m.group(4), m.group(5), m.group(6), m.group(1), m.group(2), m.group(3) or 0)
            if dt:
                candidates.append((weight + 5, dt))

        # التاريخ قبل الوقت
        for m in re.finditer(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})\s+(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?", raw):
            dt = valid_dt(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6) or 0)
            if dt:
                candidates.append((weight + 5, dt))

        # تاريخ فقط
        for m in re.finditer(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", raw):
            dt = valid_dt(m.group(1), m.group(2), m.group(3))
            if dt:
                candidates.append((weight, dt))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


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
        issue_dt = issue_dt or telegram_local_datetime(msg)
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
    code = extract_code_from_ocr_results(texts)
    if not code:
        return None

    issue_dt = extract_issue_datetime_from_text(texts)
    fallback_dt = telegram_local_datetime(msg)
    if not issue_dt:
        issue_dt = fallback_dt
    elif issue_dt.hour == 0 and issue_dt.minute == 0:
        # لو OCR قرأ التاريخ فقط، استخدم وقت إرسال الصورة بدل 00:00
        issue_dt = issue_dt.replace(hour=fallback_dt.hour, minute=fallback_dt.minute, second=fallback_dt.second)

    return {
        "name": sender_display_name(user),
        "code": code,
        "issued_at": issue_dt,
        "expiry_at": issue_dt + timedelta(days=PHOTO_EXPIRY_DAYS),
        "source": "ocr",
    }


def send_card_summary(chat_id, reply_to_message_id, info, owner_id):
    name = info.get("name")
    code = info.get("code")
    issued_at = info.get("issued_at")
    expiry_at = info.get("expiry_at")

    text = (
        "✅ <b>بطاقة متاحة</b>\n\n"
        f"👤 الناشر: <b>{name}</b>\n"
        "🎟 رمز الاستبدال:\n"
        f"<code>{code}</code>\n\n"
        f"📅 الإصدار: {format_datetime(issued_at)}\n"
        f"⏳ الانتهاء: {format_datetime(expiry_at)}\n"
        f"⌛ المتبقي: {human_remaining(expiry_at)}"
    )
    keyboard = {"inline_keyboard": [[{
        "text": "✅ تم الاستبدال",
        "callback_data": f"used:{owner_id}:{code}"
    }]]}
    return tg_api("sendMessage", {
        "chat_id": chat_id,
        "reply_to_message_id": reply_to_message_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    })


def send_photo_ocr_help(chat_id, reply_to_message_id=None):
    text = (
        "❌ معرفتش أقرأ رمز الاستبدال بدقة.\n"
        "ابعت الصورة كاملة وواضحة، أو اكتب في الكابشن: <code>كود: 123456789</code>"
    )
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    return tg_api("sendMessage", payload)


def send_simple_notice(chat_id, reply_to_message_id, text):
    return tg_api("sendMessage", {
        "chat_id": chat_id,
        "reply_to_message_id": reply_to_message_id,
        "text": text,
        "parse_mode": "HTML",
    })



def send_auto_delete_message(chat_id, text, reply_to_message_id=None, seconds=30, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = tg_api("sendMessage", payload)
    # Vercel لا يدعم انتظارًا طويلًا داخل الطلب؛ نضيف الحذف الفوري فقط لو seconds=0.
    # الرسائل المؤقتة يمكن تنظيفها يدويًا أو لاحقًا بجدولة خارجية.
    return result


def get_warning_key(chat_id, user_id):
    return f"{chat_id}:{user_id}"


def warning_count(chat_id, user_id):
    return user_warnings.get(get_warning_key(chat_id, user_id), 0)


def set_member_restricted(chat_id, user_id, restricted=True, until_date=None):
    if restricted:
        permissions = {
            "can_send_messages": False,
            "can_send_audios": False,
            "can_send_documents": False,
            "can_send_photos": False,
            "can_send_videos": False,
            "can_send_video_notes": False,
            "can_send_voice_notes": False,
            "can_send_polls": False,
            "can_send_other_messages": False,
            "can_add_web_page_previews": False,
            "can_change_info": False,
            "can_invite_users": False,
            "can_pin_messages": False,
            "can_manage_topics": False,
        }
    else:
        permissions = {
            "can_send_messages": True,
            "can_send_audios": True,
            "can_send_documents": True,
            "can_send_photos": True,
            "can_send_videos": True,
            "can_send_video_notes": True,
            "can_send_voice_notes": True,
            "can_send_polls": True,
            "can_send_other_messages": True,
            "can_add_web_page_previews": True,
            "can_change_info": False,
            "can_invite_users": True,
            "can_pin_messages": False,
            "can_manage_topics": False,
        }
    payload = {"chat_id": chat_id, "user_id": user_id, "permissions": permissions}
    if until_date:
        payload["until_date"] = until_date
    return tg_api("restrictChatMember", payload)


def add_violation(chat_id, user_id, reason, reply_to_message_id=None, severe=False):
    key = get_warning_key(chat_id, user_id)
    count = user_warnings.get(key, 0) + 1
    user_warnings[key] = count

    if severe:
        result = tg_api("banChatMember", {"chat_id": chat_id, "user_id": user_id})
        send_auto_delete_message(chat_id, f"🚫 تم حظر العضو بسبب مخالفة خطيرة:\n<b>{reason}</b>", reply_to_message_id, WARNING_DELETE_SECONDS)
        return result

    if count == 1:
        send_auto_delete_message(chat_id, f"⚠️ تحذير أول: <b>{reason}</b>\nالمخالفة القادمة تؤدي إلى كتم مؤقت.", reply_to_message_id, WARNING_DELETE_SECONDS)
    elif count == 2:
        until_date = int(time.time()) + DEFAULT_MUTE_MINUTES * 60
        set_member_restricted(chat_id, user_id, True, until_date)
        send_auto_delete_message(chat_id, f"🔇 تم كتم العضو لمدة {DEFAULT_MUTE_MINUTES} دقائق بسبب تكرار المخالفة.", reply_to_message_id, WARNING_DELETE_SECONDS)
    else:
        tg_api("banChatMember", {"chat_id": chat_id, "user_id": user_id})
        send_auto_delete_message(chat_id, "🚫 تم حظر العضو بعد 3 مخالفات.", reply_to_message_id, WARNING_DELETE_SECONDS)



def admin_contact_url():
    username = ADMIN_CONTACT_USERNAME or "Mofr3oon"
    return f"https://t.me/{username}"


def admin_contact_keyboard(extra_rows=None):
    rows = list(extra_rows or [])
    rows.append([{
        "text": "💬 تواصل مع الأدمن",
        "url": admin_contact_url(),
    }])
    return {"inline_keyboard": rows}


def replied_target(msg):
    replied = msg.get("reply_to_message") or {}
    target_user = replied.get("from") or {}
    target_id = target_user.get("id")
    target_message_id = replied.get("message_id")
    if not target_id or not target_message_id:
        return None, None, None
    return target_user, target_id, target_message_id


def target_can_be_moderated(chat_id, target_user_id):
    if not target_user_id:
        return False, "لم أجد العضو المطلوب."
    if user_is_admin(chat_id, target_user_id):
        return False, "لا يمكن تنفيذ الإجراء على أدمن في الجروب."
    member = tg_api("getChatMember", {"chat_id": chat_id, "user_id": target_user_id})
    try:
        if (member.get("result") or {}).get("user", {}).get("is_bot"):
            return False, "لا يمكن تنفيذ الإجراء على بوت."
    except Exception:
        pass
    return True, ""


def moderation_panel_keyboard(group_chat_id, target_user_id, target_message_id, message_url=None):
    rows = [
        [
            {"text": "⚠️ إنذار", "callback_data": f"pmod:w:{group_chat_id}:{target_user_id}:{target_message_id}"},
            {"text": f"🔇 كتم {DEFAULT_MUTE_MINUTES}د", "callback_data": f"pmod:m:{group_chat_id}:{target_user_id}:{target_message_id}"},
        ],
        [
            {"text": "🚫 حظر فوري", "callback_data": f"pmod:b:{group_chat_id}:{target_user_id}:{target_message_id}"},
            {"text": "🗑 حذف الرسالة", "callback_data": f"pmod:d:{group_chat_id}:{target_user_id}:{target_message_id}"},
        ],
        [
            {"text": "✅ فك الكتم", "callback_data": f"pmod:u:{group_chat_id}:{target_user_id}:{target_message_id}"},
            {"text": "♻️ تصفير الإنذارات", "callback_data": f"pmod:r:{group_chat_id}:{target_user_id}:{target_message_id}"},
        ],
    ]
    if message_url:
        rows.append([{"text": "🔎 فتح الرسالة في الجروب", "url": message_url}])
    return {"inline_keyboard": rows}


def telegram_message_url(chat, message_id):
    username = (chat.get("username") or "").strip().lstrip("@")
    if username:
        return f"https://t.me/{username}/{message_id}"
    chat_id = str(chat.get("id") or "")
    if chat_id.startswith("-100"):
        return f"https://t.me/c/{chat_id[4:]}/{message_id}"
    return None


def bot_private_url():
    result = tg_api("getMe")
    username = ((result.get("result") or {}).get("username") or "").strip()
    if not username:
        return None
    return f"https://t.me/{username}?start=admin"


def admin_action_notice(chat_id, reply_to_message_id, text):
    return send_auto_delete_message(chat_id, text, reply_to_message_id, WARNING_DELETE_SECONDS)

def group_rules_text():
    return (
        "📜 <b>قوانين جروب تبادل بطاقات ببجي</b>\n\n"
        "✅ المسموح: صور البطاقات + كلام محترم عن التبادل.\n"
        "❌ ممنوع البيع والشراء والتحويلات المالية.\n"
        "❌ ممنوع طلب الإيميل أو الباسورد أو كود التحقق.\n"
        "❌ ممنوع الروابط والفورورد والسبام والشتائم.\n"
        "⚠️ المخالفات: تحذير، ثم كتم، ثم حظر."
    )


def handle_new_members(msg):
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    members = msg.get("new_chat_members") or []
    if not chat_id or not members:
        return
    for member in members:
        if member.get("is_bot"):
            continue
        user_id = member.get("id")
        name = sender_display_name(member)
        if REQUIRE_RULES_ACCEPTANCE:
            set_member_restricted(chat_id, user_id, True)
        accept_rows = [[{
            "text": "✅ قرأت القوانين وأوافق",
            "callback_data": f"rules:{user_id}"
        }]] if REQUIRE_RULES_ACCEPTANCE else []
        keyboard = admin_contact_keyboard(accept_rows)
        send_auto_delete_message(
            chat_id,
            f"أهلًا يا <b>{name}</b> 👋\n\n{group_rules_text()}\n\nلو احتجت مساعدة اضغط زر <b>تواصل مع الأدمن</b>.",
            None,
            WELCOME_DELETE_SECONDS,
            keyboard,
        )
    if message_id:
        delete_message(chat_id, message_id)


def handle_service_message(msg):
    service_keys = (
        "left_chat_member", "pinned_message", "new_chat_title", "new_chat_photo",
        "delete_chat_photo", "group_chat_created", "supergroup_chat_created",
        "channel_chat_created", "message_auto_delete_timer_changed"
    )
    if any(msg.get(key) is not None for key in service_keys):
        chat_id = (msg.get("chat") or {}).get("id")
        message_id = msg.get("message_id")
        if chat_id and message_id:
            delete_message(chat_id, message_id)
        return True
    return False


def admin_list_text(chat_id):
    result = tg_api("getChatAdministrators", {"chat_id": chat_id})
    admins = []
    for item in result.get("result") or []:
        u = item.get("user") or {}
        if u.get("is_bot"):
            continue
        username = u.get("username")
        name = sender_display_name(u)
        admins.append(f"@{username}" if username else name)
    return "👮 الأدمن المتاحون: " + ("، ".join(admins) if admins else "غير متاحين حاليًا")


def handle_group_command(msg, is_admin):
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    user = msg.get("from") or {}
    user_id = user.get("id")
    text = (msg.get("text") or "").strip()
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""

    if command == "/rules":
        send_simple_notice(chat_id, message_id, group_rules_text())
        return True
    if command == "/help":
        help_text = (
            "🤖 <b>مساعدة الجروب</b>\n\n"
            "/rules — القوانين\n"
            "/admin — تواصل مع الأدمن\n"
            "/report — رد على رسالة للإبلاغ عنها\n"
            "/mywarnings — عدد مخالفاتك"
        )
        if is_admin:
            help_text += (
                "\n\n👮 <b>أوامر الأدمن بالرد على رسالة العضو:</b>\n"
                "/mod — إرسال لوحة الإنذار والكتم والحظر إلى الخاص\n"
                "/warn [السبب] — إنذار\n"
                "/mute [الدقائق] — كتم\n"
                "/unmute — فك الكتم\n"
                "/ban [السبب] — حظر فوري\n"
                "/unban — فك الحظر\n"
                "/resetwarn — تصفير الإنذارات\n"
                "/del — حذف الرسالة"
            )
        send_simple_notice(chat_id, message_id, help_text)
        return True
    if command == "/admin":
        tg_api("sendMessage", {
            "chat_id": chat_id,
            "reply_to_message_id": message_id,
            "text": f"👮 للتواصل مع الأدمن اضغط الزر بالأسفل: <b>@{ADMIN_CONTACT_USERNAME}</b>",
            "parse_mode": "HTML",
            "reply_markup": admin_contact_keyboard(),
        })
        return True
    if command == "/mywarnings":
        count = warning_count(chat_id, user_id)
        send_simple_notice(chat_id, message_id, f"⚠️ عدد مخالفاتك الحالية: <b>{count}</b> من 3")
        return True
    if command == "/report":
        replied = msg.get("reply_to_message") or {}
        if not replied:
            send_simple_notice(chat_id, message_id, "استخدم /report بالرد على الرسالة المشبوهة.")
            return True
        reported_user = replied.get("from") or {}
        report_text = get_text(replied)[:800] or "[رسالة بدون نص]"
        reporter = sender_display_name(user)
        reported = sender_display_name(reported_user)
        notice = (
            "🚨 <b>بلاغ جديد للأدمن</b>\n"
            f"المبلّغ: {reporter}\n"
            f"عن: {reported}\n"
            f"المحتوى: <code>{report_text}</code>"
        )
        send_simple_notice(chat_id, message_id, notice)
        return True
    if command in ("/mod", "/panel"):
        if not is_admin:
            return True
        target_user, target_id, target_message_id = replied_target(msg)
        if not target_id:
            send_simple_notice(chat_id, message_id, "استخدم الأمر بالرد على رسالة العضو: <code>/mod</code>")
            return True
        allowed, reason = target_can_be_moderated(chat_id, target_id)
        if not allowed:
            send_simple_notice(chat_id, message_id, reason)
            return True

        panel_text = (
            "👮 <b>لوحة إدارة خاصة</b>\n\n"
            f"المجموعة: <b>{chat.get('title') or 'الجروب'}</b>\n"
            f"العضو: <b>{sender_display_name(target_user)}</b>\n"
            f"الإنذارات الحالية: <b>{warning_count(chat_id, target_id)}</b> من 3\n\n"
            "اختر الإجراء المطلوب:"
        )
        private_result = tg_api("sendMessage", {
            "chat_id": user_id,
            "text": panel_text,
            "parse_mode": "HTML",
            "reply_markup": moderation_panel_keyboard(
                chat_id,
                target_id,
                target_message_id,
                telegram_message_url(chat, target_message_id),
            ),
        })

        delete_message(chat_id, message_id)
        if not private_result.get("ok"):
            start_url = bot_private_url()
            payload = {
                "chat_id": chat_id,
                "text": "⚠️ افتح خاص البوت واضغط <b>Start</b> مرة واحدة، وبعدها جرّب <code>/mod</code> تاني.",
                "parse_mode": "HTML",
            }
            if start_url:
                payload["reply_markup"] = {"inline_keyboard": [[{"text": "🤖 فتح خاص البوت", "url": start_url}]]}
            tg_api("sendMessage", payload)
        return True

    if command in ("/warn", "/mute", "/unmute", "/ban", "/unban", "/resetwarn", "/del"):
        if not is_admin:
            return True
        target_user, target_id, target_message_id = replied_target(msg)
        if not target_id:
            send_simple_notice(chat_id, message_id, f"استخدم <code>{command}</code> بالرد على رسالة العضو.")
            return True
        allowed, reason = target_can_be_moderated(chat_id, target_id)
        if not allowed and command not in ("/unban",):
            send_simple_notice(chat_id, message_id, reason)
            return True

        parts = text.split()
        target_name = sender_display_name(target_user)

        if command == "/warn":
            reason_text = " ".join(parts[1:]).strip() or "إنذار يدوي من الأدمن"
            add_violation(chat_id, target_id, reason_text, target_message_id)
            delete_message(chat_id, message_id)
            return True

        if command == "/mute":
            minutes = DEFAULT_MUTE_MINUTES
            if len(parts) > 1 and parts[1].isdigit():
                minutes = max(1, min(10080, int(parts[1])))
            until_date = int(time.time()) + minutes * 60
            set_member_restricted(chat_id, target_id, True, until_date)
            admin_action_notice(chat_id, target_message_id, f"🔇 تم كتم <b>{target_name}</b> لمدة {minutes} دقيقة.")
            delete_message(chat_id, message_id)
            return True

        if command == "/unmute":
            set_member_restricted(chat_id, target_id, False)
            admin_action_notice(chat_id, target_message_id, f"✅ تم فك الكتم عن <b>{target_name}</b>.")
            delete_message(chat_id, message_id)
            return True

        if command == "/ban":
            reason_text = " ".join(parts[1:]).strip() or "قرار مباشر من الأدمن"
            tg_api("banChatMember", {"chat_id": chat_id, "user_id": target_id})
            admin_action_notice(chat_id, target_message_id, f"🚫 تم حظر <b>{target_name}</b>.\nالسبب: <b>{reason_text}</b>")
            delete_message(chat_id, message_id)
            return True

        if command == "/unban":
            tg_api("unbanChatMember", {"chat_id": chat_id, "user_id": target_id, "only_if_banned": True})
            admin_action_notice(chat_id, target_message_id, f"✅ تم فك الحظر عن <b>{target_name}</b>.")
            delete_message(chat_id, message_id)
            return True

        if command == "/resetwarn":
            user_warnings[get_warning_key(chat_id, target_id)] = 0
            admin_action_notice(chat_id, target_message_id, f"♻️ تم تصفير إنذارات <b>{target_name}</b>.")
            delete_message(chat_id, message_id)
            return True

        if command == "/del":
            delete_message(chat_id, target_message_id)
            delete_message(chat_id, message_id)
            return True

    if command == "/slow" and is_admin:
        parts = text.split()
        seconds = 30
        if len(parts) > 1 and parts[1].isdigit():
            seconds = max(5, min(3600, int(parts[1])))
        slow_mode_seconds[chat_id] = seconds
        send_simple_notice(chat_id, message_id, f"🐢 تم تفعيل الوضع البطيء: رسالة كل {seconds} ثانية لكل عضو.")
        return True
    if command == "/normal" and is_admin:
        slow_mode_seconds.pop(chat_id, None)
        send_simple_notice(chat_id, message_id, "✅ تم إلغاء الوضع البطيء.")
        return True
    if command == "/lock" and is_admin:
        locked_chats.add(chat_id)
        tg_api("setChatPermissions", {"chat_id": chat_id, "permissions": {"can_send_messages": False}})
        send_simple_notice(chat_id, message_id, "🔧 الجروب مقفول مؤقتًا للصيانة.")
        return True
    if command == "/unlock" and is_admin:
        locked_chats.discard(chat_id)
        tg_api("setChatPermissions", {"chat_id": chat_id, "permissions": {
            "can_send_messages": True, "can_send_photos": True, "can_send_videos": True,
            "can_send_audios": True, "can_send_documents": True, "can_send_voice_notes": True,
            "can_send_video_notes": True, "can_send_polls": True, "can_send_other_messages": True,
            "can_add_web_page_previews": True, "can_invite_users": True
        }})
        send_simple_notice(chat_id, message_id, "✅ تم فتح الجروب.")
        return True
    return False


def check_custom_slow_mode(chat_id, user_id):
    seconds = slow_mode_seconds.get(chat_id)
    if not seconds:
        return False
    key = f"{chat_id}:{user_id}"
    now = int(time.time())
    previous = last_group_message.get(key, 0)
    if now - previous < seconds:
        return True
    last_group_message[key] = now
    return False

def handle_callback_query(query):
    callback_id = query.get("id")
    user = query.get("from") or {}
    message = query.get("message") or {}
    data = query.get("data") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    clicker_id = user.get("id")

    if data.startswith("rules:"):
        try:
            target_id = int(data.split(":", 1)[1])
        except Exception:
            target_id = 0
        if clicker_id != target_id:
            tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "الزر مخصص للعضو الجديد فقط", "show_alert": True})
            return
        accepted_rules.add(f"{chat_id}:{clicker_id}")
        set_member_restricted(chat_id, clicker_id, False)
        tg_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message.get("message_id"),
            "text": f"✅ أهلًا <b>{sender_display_name(user)}</b>، تم قبول القوانين ويمكنك المشاركة الآن.",
            "parse_mode": "HTML",
        })
        tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "تم تفعيل مشاركتك ✅"})
        return

    if data.startswith("pmod:"):
        if not callback_id or not clicker_id:
            return
        try:
            _, action, group_chat_id_raw, target_id_raw, target_message_id_raw = data.split(":", 4)
            group_chat_id = int(group_chat_id_raw)
            target_id = int(target_id_raw)
            target_message_id = int(target_message_id_raw)
        except Exception:
            tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "بيانات الإجراء غير صحيحة"})
            return

        if not user_is_admin(group_chat_id, clicker_id):
            tg_api("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "لوحة الإدارة للأدمن فقط",
                "show_alert": True,
            })
            return

        allowed, reason = target_can_be_moderated(group_chat_id, target_id)
        if not allowed and action not in ("u", "r"):
            tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": reason, "show_alert": True})
            return

        if action == "w":
            add_violation(group_chat_id, target_id, "إنذار يدوي من الأدمن", target_message_id)
            result_text = "⚠️ تم إعطاء العضو إنذارًا"
        elif action == "m":
            until_date = int(time.time()) + DEFAULT_MUTE_MINUTES * 60
            set_member_restricted(group_chat_id, target_id, True, until_date)
            admin_action_notice(group_chat_id, target_message_id, f"🔇 تم كتم العضو لمدة {DEFAULT_MUTE_MINUTES} دقائق.")
            result_text = f"🔇 تم الكتم {DEFAULT_MUTE_MINUTES} دقائق"
        elif action == "b":
            tg_api("banChatMember", {"chat_id": group_chat_id, "user_id": target_id})
            admin_action_notice(group_chat_id, target_message_id, "🚫 تم حظر العضو فورًا بواسطة الأدمن.")
            result_text = "🚫 تم حظر العضو"
        elif action == "d":
            delete_message(group_chat_id, target_message_id)
            result_text = "🗑 تم حذف الرسالة"
        elif action == "u":
            set_member_restricted(group_chat_id, target_id, False)
            result_text = "✅ تم فك الكتم"
        elif action == "r":
            user_warnings[get_warning_key(group_chat_id, target_id)] = 0
            result_text = "♻️ تم تصفير الإنذارات"
        else:
            tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "إجراء غير معروف"})
            return

        tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": result_text})
        tg_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message.get("message_id"),
            "text": f"{result_text} ✅\nنفّذه: <b>{sender_display_name(user)}</b>",
            "parse_mode": "HTML",
        })
        return

    if not callback_id or not data.startswith("used:"):
        return
    try:
        _, owner_id_raw, code = data.split(":", 2)
        owner_id = int(owner_id_raw)
    except Exception:
        tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "بيانات الزر غير صحيحة"})
        return

    is_admin = bool(chat_id and clicker_id and user_is_admin(chat_id, clicker_id))
    if clicker_id != owner_id and not is_admin:
        tg_api("answerCallbackQuery", {
            "callback_query_id": callback_id,
            "text": "الزر لصاحب البطاقة أو الأدمن فقط",
            "show_alert": True,
        })
        return

    used_by = sender_display_name(user)
    new_text = (
        "🔴 <b>تم استخدام رمز الاستبدال</b>\n\n"
        f"🎟 <code>{code}</code>\n"
        f"✅ أكده: <b>{used_by}</b>"
    )
    tg_api("editMessageText", {
        "chat_id": chat_id,
        "message_id": message.get("message_id"),
        "text": new_text,
        "parse_mode": "HTML",
    })
    stats["marked_used"] += 1
    tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "تم تعليم الكود كمستخدم ✅"})

def handle_message(msg):
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}

    if chat.get("type") == "private":
        text = (msg.get("text") or "").strip().lower()
        if text.startswith("/start"):
            tg_api("sendMessage", {
                "chat_id": chat.get("id"),
                "text": (
                    "✅ <b>تم تفعيل لوحة الإدارة الخاصة</b>\n\n"
                    "ارجع للجروب، واعمل رد على رسالة العضو، واكتب <code>/mod</code>.\n"
                    "هتوصلك أزرار الإنذار والكتم والحظر هنا في الخاص فقط."
                ),
                "parse_mode": "HTML",
            })
        return

    if not is_group(chat):
        return

    # منشور القناة المرتبطة الخاص بالتعليقات
    if msg.get("is_automatic_forward") is True:
        return

    if ENABLE_GROUP_TOOLS and msg.get("new_chat_members"):
        handle_new_members(msg)
        return
    if ENABLE_GROUP_TOOLS and handle_service_message(msg):
        return

    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    user_id = user.get("id")

    if not chat_id or not message_id or not user_id:
        return

    is_admin = user_is_admin(chat_id, user_id)

    clean_old_memory()

    if ENABLE_GROUP_TOOLS and handle_group_command(msg, is_admin):
        return

    if ENABLE_GROUP_TOOLS and not is_admin and check_custom_slow_mode(chat_id, user_id):
        delete_message(chat_id, message_id)
        send_auto_delete_message(chat_id, "🐢 الوضع البطيء مفعّل؛ استنى شوية قبل الرسالة التالية.", None, WARNING_DELETE_SECONDS)
        return

    if (msg.get("text") or "").strip().lower() == "/stats":
        if not is_admin:
            return
        send_simple_notice(chat_id, message_id, (
            "📊 <b>إحصائيات البوت منذ آخر تشغيل</b>\n\n"
            f"✅ بطاقات مقبولة: {stats['accepted']}\n"
            f"♻️ أكواد مكررة: {stats['duplicate']}\n"
            f"⌛ أكواد منتهية: {stats['expired']}\n"
            f"❌ فشل قراءة: {stats['ocr_failed']}\n"
            f"🔴 تم الاستبدال: {stats['marked_used']}"
        ))
        return

    if ENABLE_GROUP_TOOLS and not is_admin:
        raw_text = get_text(msg)
        if SEVERE_CREDENTIAL_RE.search(raw_text):
            delete_message(chat_id, message_id)
            add_violation(chat_id, user_id, "طلب باسورد أو كود تحقق", message_id, severe=True)
            return
        if CREDENTIAL_RE.search(raw_text):
            delete_message(chat_id, message_id)
            add_violation(chat_id, user_id, "ممنوع طلب بيانات الحساب أو الهاتف", message_id)
            return
        if SALE_RE.search(raw_text):
            delete_message(chat_id, message_id)
            add_violation(chat_id, user_id, "ممنوع البيع والشراء أو التحويلات المالية", message_id)
            return
        if FAQ_EXCHANGE_RE.search(raw_text):
            send_auto_delete_message(chat_id, "🔄 طريقة التبادل: ارفع صورة البطاقة بوضوح، واتفق مع الطرف الآخر داخل الجروب بدون إرسال بيانات الحساب.", message_id, WARNING_DELETE_SECONDS)
        elif FAQ_CODE_RE.search(raw_text):
            send_auto_delete_message(chat_id, "🎟️ رمز الاستبدال يوضع داخل صفحة الاسترداد الرسمية في اللعبة/الفعالية. لا ترسل بيانات حسابك لأي شخص.", message_id, WARNING_DELETE_SECONDS)

    if not is_admin and is_flood(user_id):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "ممنوع السبام والرسائل الكتير ورا بعض", message_id)
        return

    if not is_admin and is_forwarded(msg):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "ممنوع الرسائل المعاد توجيهها", message_id)
        return

    forbidden_media = msg.get("video") or msg.get("animation") or msg.get("document") or msg.get("audio") or msg.get("voice") or msg.get("video_note") or msg.get("sticker")
    if not is_admin and forbidden_media:
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "المسموح من الميديا هو الصور فقط", message_id)
        return

    if not is_admin and is_photo_flood(user_id, msg):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "ممنوع إرسال صور كتير بسرعة", message_id)
        return

    if not is_admin and message_has_link(msg):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "ممنوع نشر روابط", message_id)
        return

    if not is_admin and message_has_bad_word(msg):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "ممنوع الشتيمة", message_id)
        return

    text = get_text(msg)
    if not is_admin and is_repeated_text(chat_id, user_id, text):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "ممنوع تكرار نفس الرسالة", message_id)
        return

    if not is_admin and is_repeated_photo(msg):
        delete_message(chat_id, message_id)
        add_violation(chat_id, user_id, "الصورة دي اتبعت قبل كده", message_id)
        return

    # الصور: جرّب OCR من الصورة أولًا، ثم الكابشن كحل احتياطي
    if msg.get("photo"):
        info = None
        if OCR_FROM_IMAGE:
            info = parse_card_info_from_photo(msg, user)
        if not info:
            info = parse_card_info_from_caption(msg, user)
        if info:
            code = info.get("code")
            expiry_at = info.get("expiry_at")
            if expiry_at and expiry_at <= cairo_now():
                stats["expired"] += 1
                delete_message(chat_id, message_id)
                send_simple_notice(chat_id, message_id, "❌ الكود منتهي الصلاحية.")
                return
            if code in seen_codes:
                stats["duplicate"] += 1
                delete_message(chat_id, message_id)
                send_simple_notice(chat_id, message_id, "♻️ رمز الاستبدال ده اتنشر قبل كده.")
                return
            seen_codes[code] = {"ts": int(time.time()), "user_id": user_id}
            stats["accepted"] += 1
            send_card_summary(chat_id, message_id, info, user_id)
            return
        if REQUIRE_PHOTO_TEMPLATE or OCR_FROM_IMAGE:
            stats["ocr_failed"] += 1
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
    payload = {"url": webhook_url, "allowed_updates": ["message", "edited_message", "callback_query"], "drop_pending_updates": True}
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
            "message": "Fr3oon Helper Bot V20 private admin panel is running",
            "rules": "V11 stable card OCR + private admin moderation panel + contact button + group tools",
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
        callback_query = update.get("callback_query")
        if callback_query:
            handle_callback_query(callback_query)
        else:
            msg = update.get("message") or update.get("edited_message")
            if msg:
                handle_message(msg)
        self._send_json(200, {"ok": True})
