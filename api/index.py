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

PHOTO_REPEAT_SECONDS = 3 * 24 * 60 * 60
CAIRO_TZ = timezone(timedelta(hours=3))
CODE_MEMORY_SECONDS = 7 * 24 * 60 * 60

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


def extract_trade_details(text):
    """Extract optional offered/wanted details when the sender writes them in the caption."""
    text = (text or "").strip()
    if not text:
        return None, None
    offered = None
    wanted = None
    offered_patterns = [
        r"(?:معايا|معي|عندي|المعروض)\s*[:：=-]?\s*([^\n]{2,60})",
        r"(?:have|offering)\s*[:：=-]?\s*([^\n]{2,60})",
    ]
    wanted_patterns = [
        r"(?:عايز|محتاج|المطلوب)\s*[:：=-]?\s*([^\n]{2,60})",
        r"(?:want|need)\s*[:：=-]?\s*([^\n]{2,60})",
    ]
    for pattern in offered_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            offered = m.group(1).strip()
            break
    for pattern in wanted_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            wanted = m.group(1).strip()
            break
    return offered, wanted


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
    """Build a small set of code crops without flooding the OCR API.

    The code is orange and normally sits in the lower-middle band. We find
    the row with the strongest orange signal, then crop tightly around it.
    """
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return []

    w, h = img.size
    px = img.load()
    y_start, y_end = int(h * 0.48), int(h * 0.80)
    x_start, x_end = int(w * 0.18), int(w * 0.72)

    def is_orange(r, g, b):
        return (
            r >= 115 and 35 <= g <= 195 and b <= 145
            and r >= g + 20 and g >= b - 5
        )

    row_counts = []
    for y in range(y_start, y_end):
        count = 0
        for x in range(x_start, x_end):
            if is_orange(*px[x, y]):
                count += 1
        row_counts.append((count, y))

    best_count, best_y = max(row_counts, default=(0, int(h * 0.64)))

    # Fall back to the known PUBG card area when orange detection is weak.
    if best_count < max(8, int(w * 0.008)):
        boxes = [
            (0.30, 0.56, 0.62, 0.72),
            (0.34, 0.59, 0.57, 0.72),
        ]
    else:
        band_top = max(y_start, best_y - int(h * 0.035))
        band_bottom = min(y_end, best_y + int(h * 0.045))
        xs = []
        for y in range(band_top, band_bottom):
            for x in range(x_start, x_end):
                if is_orange(*px[x, y]):
                    xs.append(x)
        if xs:
            left = max(0, min(xs) - int(w * 0.035))
            right = min(w, max(xs) + int(w * 0.035))
            # Keep a sensible minimum width around the code.
            if right - left < int(w * 0.12):
                center = (left + right) // 2
                left = max(0, center - int(w * 0.10))
                right = min(w, center + int(w * 0.10))
            boxes = [
                (left / w, max(0, (band_top - int(h * 0.02)) / h), right / w, min(1, (band_bottom + int(h * 0.02)) / h)),
            ]
        else:
            boxes = [(0.30, 0.56, 0.62, 0.72)]

    crops = []
    for idx, box in enumerate(boxes, start=1):
        crop = img.crop((int(w * box[0]), int(h * box[1]), int(w * box[2]), int(h * box[3])))
        crop = crop.resize((max(crop.width * 8, 1), max(crop.height * 8, 1)))
        crop = ImageEnhance.Contrast(crop).enhance(1.8)
        crop = ImageEnhance.Sharpness(crop).enhance(2.5)
        crops.append((f"code-dynamic-{idx}.png", image_to_png_bytes(crop)))

        masked = Image.new("L", crop.size, 255)
        cp = crop.load()
        mp = masked.load()
        for y in range(crop.height):
            for x in range(crop.width):
                if is_orange(*cp[x, y]):
                    mp[x, y] = 0
        masked = ImageEnhance.Contrast(masked).enhance(3.0)
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
    """Read the full image only.

    PUBG exchange screenshots already contain the redemption code as the only
    standalone 9-digit number. Tight crops were the source of the recent
    failures, especially after Telegram resized the photo. Two full-image OCR
    engines are enough and are much more stable on Vercel/free OCR quotas.
    """
    texts = []

    if OCR_SPACE_API_KEY:
        for engine in ("2", "1"):
            for text in run_ocr_space(image_bytes, f"card-full-e{engine}.png", engine):
                texts.append((f"full_e{engine}", text))

    # Local OCR is only a fallback. Vercel may not have the tesseract binary,
    # so failures here are intentionally ignored.
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        gray = ImageOps.grayscale(img).resize((w * 2, h * 2))
        for psm in (6, 11):
            try:
                txt = pytesseract.image_to_string(gray, lang="eng", config=f"--psm {psm}")
                if txt and txt.strip():
                    texts.append((f"local_full_{psm}", txt.strip()))
            except Exception:
                pass
    except Exception:
        pass

    deduped = []
    seen = set()
    for source, text in texts:
        key = text.strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append((source, key))
    return deduped

