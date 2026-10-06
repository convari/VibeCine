# -*- coding: utf-8 -*-
"""yt-dlp falso para testes do DownloadManager.

Simula o comportamento do yt-dlp real via stdout:
  python _fake_ytdlp.py [args do yt-dlp] -o TEMPLATE URL

URL controla o cenario:
  fake://ok         -> progresso 0..100% e arquivo criado (sucesso)
  fake://slow?T     -> idem, com T segundos de espera entre passos
  fake://403        -> erro permanente, exit 3
  fake://flaky      -> falha transitoria na 1a vez, sucesso nas demais

Se a variavel de ambiente VIBE_FAKE_CONC estiver definida (caminho de um
arquivo), registra linhas "start_ts end_ts" para medicao de concorrencia.
"""
import os
import sys
import time

mode = sys.argv[-1].replace("fake://", "")
tpl = sys.argv[sys.argv.index("-o") + 1]
out = tpl.replace("%(ext)s", "mp4")
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

TOTAL = 10 * 1024 * 1024  # 10 MiB

if mode == "403":
    print("ERROR: HTTP Error 403: Forbidden", flush=True)
    sys.exit(3)

if mode == "flaky":
    marker = out + ".attempts"
    n = int(open(marker).read()) if os.path.exists(marker) else 0
    with open(marker, "w") as fh:
        fh.write(str(n + 1))
    if n == 0:
        print("ERROR: connection timed out", flush=True)
        sys.exit(1)
    # segunda tentativa: cai no fluxo de sucesso abaixo (resume com --continue)

slow = 0.0
if mode.startswith("slow"):
    slow = float(mode.split("?")[1]) if "?" in mode else 0.3

conc_log = os.environ.get("VIBE_FAKE_CONC")
t0 = time.monotonic()

steps = 8
for i in range(1, steps + 1):
    pct = i * 100.0 / steps
    mib = TOTAL / 1024 / 1024
    print(f"[download] {pct:5.1f}% of ~{mib:.2f}MiB at 2.50MiB/s ETA 00:{steps - i:02d}",
          flush=True)
    if slow:
        time.sleep(slow)

with open(out, "wb") as fh:
    fh.write(b"\x00" * TOTAL)

if conc_log:
    with open(f"{conc_log}.{'%04d' % os.getpid()}", "a") as fh:
        fh.write(f"{t0:.3f} {time.monotonic():.3f}\n")

print(f"[download] Destination: {out}", flush=True)
sys.exit(0)
