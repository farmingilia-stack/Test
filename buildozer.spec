[app]
title = Arbitrage Tracker
package.name = arbtracker
package.domain = com.parcian
source.dir = .
source.exclude_patterns = bin/*, .github/*, __pycache__/*, *.md

version = 0.2.0
requirements = python3, kivy==2.3.0, requests, certifi, idna, chardet, urllib3
orientation = portrait
fullscreen = 0

# مهم‌ها برای سازگاری با اکشن‌های گیت‌هاب
android.api = 34
android.minapi = 24
android.build_tools_version = 34.0.0

# معماری‌ها (دو تا کافی‌ان و سایز APK هم معقول می‌مونه)
android.archs = arm64-v8a, armeabi-v7a

# دسترسی‌های لازم
android.permissions = INTERNET, ACCESS_NETWORK_STATE

# لاگ کمتر/بیشتر
log_level = 2

# (اختیاری) اگر اسپلش‌اسکرین داری، مسیرش را بده
# presplash.filename = assets/presplash.png

# اگر آیکون اختصاصی داری، فعال کن
# icon.filename = assets/icon.png


[buildozer]
log_level = 2
warn_on_root = 1
build_dir = .buildozer
