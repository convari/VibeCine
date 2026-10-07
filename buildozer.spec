[app]
title = VibeCine
package.name = vibecine
package.domain = app.vibecine
version = 2.0.0

# p4a exige main.py na raiz (shim criado propositalmente — ver main.py).
source.dir = .
source.include_exts = py,png,jpg,kv,txt,md,json,ttf,otf
# NUNCA empacotar diretórios de dev/build/Windows (tamanho e segurança).
source.exclude_dirs = tests, bin, .venv, .buildozer, dist, release, build, docs, .git, .github, app/ui, __pycache__, vibcine_backup_fase2, .pytest_cache, data

# Somente bibliotecas Python puras ou com recipe p4a.
# p4a NÃO resolve dependências automaticamente — todas listadas aqui:
# - kivy/kivymd(UI) + pillow/asynckivy (deps do KivyMD 2.0)
# - yt-dlp (como biblioteca; sem deps obrigatórias)
# - qrcode[pil] já vem com pillow; certifi garante HTTPS
# - plyer = acesso a intents/notificações
# SEM executáveis Windows no APK.
requirements = python3,kivy==2.3.1,kivymd==2.0.0,asynckivy,pillow,qrcode,yt-dlp,plyer,certifi

orientation = portrait
fullscreen = 0
android.allow_backup = True
icon.filename = app/ui/resources/vibcine.png
presplash.filename = app/ui/resources/vibcine.png
presplash.color = #0A0A0C

# MVP: downloads ativos enquanto o app está aberto. Serviço foreground
# está planejado para a próxima iteração (ver docs/ANDROID.md).

android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, POST_NOTIFICATIONS, FOREGROUND_SERVICE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# [buildozer]
log_level = 2

# Versão das build-tools a ser usada (compatível com android.api = 34)
android.build_tools_version = 34.0.0

# Caminho do SDK Android (configurado no CI via ANDROID_SDK_ROOT)
# Não definimos android.accept_sdk_license aqui - o CI aceita as licenças manualmente
