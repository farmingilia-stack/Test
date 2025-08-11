[app]
title = ArbTracker
package.name = arbtracker
package.domain = com.user
source.dir = .
source.include_exts = py,kv,png,jpg,txt,ini
version = 0.1
requirements = python3,kivy==2.2.1,requests,certifi,charset-normalizer,idna,urllib3
orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

[android]
android.api = 33
android.minapi = 24
android.permissions = INTERNET
