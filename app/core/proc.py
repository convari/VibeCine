# -*- coding: utf-8 -*-
"""Política CENTRALIZADA de criação de subprocessos.

No Windows, subprocessos de ferramentas (yt-dlp, ffmpeg, ffprobe, deno)
não devem abrir janela de console para o usuário, MAS precisam continuar
com stdout/stderr capturados (progresso real e erros vão à interface).

Estratégia (dupla camada, mantendo shell=False):
1. creationflags=CREATE_NO_WINDOW;
2. STARTUPINFO com STARTF_USESHOWWINDOW + SW_HIDE (cobertura extra).

Fora do Windows, os parâmetros são ignorados (não se aplicam).

Uso:  from app.core.proc import popen, run
Sempre use estas funções no lugar de subprocess.Popen/run diretos para
ferramentas externas. subprocess continuará sendo usado para ações
visíveis intencionais (ex.: explorer /select).
"""

from __future__ import annotations

import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def _hidden_kwargs() -> dict:
    """Kwargs para subprocess que impedem janela visível (Win only)."""
    if sys.platform != "win32":
        return {}
    kwargs: dict = {"creationflags": CREATE_NO_WINDOW}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    kwargs["startupinfo"] = si
    return kwargs


def popen(cmd: list[str], **kwargs) -> subprocess.Popen:
    """subprocess.Popen sem janela de console (stdout/stderr preservados)."""
    merged = {**kwargs, **_hidden_kwargs()}
    return subprocess.Popen(cmd, **merged)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run sem janela de console."""
    merged = {**kwargs, **_hidden_kwargs()}
    return subprocess.run(cmd, **merged)


def hidden_kwargs_for_tests() -> dict:
    """Expõe os mesmos kwargs para verificação em testes."""
    return _hidden_kwargs()