def normalize_ocr_token(token):
    token = (token or "").upper().translate(ARABIC_DIGITS_MAP)
    token = re.sub(r"[^A-Z0-9\-]", "", token)
    token = token.replace("-", "")
    return token.translate(CONFUSABLE_MAP)


def extract_code_from_ocr_results(results):
    """Extract the unique standalone 9-digit redemption code from full OCR.

    Dates in these screenshots are 8 digits when separators disappear
    (YYYYMMDD), while the redemption code is 9 digits. We therefore avoid all
    crop heuristics and select the 9-digit number seen in the full OCR output.
    """
    if not results:
        return None

    counts = {}
    for source, text in results:
        raw = text.translate(ARABIC_DIGITS_MAP).upper()
        # Correct common OCR substitutions only inside alphanumeric tokens.
        for token in re.findall(r"(?<![A-Z0-9])[A-Z0-9]{9}(?![A-Z0-9])", raw):
            normalized = normalize_ocr_token(token)
            if not normalized.isdigit() or len(normalized) != 9:
                continue
            # Reject impossible date-like prefixes and obvious repeated noise.
            if normalized.startswith(("2026", "2027", "2028", "2029", "2030")):
                continue
            if len(set(normalized)) <= 2:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1

        # OCR sometimes inserts spaces or punctuation between digits.
        compact = re.sub(r"[^0-9]", "", raw)
        for match in re.finditer(r"(?<!\d)(\d{9})(?!\d)", compact):
            code = match.group(1)
            if code.startswith(("2026", "2027", "2028", "2029", "2030")):
                continue
            if len(set(code)) <= 2:
                continue
            counts[code] = counts.get(code, 0) + 1

    if not counts:
        return None

    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    best_code, best_votes = ranked[0]

    # If two different codes tie, do not guess.
    if len(ranked) > 1 and ranked[1][1] == best_votes:
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
        offered, wanted = extract_trade_details(text)
        return {
            "name": sender_display_name(user),
            "code": code,
            "issued_at": issue_dt,
            "expiry_at": issue_dt + timedelta(days=PHOTO_EXPIRY_DAYS),
            "source": "caption",
            "offered": offered,
            "wanted": wanted,
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

    offered, wanted = extract_trade_details(msg.get("caption") or "")
    return {
        "name": sender_display_name(user),
        "code": code,
        "issued_at": issue_dt,
        "expiry_at": issue_dt + timedelta(days=PHOTO_EXPIRY_DAYS),
        "source": "ocr",
        "offered": offered,
        "wanted": wanted,
    }


def build_card_text(info):
    name = info.get("name")
    code = info.get("code")
    expiry_at = info.get("expiry_at")
    offered = info.get("offered")
    wanted = info.get("wanted")

    lines = [
        "✅ <b>بطاقة متاحة</b>",
        "",
        f"👤 <b>{name}</b>",
    ]
    if offered:
        lines.append(f"🎁 معاه: <b>{offered}</b>")
    if wanted:
        lines.append(f"🔎 عايز: <b>{wanted}</b>")
    lines.extend([
        f"🎟 <code>{code}</code>",
        f"⏳ متبقي: <b>{human_remaining(expiry_at)}</b>",
    ])
    return "\n".join(lines)


def build_card_keyboard(owner_id, code):
    return {"inline_keyboard": [
        [{
            "text": "📋 نسخ الكود",
            "copy_text": {"text": code}
        }],
        [
            {
                "text": "🔄 إعادة القراءة",
                "callback_data": f"retry:{owner_id}"
            },
            {
                "text": "✅ تم الاستبدال",
                "callback_data": f"used:{owner_id}:{code}"
            }
        ]
    ]}


def send_card_summary(chat_id, reply_to_message_id, info, owner_id):
    code = info.get("code")
    return tg_api("sendMessage", {
        "chat_id": chat_id,
        "reply_to_message_id": reply_to_message_id,
        "text": build_card_text(info),
        "parse_mode": "HTML",
        "reply_markup": build_card_keyboard(owner_id, code),
    })


def send_photo_ocr_help(chat_id, reply_to_message_id=None, owner_id=None):
    text = "⚠️ معرفتش أقرأ الكود بدقة. جرّب إعادة القراءة، أو ابعت الصورة أوضح."
    payload = {"chat_id": chat_id, "text": text}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    if owner_id:
        payload["reply_markup"] = {"inline_keyboard": [[{
            "text": "🔄 إعادة القراءة",
            "callback_data": f"retry:{owner_id}"
        }]]}
    return tg_api("sendMessage", payload)


def send_simple_notice(chat_id, reply_to_message_id, text):
    return tg_api("sendMessage", {
        "chat_id": chat_id,
        "reply_to_message_id": reply_to_message_id,
        "text": text,
        "parse_mode": "HTML",
    })


def handle_callback_query(query):
    callback_id = query.get("id")
    user = query.get("from") or {}
    message = query.get("message") or {}
    data = query.get("data") or ""
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    clicker_id = user.get("id")

    if not callback_id:
        return

    if data.startswith("retry:"):
        try:
            owner_id = int(data.split(":", 1)[1])
        except Exception:
            tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "بيانات الزر غير صحيحة"})
            return

        is_admin = bool(chat_id and clicker_id and user_is_admin(chat_id, clicker_id))
        if clicker_id != owner_id and not is_admin:
            tg_api("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "إعادة القراءة لصاحب الصورة أو الأدمن فقط",
                "show_alert": True,
            })
            return

        original = message.get("reply_to_message") or {}
        if not original.get("photo"):
            tg_api("answerCallbackQuery", {
                "callback_query_id": callback_id,
                "text": "الصورة الأصلية مش متاحة لإعادة القراءة",
                "show_alert": True,
            })
            return

        owner_user = original.get("from") or user
        tg_api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "جاري إعادة القراءة…"})
        tg_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message.get("message_id"),
            "text": "🔄 جاري إعادة قراءة الصورة…",
        })

        info = parse_card_info_from_photo(original, owner_user)
        if not info:
            info = parse_card_info_from_caption(original, owner_user)
        if not info:
            tg_api("editMessageText", {
                "chat_id": chat_id,
                "message_id": message.get("message_id"),
                "text": "⚠️ لسه معرفتش أقرأ الكود بدقة. ارفع الصورة مرة تانية كاملة ومن غير قص.",
                "reply_markup": {"inline_keyboard": [[{
                    "text": "🔄 حاول مرة أخرى",
                    "callback_data": f"retry:{owner_id}"
                }]]},
            })
            return

        code = info.get("code")
        tg_api("editMessageText", {
            "chat_id": chat_id,
            "message_id": message.get("message_id"),
            "text": build_card_text(info),
            "parse_mode": "HTML",
            "reply_markup": build_card_keyboard(owner_id, code),
        })
        return

    if not data.startswith("used:"):
        tg_api("answerCallbackQuery", {"callback_query_id": callback_id})
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

    if not is_admin and is_flood(user_id):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع السبام والرسائل الكتير ورا بعض")
        return

    if not is_admin and is_forwarded(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع الرسائل المعاد توجيهها في الجروب")
        return

    forbidden_media = msg.get("video") or msg.get("animation") or msg.get("document") or msg.get("audio") or msg.get("voice") or msg.get("video_note") or msg.get("sticker")
    if not is_admin and forbidden_media:
        delete_message(chat_id, message_id)
        send_warning(chat_id, "المسموح من الميديا هو الصور فقط")
        return

    if not is_admin and is_photo_flood(user_id, msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع ارسال صور كتير بسرعة")
        return

    if not is_admin and message_has_link(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع نشر روابط في الجروب")
        return

    if not is_admin and message_has_bad_word(msg):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع الشتيمة في الجروب")
        return

    text = get_text(msg)
    if not is_admin and is_repeated_text(chat_id, user_id, text):
        delete_message(chat_id, message_id)
        send_warning(chat_id, "ممنوع تكرار نفس الرسالة")
        return

    if not is_admin and is_repeated_photo(msg):
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
            send_photo_ocr_help(chat_id, message_id, user_id)
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
            "message": "Fr3oon Helper Bot V15 full-image OCR is running",
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
        callback_query = update.get("callback_query")
        if callback_query:
            handle_callback_query(callback_query)
        else:
            msg = update.get("message") or update.get("edited_message")
            if msg:
                handle_message(msg)
        self._send_json(200, {"ok": True})
