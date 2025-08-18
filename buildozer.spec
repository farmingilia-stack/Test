[app]
# --- اپ ---
title = ArbTracker
package.name = arbtracker
package.domain = com.yourcompany  # ← در صورت نیاز تغییر بده
version = 1.0.0

# فایل‌های پروژه
source.dir = .
source.include_exts = py,kv,png,jpg,ico,xml,txt,md

# ظاهر و رفتار
orientation = portrait
fullscreen = 0
log_level = 2
# اگر کی‌بورد روی بعضی دستگاه‌ها مزاحم شد، این را فعال کن:
# android.windowSoftInputMode = adjustPan

# نیازمندی‌ها (کاملاً کافی برای کدی که دادم)
requirements = python3,kivy==2.2.1,requests,pyaes,certifi,charset-normalizer,idna,urllib3

# فایل اجرا
# (main.py باید در ریشه‌ی ریپو باشد)
entrypoint = main.py

# آیکن/اسپلش (اختیاری)
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png
# android.presplash_color = #101010

# اجازه‌ها
android.permissions = INTERNET

# --- اندروید/بیلد ---
# API و ABIها
android.api = 34          # Android 14
android.minapi = 24       # Android 7.0 به بالا
android.archs = arm64-v8a, armeabi-v7a

# جاوا/گرادل (پیش‌فرض‌های Buildozer کافی‌اند؛ نیازی به تغییر نیست)
# android.ndk = 25b
# android.sdk = 27
# android.gradle_dependencies =
# android.gradle_arguments =

# امضای دیباگ خودکار انجام می‌شود؛ برای ریلیز می‌تونی keystore تعریف کنی:
# android.release_keystore = %(source.dir)s/keystore.jks
# android.release_keystore_pass = yourpass
# android.release_keyalias = youralias
# android.release_keyalias_pass = yourpass

# کاهش حجم لاگ‌ها روی دستگاه
# android.logcat_filters = *:S python:D ActivityManager:I WindowManager:I

# اگر نیاز به پروکسی/گواهی خاص داری:
# android.add_src = %(source.dir)s/android_src

# ---------------------
# بخش‌های پیش‌فرض/اختیاری buildozer (دست نزن مگر لازم شد)
# ---------------------
# garden_requirements =
# p4a.branch = master
# p4a.local_recipes = ./recipes
# android.enable_androidx = True
# android.allow_backup = False
# android.support_version = 28.0.0
# (… سایر گزینه‌ها در صورت نیاز)
