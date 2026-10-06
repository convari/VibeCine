# Changelog — VibeCine Downloader Pro

## v2.0.0 (2026-10-04) — Reescrita completa

### Novo
- Interface moderna em PySide6 (Qt) com tema escuro/claro, sidebar e
  identidade visual própria (logo/ícone vetoriais integrados).
- Núcleo modular (app/core): parser M3U robusto, roteador de URLs,
  extrator com retry/backoff e classificação de erros amigável.
- Downloader v2: fila com concorrência configurável, 6 estados,
  progresso real (%/velocidade/ETA), pausa/retomada, cancelamento
  individual e geral, verificação de integridade com ffprobe, nomes
  seguros (sem sobrescrita).
- Histórico em SQLite (filtro, abrir pasta, excluir/limpar).
- Compartilhamento seguro: WhatsApp, Telegram, Facebook, X, e-mail,
  copiar link e QR Code — com bloqueio de URLs com credenciais.
- Onboarding de primeira execução + Termos de Uso.
- Protocolo vibcine:// (registro HKCU, instância única).
- Atualizador interno do app (SHA-256) e das ferramentas
  (yt-dlp/FFmpeg/Deno) em pasta gravável.

### Correções (em relação à versão legada)
- Formato padrão não assume mais MP3 indevidamente (agora "Original").
- Erros de rede exibidos em linguagem amigável (403/404/timeout/DNS...).
- Credenciais de IPTV mascaradas em logs, telas e histórico.
- Fim de messages boxes bloqueantes; toasts informativos.

### Legado
- A interface Tkinter original permanece em `m3u_downloader.py`
  (compatibilidade), consumindo o mesmo núcleo.
