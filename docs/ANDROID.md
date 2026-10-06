# VibeCine para Android — Documentação

## Status
**MVP funcional.** A versão Windows **não é afetada** — toda a camada
Android vive em `android/` e reutiliza `app/core/`.

## O que já funciona (MVP)
- Abrir o app (Kivy/KivyMD, tema escuro/claro);
- Colar URL (lista M3U, YouTube, vídeo direto) e carregar;
- Biblioteca com busca, toque p/ selecionar, detalhes com QR Code e
  compartilhamento nativo do Android (sheet do sistema);
- Fila de downloads em processo via **yt-dlp como biblioteca**:
  progresso real (%, velocidade, ETA), pausa/retomada via `.part`,
  cancelamento individual/total, retry de erros transitórios;
- Histórico em SQLite (`app/core/history.py`);
- Configurações básicas (tema, organizar por grupo, formato);
- Notificação ao concluir (plyer, no Android).

## Ferramentas externas no Android — decisões técnicas
| Ferramenta | Solução |
|---|---|
| yt-dlp | **biblioteca Python** dentro do APK (sem .exe) |
| FFmpeg | **ausente no MVP** → formatos single-file; sem merge/conversão; MP3 vira áudio original (m4a/webm). Caminho futuro: `ffmpeg-kit` (AAR nativo) |
| Deno | **não existe build Android** → alguns vídeos do YouTube podem falhar com erro amigável ("exige runtime JS"). Sem gambiarras |

## Cadeia de decisão de formatos (Android)
`app/core/downloader.FORMAT_MAP` usa flags de merge → substituído por
`android/engine.py:FORMAT_MAP` com seletores de arquivo único (`b[...]`).

## Como gerar o APK (na sua máquina com WSL2 ou Linux)
```bash
# Linux/WSL2 Ubuntu
sudo apt-get update && sudo apt-get install -y git zip unzip openjdk-17-jdk \
  python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev \
  libncursesw5-dev libtinfo5 cmake libffi-dev libssl-dev
pip3 install --upgrade buildozer cython

git clone <repo> vibcine && cd vibcine
buildozer -v android debug        # APK → bin/
```

## APK/AAB via GitHub Actions (nesta máquina)
`.github/workflows/android-apk.yml`:
- `workflow_dispatch` manual → gera **APK** (artefato `vibecine-apk`);
- tag `android-vX.Y.Z` → gera APK + **AAB** release (artefato `vibecine-aab`).

## Build local/APK — observações importantes
- **Entry point exigido pelo python-for-android:** `main.py` na raiz do
  projeto (shim que chama `android.main:run`). A versão Windows continua
  usando `vibcine.py` e não é afetada.
- `source.exclude_dirs` de `buildozer.spec` remove `.venv/`, `dist/`,
  `release/`, `app/ui/` etc. — nada de desktop entra no APK.

## AAB (assinatura)
`buildozer android release` precisa de um keystore. Configure segredos no
repositório (ex.: `KEYSTORE_B64`, `KEYSTORE_PASSWORD`) e decodifique no
workflow antes do passo release, por exemplo:

```yaml
- run: |
    echo "${{ secrets.KEYSTORE_B64 }}" | base64 -d > vibcine.keystore
# e em buildozer.spec:
# [app]  android.release_artifact = aab
# p4a.release.keystore = ./vibcine.keystore
# p4a.release.keystorepw via env KEYSTORE_PASSWORD
```

Alternativa: gerar o AAB localmente (WSL2/Linux) com keystore próprio e
assinar com `jarsigner`/`apksigner`.

## Instalar no celular
- Ative "Fontes desconhecidas" e instale o APK; ou `adb install`.
- Permissões pedidas: INTERNET, armazenamento, notificações.

## Arquitetura
```
app/core/            → núcleo compartilhado (sem mudanças no Windows)
android/             → camada Android
  engine.py          → DownloadEngine (yt-dlp em-processo)
  share.py           → Intent ACTION_SEND / fallback desktop
  main.py            → UI KivyMD (4 seções, navegação inferior)
buildozer.spec       → configuração do APK/AAB
.github/workflows/   → build CI do APK/AAB
```

## Testes
`python -m unittest tests.test_android` — engine (download real com
yt-dlp falso), pausa/retomada, cancelamento, fila, erros sem credenciais,
paths Android, bloqueio de URL sensível.

## Limitações conhecidas (documentadas)
1. MP3 requer FFmpeg → no MVP baixa áudio original; conversão não feita.
2. YouTube com proteção JS pode falhar (sem Deno no Android).
3. Downloads continuam apenas com o app aberto (MVP); serviço foreground
   planejado (`android/services/`) na próxima iteração.
4. Merge de vídeo+áudio (melhor qualidade) indisponível sem ffmpeg.
5. `vibcine://` no Android usa Intent-filter (a adicionar em revisão
   futura; Windows usa Registro — fora do escopo do MVP).
