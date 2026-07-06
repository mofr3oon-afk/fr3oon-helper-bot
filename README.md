# Fr3oon Helper Bot - Vercel V5

الإضافات الجديدة:
- قاموس شتايم أقوى بالعربي والمصري وArabizi والإنجليزي
- منع سبام الصور
- منع أي رسالة Forward
- الكلام والصور العادية مسموحة
- الروابط والسبام وتكرار الرسائل ممنوعة
- الأدمنز مستثنون من الفلترة

## التحكم في سبام الصور من Vercel

```text
PHOTO_FLOOD_LIMIT=4
PHOTO_FLOOD_SECONDS=10
```

يعني أكثر من 4 صور خلال 10 ثواني يعتبر سبام.

## Environment Variables

```text
BOT_TOKEN
WEBHOOK_URL
WEBHOOK_SECRET
SEND_WARNINGS=false
FLOOD_LIMIT=5
FLOOD_SECONDS=10
REPEAT_SECONDS=60
PHOTO_FLOOD_LIMIT=4
PHOTO_FLOOD_SECONDS=10
```

ارفع الملفات واعمل Redeploy. نفس الـ webhook الحالي يفضل شغال طالما الدومين والمسار لم يتغيرا.
