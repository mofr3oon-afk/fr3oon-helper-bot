import os
import re
import json
import time
import asyncio
import logging
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Koyeb Environment Variables.")

SEEN_FILE = Path("seen_photos.json")

# مدة حفظ تكرار الصور: 3 أيام
KEEP_SECONDS = 3 * 24 * 60 * 60

LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|bit\.ly|tinyurl\.com|wa\.me/|whatsapp\.com|discord\.gg|fb\.com|facebook\.com|instagram\.com|youtube\.com|youtu\.be)",
    re.IGNORECASE
)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Fr3oon Helper Bot is running")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info(f"Health server running on port {port}")
    server.serve_forever()


def load_seen():
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_seen(data):
    SEEN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


seen_photos = load_seen()


def message_has_link(msg):
    text = f"{msg.text or ''}\n{msg.caption or ''}"

    if LINK_RE.search(text):
        return True

    entities = []
    if msg.entities:
        entities += msg.entities
    if msg.caption_entities:
        entities += msg.caption_entities

    for ent in entities:
        if ent.type in ("url", "text_link"):
            return True

    return False


async def user_is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id
        )
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def delete_and_warn(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str):
    msg = update.effective_message

    try:
        await msg.delete()
    except Exception as e:
        logging.warning(f"Delete failed: {e}")

    try:
        warning = await context.bot.send_message(
            chat_id=msg.chat_id,
            text=(
                "تم حذف الرسالة ❌\n\n"
                f"{reason}\n\n"
                "المسموح هنا: صور بطاقات ببجي فقط ✅\n"
                "ممنوع الروابط او الكلام العشوائي"
            )
        )
        await asyncio.sleep(6)
        await warning.delete()
    except Exception as e:
        logging.warning(f"Warning failed: {e}")


async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if not msg or not update.effective_chat:
        return

    # اشتغل في الجروبات فقط
    if update.effective_chat.type not in ("group", "supergroup"):
        return

    if not update.effective_user:
        return

    # سيب الادمنز عادي
    if await user_is_admin(update, context):
        return

    now = int(time.time())

    # تنظيف الصور القديمة من الذاكرة
    old_keys = [
        key for key, ts in seen_photos.items()
        if now - ts > KEEP_SECONDS
    ]
    for key in old_keys:
        del seen_photos[key]

    # منع الروابط في النص او الكابشن
    if message_has_link(msg):
        save_seen(seen_photos)
        return await delete_and_warn(update, context, "ممنوع نشر روابط في الجروب")

    # السماح بالصور فقط
    if not msg.photo:
        save_seen(seen_photos)
        return await delete_and_warn(update, context, "الجروب مخصص لصور بطاقات ببجي فقط")

    # منع نفس الصورة لو اتبعت قبل كده
    photo_unique_id = msg.photo[-1].file_unique_id

    if photo_unique_id in seen_photos:
        save_seen(seen_photos)
        return await delete_and_warn(update, context, "الصورة دي اتبعت قبل كده")

    seen_photos[photo_unique_id] = now
    save_seen(seen_photos)


def main():
    # سيرفر بسيط عشان Koyeb يعرف إن الخدمة شغالة
    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, moderate))

    logging.info("Fr3oon Helper Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
