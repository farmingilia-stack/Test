[app]
title = ArbTracker
package.name = arbtracker
package.domain = com.user
version = 0.1

source.dir = .
source.include_exts = py,kv,png,jpg,txt,ini
requirements = python3,kivy==2.2.1,requests,certifi,charset-normalizer,idna,urllib3

orientation = portrait
fullscreen = 0
android.permissions = INTERNET

[android]
# API هدف و کمینه
android.api = 33
android.minapi = 24

# بسیار مهم: همین نسخه Build-Tools را استفاده کن
android.build_tools = 33.0.2

# بیلدوزر را مجبور کن از SDK/NDK بیرونی استفاده کند (مسیرها را با build.yml ست می‌کنیم)
android.sdk_path = /usr/local/lib/android/sdk
android.ndk_path = /usr/local/lib/android/ndk

# پذیرش خودکار لایسنس‌ها (ویژگی جدید بیلدوزر)
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
