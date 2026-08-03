# Fr3oon Helper Bot V9 - Accurate OCR

التحديث الجديد:
- يرسل الصورة كاملة إلى OCR.Space.
- يرسل قصتين مكبرتين من مكان رمز الاستبدال في صورة بطاقة ببجي.
- يجرب محركي OCR.Space 1 و2 على سطر الكود.
- يقبل فقط كودًا رقميًا من 9 خانات، حتى لا ينشر كودًا ناقصًا أو به حروف.
- إذا لم يصل لنتيجة موثوقة، لا يكتب كودًا غلط.
- يحافظ على تعليقات القناة المرتبطة.
- يقرأ التاريخ والوقت ويحسب الانتهاء بعد 3 أيام.

المتغيرات المطلوبة:
OCR_FROM_IMAGE=true
OCR_PREFER_CLOUD=true
OCR_SPACE_API_KEY=YOUR_REAL_KEY
PHOTO_EXPIRY_DAYS=3
REQUIRE_PHOTO_TEMPLATE=false
