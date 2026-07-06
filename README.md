# Fr3oon Helper Bot - Vercel Version

نسخة Vercel المجانية من بوت فرعون المساعد.

## البوت بيعمل ايه؟

- يمسح اي رسالة فيها لينك
- يمسح اي رسالة مش صورة
- يسمح بصور بطاقات ببجي فقط
- يسيب الادمنز عادي
- يمنع تكرار نفس ملف الصورة قدر الإمكان

ملاحظة مهمة:
منع تكرار الصور على Vercel مؤقت ومش مضمون 100٪، لأن Vercel مش بيحفظ ملف دائم.
لو عايز منع تكرار قوي بعدين نضيف Supabase.

## الملفات

```text
api/
  bot.py
  set_webhook.py
  delete_webhook.py
requirements.txt
.env.example
README.md
```

## خطوات التشغيل على Vercel

1. ارفع الملفات دي على GitHub.
2. ادخل Vercel واعمل Import للـ repo.
3. في Environment Variables ضيف:

```text
BOT_TOKEN
```

وحط التوكن الجديد من BotFather.

4. ضيف كمان:

```text
WEBHOOK_SECRET
```

واكتب اي كلمة سرية انجليزي بدون مسافات، مثال:

```text
fr3oon-secret-2026
```

5. بعد ما تعمل Deploy، هتعرف رابط مشروعك مثل:

```text
https://your-project.vercel.app
```

6. ارجع Environment Variables وضيف:

```text
WEBHOOK_URL
```

بالشكل ده:

```text
https://your-project.vercel.app/api/bot
```

7. اعمل Redeploy من Vercel.

8. افتح الرابط ده في المتصفح:

```text
https://your-project.vercel.app/api/set_webhook
```

لو ظهر لك:

```json
"ok": true
```

يبقى البوت اتربط بتليجرام.

## مهم في تليجرام

البوت لازم يكون Admin في الجروب ومعاه صلاحية:

```text
Delete messages
```

ومن BotFather خلي Privacy:

```text
Disable
```

## الاختبار

- ابعت رسالة نص في الجروب: المفروض تتحذف.
- ابعت لينك: المفروض يتحذف.
- ابعت صورة: المفروض تفضل.
