# Fr3oon Helper Bot - Vercel V4

القواعد الحالية:

- الكلام مسموح
- الصور مسموحة
- الروابط ممنوعة
- الشتايم ممنوعة
- السبام ممنوع
- تكرار نفس الكلام ممنوع
- تكرار نفس ملف الصورة ممنوع قدر الإمكان
- الأدمنز مسموح لهم بكل حاجة

## ملفات المشروع

```text
api/index.py
pyproject.toml
.env.example
.gitignore
README.md
```

## Environment Variables

```text
BOT_TOKEN=توكن البوت الجديد
WEBHOOK_URL=https://your-project.vercel.app/api/bot
WEBHOOK_SECRET=fr3oon-secret-2026
SEND_WARNINGS=false
FLOOD_LIMIT=5
FLOOD_SECONDS=10
REPEAT_SECONDS=60
```

بعد التعديل اعمل Redeploy.
لو غيرت الدومين أو أول مرة تشغل، افتح:

```text
https://your-project.vercel.app/api/set_webhook
```
