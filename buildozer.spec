[app]
# --- App metadata ---
title = ArbTracker
package.name = arbtracker
package.domain = com.user
version = 0.1
# سورس همین پوشه
source.dir = .
source.include_exts = py,kv,png,jpg,txt,ini
# اجرای اصلی
# (main.py در ریشه ریپو هست)
# اگر اسم فایل رو عوض کردی، این رو هم اصلاح کن.
# main.py به‌صورت پیش‌فرض شناخته می‌شود.

# --- Python/Kivy requirements ---
# لطفاً همین نسخه‌ها را نگه دار تا بیلد پایدار باشد
requirements = python3,kivy==2.2.1,requests,certifi,charset-normalizer,idna,urllib3

# --- UI ---
orientation = portrait
fullscreen = 0

# --- Permissions ---
android.permissions = INTERNET

# --------------------------------
# بخش‌های زیر برای اندروید مهم‌اند
# --------------------------------
[android]
# API هدف (سازگار با Play-policy فعلاً 33)
android.api = 33
# کمینه API (اندروید 7.0)
android.minapi = 24
# مهم: Build-Tools را پین می‌کنیم تا مشکل لایسنس/aidl ندهد
android.build_tools = 33.0.2

# (اختیاری) نام پکیج جاوا – اگر خالی بماند از package.domain+package.name می‌سازد
# package = com.user.arbtracker

# NDK/SDK را خود Buildozer می‌گیرد؛ نیازی به مقداردهی دستی نیست

# اگر فونت فارسی نیاز شد، می‌توانی از assets استفاده کنی:
# presplash.filename = %(source.dir)s/assets/presplash.png
# icon.filename = %(source.dir)s/assets/icon.png

# برای بیلد دیباگ کافیست؛ برای ریلیز بعداً keystore اضافه می‌کنیم.
# (بعداً اگر خواستی آپلود به استور، این‌ها را تنظیم می‌کنیم.)

# --------------------------------
# سایر بخش‌ها (به حالت پیش‌فرض)
# --------------------------------
[buildozer]
log_level = 2
warn_on_root = 1

# اگر نیاز به محیط‌های خاص داشتی، این‌ها را فعال کن:
# requirements.source.kivy = https://github.com/kivy/kivy/archive/2.2.1.zip
# (فعلاً لازم نیست)
