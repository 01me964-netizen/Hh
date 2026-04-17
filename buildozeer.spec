[app]

title = My Application
package.name = devmit
package.domain = com.devanshpatel
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
#android.add_src = AdmobBridge.java
# ── FIXED: removed opencv-python-headless, removed duplicate kivymd ──
requirements = python3,kivy,kivymd,pyjnius,opencv,pillow,requests,camera4kivy,gestures4kivy,hostpython3

orientation = portrait
fullscreen = 0

# ── FIXED: uncommented and set correct API levels ──
android.api = 33
android.minapi = 21
android.enable_multidex = True
android.manifest.application_attribs = android:usesCleartextTraffic="true"
# ── FIXED: Added all required permissions ──
android.permissions = CAMERA,RECORD_AUDIO,INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

android.archs = arm64-v8a, armeabi-v7a
p4a.hook = camerax_provider/gradle_options.py
# Add this line in your buildozer.spec

# ── FIXED: Enable androidx (needed for modern camera APIs) ──
android.enable_androidx = True

osx.python_version = 3
osx.kivy_version = 1.9.1

ios.kivy_ios_url = https://github.com/kivy/kivy-ios
ios.kivy_ios_branch = master
ios.ios_deploy_url = https://github.com/phonegap/ios-deploy
ios.ios_deploy_branch = 1.10.0
ios.codesign.allowed = false

android.gradle_dependencies = com.google.android.gms:play-services-ads:19.3.0

android.meta_data = com.google.android.gms.ads.APPLICATION_ID=ca-app-pub-3940256099942544~3347511713
[buildozer]
log_level = 2
warn_on_root = 1