# AGENTS.md — VibeCine Downloader Pro

## Estrutura
- `vibcine.py` — launcher da UI moderna (PySide6), instância única, `--selftest`.
- `m3u_downloader.py` — UI legada Tkinter (compatibilidade; usa o mesmo núcleo).
- `android/` — **camada Android (Kivy/KivyMD)**: `engine.py` (downloads com
  yt-dlp como biblioteca, sem executáveis), `share.py` (Intent nativa),
  `main.py` (UI mobile). Windows NÃO depende desta pasta.
- `buildozer.spec` + `.github/workflows/android-apk.yml` — build APK/AAB.
- `app/core/` — núcleo sem UI, 100% testável:
  `branding` (marca/versão/termos), `config`, `paths` (frozen/%APPDATA%),
  `m3u_parser`, `url_router`, `extractor`, `downloader` (DownloadManager),
  `history` (SQLite), `share`, `protocol` (vibcine://), `tools`,
  `tools_updater`, `app_updater`, `errors`.
- `app/ui/` — PySide6: `pages/` (library, downloads, history, settings),
  `widgets/` (toast, empty_state, share_dialog), `resources/` (ícones),
  `theme.py`, `main_window.py`, `onboarding.py`, `workers.py` (QThreads).
- `build/` — `vibcine.spec` (PyInstaller), `build.py` (build completo),
  `installer.iss` (Inno Setup), `THIRD_PARTY_LICENSES.md`, `README_BUILD.md`.
- `tests/` — unittest (rodar `python -m unittest discover -s tests`).
- `dist/VibeCine/`, `release/` — artefatos gerados (não versionar).

## Ambiente
- Python 3.13 **64-bit** obrigatório (PySide6 não tem wheel 32-bit).
- Dependências no venv do projeto: `.venv` (`pip install -r requirements.txt` +
  `pyinstaller` para build).
- Dados do usuário (config/histórico/ferramentas) em `%APPDATA%\VibeCine`
  quando empacotado; em desenvolvimento, na pasta do projeto.

## Comandos
- Testes: `.\.venv\Scripts\python.exe -m unittest discover -s tests`
- App (dev): `.\.venv\Scripts\python.exe vibcine.py`
- App Android (dev): `.\.venv\Scripts\python.exe -m android.main`
- Build+release: `.\.venv\Scripts\python.exe build\build.py`
- Versão: `APP_VERSION` em `app/core/branding.py` (fonte única).
