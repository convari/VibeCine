# -*- coding: utf-8 -*-
"""Compartilhamento via Intent nativo do Android.

No Android usa ACTION_SEND (sheet nativo do sistema). Fora do Android,
faz fallback para os links de compartilhamento do core (webbrowser).
Todas as proteções anti-credencial do core/share.py são mantidas.
"""

from __future__ import annotations

from app.core import paths, share


def share_entry(entry: dict) -> tuple[bool, str]:
    """Compartilha uma entrada. Retorna (ok, mensagem_de_feedback).

    Nunca expõe credenciais: URLs sensíveis viram referência mascarada.
    """
    plan = share.plan_share(entry)
    if not plan.shareable:
        return False, (plan.reason or "Este conteúdo não pode ser compartilhado.")
    message = share.build_share_message(entry, plan.url)

    if paths.is_android():
        try:
            from jnius import autoclass  # type: ignore
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_SEND)
            intent.setType("text/plain")
            intent.putExtra(Intent.EXTRA_TEXT, message)
            chooser = Intent.createChooser(intent, "Compartilhar via…")
            PythonActivity.mActivity.startActivity(chooser)
            return True, "Abrindo compartilhamento do sistema…"
        except Exception as exc:
            return False, f"Compartilhamento nativo indisponível: {exc}"

    # Desktop/dev: fallback pelo navegador (WhatsApp web etc.)
    import webbrowser
    links = share.build_share_links(message, plan.url)
    webbrowser.open(links["whatsapp"])
    return True, "Abrindo compartilhamento no navegador…"
