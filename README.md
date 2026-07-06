# Fr3oon Helper Bot - Vercel V3

ارفع الملفات على GitHub ثم اعمل Redeploy في Vercel.

مهم: في النسخة دي مفيش requirements.txt، الاعتمادات جوه pyproject.toml.

Environment Variables:
- BOT_TOKEN
- WEBHOOK_URL = https://your-project.vercel.app/api/bot
- WEBHOOK_SECRET = اي كلمة سرية
- SEND_WARNINGS = false

بعد Deploy افتح:
https://your-project.vercel.app/api/set_webhook
