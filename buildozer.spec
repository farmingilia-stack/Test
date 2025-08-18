[app]
title = Arbitrage Tracker
package.name = arbtracker
package.domain = com.yourorg
version = 0.5.0
# ورود برنامه از main.py در ریشه ریپو
source.dir = .
source.main = main.py
source.include_exts = py,kv,png,jpg,ttf,json
requirements = python3,kivy,requests,ccxt,urllib3,certifi,idna,chardet
orientation = portrait
fullscreen = 0
log_level = 2
# دسترسی‌های شبکه
android.permissions = INTERNET, WAKE_LOCK
# آیکون و اسپلش اگر داری اضافه کن (اختیاری)
# icon.filename = assets/icon.png
# presplash.filename = assets/presplash.png

[buildozer]
warn_on_root = 0

# پین کردن API/NDK که با SDK نصب‌شده در workflow جور است
android.api = 34
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# شاخه python-for-android
p4a.branch = master

# برای کاهش حجم لاگ در بیلد‌های بعدی اگر خواستی:
# builddir = .buildozer
