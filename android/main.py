# -*- coding: utf-8 -*-
"""VibeCine para Android — UI mobile (Kivy/KivyMD).

Navegação inferior com 4 seções: Biblioteca, Downloads, Histórico,
Configurações. Reutiliza o núcleo em app/core (parser, roteador, extrator,
engine de download em processo, histórico, compartilhamento).

UX mobile: alvos de toque grandes, navegação por toque, cards/listas,
feedback com snackbar, loading indeterminado, estados vazios e erros
amigáveis vindos do core (errors.py).
"""

from __future__ import annotations

import os
import threading

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import (MDDialog, MDDialogButtonContainer,
                               MDDialogContentContainer, MDDialogHeadlineText,
                               MDDialogSupportingText)
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (MDListItem, MDListItemHeadlineText,
                             MDListItemSupportingText,
                             MDListItemTrailingCheckbox)
from kivymd.uix.navigationbar import (MDNavigationBar, MDNavigationItem,
                                      MDNavigationItemIcon,
                                      MDNavigationItemLabel)
from kivymd.uix.progressindicator import (MDCircularProgressIndicator,
                                          MDLinearProgressIndicator)
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.textfield import MDTextField, MDTextFieldHintText

from kivy.uix.image import Image as KivyImage
from kivy.uix.widget import Widget

from app.core import share as core_share
from app.core import paths
from app.core.config import load_config, save_config
from app.core.extractor import ExtractorError, extract_entries
from app.core.history import HistoryStore
from app.core.branding import APP_NAME, APP_PRODUCT, APP_VERSION, APP_ABOUT_TEXT
from app.core.downloader import JobStatus
from android import share as android_share
from android.engine import DownloadEngine


def _snackbar(self, text: str):
    from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
    MDSnackbar(MDSnackbarText(text=text), y=dp(24), pos_hint={"center_x": .5},
               size_hint_x=.9, duration=2).open()


# ══════════════════════════ BIBLIOTECA ══════════════════════════════════════

class BibliotecaScreen(MDScreen):
    def __init__(self, app, **kw):
        super().__init__(name="biblioteca", **kw)
        self.app = app
        self.entries: list[dict] = []
        self.filtered: list[dict] = []
        self.selected: set[int] = set()
        self._loading_thread: threading.Thread | None = None
        self._cancel = threading.Event()

        root = MDBoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))

        root.add_widget(MDLabel(text="Biblioteca", font_style="Title",
                                role="large", size_hint_y=None, height=dp(40)))

        row = MDBoxLayout(orientation="horizontal", spacing=dp(8),
                          size_hint_y=None, height=dp(56))
        self.url_field = MDTextField(MDTextFieldHintText(
            text="Cole a URL (M3U, YouTube, vídeo)…"), mode="outlined")
        row.add_widget(self.url_field)
        self.load_btn = MDButton(MDButtonText(text="Carregar"), style="filled",
                                 size_hint_x=None, width=dp(120))
        self.load_btn.bind(on_release=lambda *_: self.load())
        row.add_widget(self.load_btn)
        root.add_widget(row)

        self.search = MDTextField(MDTextFieldHintText(text="Buscar por título…"),
                                  mode="outlined", size_hint_y=None,
                                  height=dp(52))
        self.search.bind(text=lambda *_: self.apply_filters())
        root.add_widget(self.search)

        self.status = MDLabel(text="Nenhuma lista carregada",
                              size_hint_y=None, height=dp(24),
                              theme_text_color="Secondary")
        root.add_widget(self.status)

        self.spinner = MDCircularProgressIndicator(size_hint=(None, None),
                                                   size=(dp(38), dp(38)),
                                                   pos_hint={"center_x": .5})
        self.spinner.opacity = 0
        root.add_widget(self.spinner)

        self.list_scroll = MDScrollView()
        self.list_box = MDBoxLayout(orientation="vertical", spacing=dp(4),
                                    adaptive_height=True)
        self.list_scroll.add_widget(self.list_box)
        root.add_widget(self.list_scroll)

        bottom = MDBoxLayout(orientation="horizontal", spacing=dp(8),
                             size_hint_y=None, height=dp(52))
        self.sel_label = MDLabel(text="0 selecionados", theme_text_color="Secondary")
        bottom.add_widget(self.sel_label)
        all_b = MDButton(MDButtonText(text="Todos"), style="text")
        all_b.bind(on_release=lambda *_: self.select_all(True))
        bottom.add_widget(all_b)
        none_b = MDButton(MDButtonText(text="Nenhum"), style="text")
        none_b.bind(on_release=lambda *_: self.select_all(False))
        bottom.add_widget(none_b)
        root.add_widget(bottom)

        self.dl_btn = MDButton(MDButtonText(text="Baixar selecionados"),
                               style="filled", size_hint_y=None, height=dp(48))
        self.dl_btn.bind(on_release=lambda *_: self.enqueue_selected())
        root.add_widget(self.dl_btn)

        self.add_widget(root)

    # ── Carregar ─────────────────────────────────────────────────────────

    def load(self):
        url = self.url_field.text.strip()
        if not url:
            _snackbar(self, "Digite uma URL para carregar.")
            return
        if self._loading_thread and self._loading_thread.is_alive():
            _snackbar(self, "Carregamento já em andamento.")
            return
        self._cancel.clear()
        self._set_loading(True, "Carregando…")
        t = threading.Thread(target=self._fetch, args=(url,), daemon=True)
        t.start()
        self._loading_thread = t

    def _fetch(self, url):
        try:
            entries = extract_entries(url, self.app.cfg, log=lambda m: None,
                                      cancel=self._cancel)
            Clock.schedule_once(lambda dt: self._loaded(entries))
        except ExtractorError as exc:
            Clock.schedule_once(lambda dt, e=exc: self._load_error(e.friendly))
        except Exception as exc:
            Clock.schedule_once(lambda dt, e=exc: self._load_error(str(e)))

    def _set_loading(self, loading, text=""):
        def _do(*_):
            self.spinner.opacity = 1 if loading else 0
            self.load_btn.disabled = loading
            if text:
                self.status.text = text
        Clock.schedule_once(_do)

    def _loaded(self, entries):
        self._set_loading(False)
        self.entries = entries
        self.apply_filters()
        n = len(entries)
        self.status.text = (f"{n} itens carregados ✔" if n else
                            "Nenhum item encontrado")
        _snackbar(self, f"{n} itens" if n else "Lista vazia")

    def _load_error(self, friendly):
        self._set_loading(False)
        self.status.text = "✖ " + friendly
        _snackbar(self, friendly)

    # ── Lista/filtros/seleção ────────────────────────────────────────────

    def apply_filters(self):
        s = self.search.text.lower().strip()
        self.filtered = [e for e in self.entries
                         if not s or s in e["title"].lower()]
        self.selected = {i for i in self.selected if i < len(self.filtered)}
        self._render()

    def _render(self):
        self.list_box.clear_widgets()
        if not self.filtered:
            empty = MDLabel(
                text="Cole uma URL acima para começar.\nToque nos itens para selecionar.",
                halign="center", theme_text_color="Secondary")
            self.list_box.add_widget(empty)
            self._update_sel_label()
            return
        for i, e in enumerate(self.filtered):
            is_sel = i in self.selected
            item = MDListItem(
                MDListItemHeadlineText(text=e["title"]),
                MDListItemSupportingText(
                    text=f"{e.get('group','')} • {e.get('type','')}"),
                MDListItemTrailingCheckbox(active=is_sel),
                theme_bg_color="Custom",
                md_bg_color=self.theme_cls.primaryColor if is_sel else
                self.theme_cls.surfaceColor,
            )
            item.bind(on_release=lambda _w, idx=i: self.toggle(idx))
            self.list_box.add_widget(item)
        self._update_sel_label()

    def toggle(self, idx):
        if idx in self.selected:
            self.selected.discard(idx)
        else:
            self.selected.add(idx)
            self._show_details(self.filtered[idx])
        self._render()

    def select_all(self, value):
        self.selected = set(range(len(self.filtered))) if value else set()
        self._render()

    def _update_sel_label(self):
        n = len(self.selected)
        self.sel_label.text = f"{n} selecionados"
        self.dl_btn.disabled = n == 0

    # ── Detalhes / compartilhar ──────────────────────────────────────────

    def _show_details(self, e):
        plan = core_share.plan_share(e)
        body = (f"{e['title']}\n\nGrupo: {e['group']}\nTipo: {e['type']}\n\n"
                + (plan.reason if not plan.shareable else
                   "Link seguro disponível para compartilhar."))

        def do_share(*_):
            ok, msg = android_share.share_entry(e)
            _snackbar(self, msg)

        def show_qr(*_):
            if not plan.shareable:
                _snackbar(self, "QR indisponível para URL sensível.")
                return
            data = core_share.make_qr_png_bytes(plan.url)
            import io
            img = KivyImage(source="",
                            size_hint=(None, None), size=(dp(220), dp(220)))
            tex = CoreImage(io.BytesIO(data), ext="png").texture
            img.texture = tex
            dlg2 = MDDialog(
                MDDialogHeadlineText(text="QR Code"),
                MDDialogContentContainer(img),
                MDDialogButtonContainer(
                    MDButton(MDButtonText(text="Fechar"), style="text",
                             on_release=lambda *_: dlg2.dismiss())),
            )
            dlg2.open()

        dlg = MDDialog(
            MDDialogHeadlineText(text=e["title"][:60]),
            MDDialogSupportingText(text=body),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="Fechar"), style="text",
                         on_release=lambda *_: dlg.dismiss()),
                MDButton(MDButtonText(text="QR"), style="text",
                         on_release=show_qr),
                MDButton(MDButtonText(text="Compartilhar"), style="text",
                         on_release=do_share)),
        )
        dlg.open()

    def enqueue_selected(self):
        entries = [self.filtered[i] for i in sorted(self.selected)]
        if not entries:
            return
        self.app.engine.add(entries)
        _snackbar(self, f"{len(entries)} item(ns) na fila")
        self.app.sm.current = "downloads"


# ══════════════════════════ DOWNLOADS ═══════════════════════════════════════

class DownloadsScreen(MDScreen):
    def __init__(self, app, **kw):
        super().__init__(name="downloads", **kw)
        self.app = app
        self._rows: dict[int, MDCard] = {}

        root = MDBoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        top = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                          height=dp(40))
        top.add_widget(MDLabel(text="Downloads", font_style="Title", role="large"))
        cancel_all = MDButton(MDButtonText(text="Cancelar todos"), style="text")
        cancel_all.bind(on_release=lambda *_: self.app.engine.cancel_all())
        top.add_widget(cancel_all)
        root.add_widget(top)

        self.total = MDLinearProgressIndicator(size_hint_y=None, height=dp(8))
        root.add_widget(self.total)

        self.scroll = MDScrollView()
        self.list_box = MDBoxLayout(orientation="vertical", spacing=dp(8),
                                    adaptive_height=True)
        self.scroll.add_widget(self.list_box)
        root.add_widget(self.scroll)

        self.empty = MDLabel(text="Nenhum download. Selecione itens na Biblioteca.",
                             halign="center", theme_text_color="Secondary")
        self.list_box.add_widget(self.empty)
        self.add_widget(root)

    def refresh(self):
        eng = self.app.engine
        ids = {j.id for j in eng.jobs}
        if self.empty in self.list_box.children and eng.jobs:
            self.list_box.remove_widget(self.empty)
        for job in eng.jobs:
            card = self._rows.get(job.id)
            if card is None:
                card = self._make_card(job)
                self._rows[job.id] = card
                self.list_box.add_widget(card)
            self._update_card(job, card)
        if eng.jobs:
            self.total.value = sum(
                100.0 if j.status is JobStatus.DONE else j.percent
                for j in eng.jobs) / len(eng.jobs)

    def _make_card(self, job):
        card = MDCard(orientation="vertical", spacing=dp(4), padding=dp(12),
                      size_hint_y=None, height=dp(120), radius=[12])
        card._title = MDLabel(text=job.title, bold=True, shorten=True,
                              shorten_from="right", max_lines=1)
        card.add_widget(card._title)
        card._prog = MDLinearProgressIndicator(size_hint_y=None, height=dp(6))
        card.add_widget(card._prog)
        info = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(26))
        card._meta = MDLabel(text="", theme_text_color="Secondary",
                             font_style="Label", role="medium")
        info.add_widget(card._meta)
        card._status = MDLabel(text="", theme_text_color="Secondary",
                               font_style="Label", role="medium",
                               halign="right")
        info.add_widget(card._status)
        card.add_widget(info)
        btns = MDBoxLayout(orientation="horizontal", spacing=dp(4),
                           size_hint_y=None, height=dp(36))
        eng = self.app.engine
        for label, fn in (("Pausar", lambda *_: eng.pause_job(job.id)),
                          ("Retomar", lambda *_: eng.resume_job(job.id)),
                          ("Cancelar", lambda *_: eng.cancel_job(job.id))):
            b = MDButton(MDButtonText(text=label), style="text")
            b.bind(on_release=fn)
            btns.add_widget(b)
        card.add_widget(btns)
        return card

    def _update_card(self, job, card):
        card._prog.value = job.percent
        card._status.text = {"aguardando": "Aguardando", "baixando": "Baixando",
                             "concluido": "Concluído ✔", "erro": "Erro ✖",
                             "cancelado": "Cancelado", "pausado": "Pausado ⏸"
                             }.get(job.status.value, job.status.value)
        parts = []
        if job.speed:
            parts.append(job.speed)
        if job.eta:
            parts.append(f"ETA {job.eta}")
        if job.total_bytes:
            parts.append(f"{job.downloaded_bytes/1048576:.0f}/{job.total_bytes/1048576:.0f} MB")
        if job.status is JobStatus.FAILED and job.error_message:
            parts.append(job.error_message)
        card._meta.text = "  •  ".join(parts)


# ══════════════════════════ HISTÓRICO ═══════════════════════════════════════

class HistoricoScreen(MDScreen):
    def __init__(self, app, **kw):
        super().__init__(name="historico", **kw)
        self.app = app
        root = MDBoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        top = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                          height=dp(40))
        top.add_widget(MDLabel(text="Histórico", font_style="Title",
                               role="large"))
        clear = MDButton(MDButtonText(text="Limpar"), style="text")
        clear.bind(on_release=lambda *_: self._clear())
        top.add_widget(clear)
        root.add_widget(top)
        self.scroll = MDScrollView()
        self.list_box = MDBoxLayout(orientation="vertical", spacing=dp(4),
                                    adaptive_height=True)
        self.scroll.add_widget(self.list_box)
        root.add_widget(self.scroll)
        self.add_widget(root)

    def on_pre_enter(self):
        self.reload()

    def reload(self):
        self.list_box.clear_widgets()
        rows = self.app.history.list()
        if not rows:
            self.list_box.add_widget(MDLabel(
                text="Sem registros ainda.", halign="center",
                theme_text_color="Secondary"))
            return
        for r in rows:
            self.list_box.add_widget(MDListItem(
                MDListItemHeadlineText(text=r["title"]),
                MDListItemSupportingText(
                    text=f"{r['status']} • {(r.get('finished_at','') or '').replace('T',' ')}")))

    def _clear(self):
        self.app.history.clear()
        self.reload()
        _snackbar(self, "Histórico limpo.")


# ══════════════════════════ CONFIGURAÇÕES ═══════════════════════════════════

class ConfigScreen(MDScreen):
    def __init__(self, app, **kw):
        super().__init__(name="config", **kw)
        self.app = app
        cfg = app.cfg

        scroll = MDScrollView()
        root = MDBoxLayout(orientation="vertical", spacing=dp(12),
                           padding=dp(12), adaptive_height=True)
        scroll.add_widget(root)

        root.add_widget(MDLabel(text="Configurações", font_style="Title",
                                role="large", size_hint_y=None, height=dp(40)))

        root.add_widget(MDLabel(text=f"Pasta de downloads:\n{cfg.get('download_folder')}",
                                theme_text_color="Secondary", adaptive_height=True))

        fmt_row = MDBoxLayout(orientation="horizontal", spacing=dp(8),
                              size_hint_y=None, height=dp(40))
        fmt_row.add_widget(MDLabel(text="Formato padrão: MP4/original"))
        self.fmt_switch = MDSwitch()
        fmt_row.add_widget(MDLabel(text="Apenas áudio"))
        fmt_row.add_widget(self.fmt_switch)
        root.add_widget(fmt_row)

        self.org_switch = MDSwitch()
        Clock.schedule_once(lambda *_: setattr(self.org_switch, "active",
                         bool(cfg.get("organize_by_group", True))), 0)
        org_row = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                              height=dp(40))
        org_row.add_widget(MDLabel(text="Organizar por grupo"))
        org_row.add_widget(Widget())
        org_row.add_widget(self.org_switch)
        root.add_widget(org_row)

        self.theme_switch = MDSwitch()
        Clock.schedule_once(lambda *_: setattr(self.theme_switch, "active",
                         cfg.get("theme", "dark") == "dark"), 0)
        trow = MDBoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(40))
        trow.add_widget(MDLabel(text="Tema escuro"))
        trow.add_widget(Widget())
        trow.add_widget(self.theme_switch)
        self.theme_switch.bind(active=lambda *_: self._toggle_theme())
        root.add_widget(trow)

        save_b = MDButton(MDButtonText(text="Salvar"), style="filled",
                          size_hint_y=None, height=dp(48))
        save_b.bind(on_release=lambda *_: self._save())
        root.add_widget(save_b)

        root.add_widget(MDLabel(text=f"{APP_PRODUCT} • v{APP_VERSION}",
                                theme_text_color="Secondary",
                                adaptive_height=True))
        self.add_widget(scroll)

    def _toggle_theme(self):
        self.app.theme_cls.theme_style = ("Dark" if self.theme_switch.active
                                          else "Light")

    def _save(self):
        cfg = self.app.cfg
        cfg["organize_by_group"] = bool(self.org_switch.active)
        cfg["theme"] = "dark" if self.theme_switch.active else "light"
        cfg["format"] = "mp4" if not self.fmt_switch.active else "mp3"
        save_config(cfg)
        _snackbar(self, "Configurações salvas!")


# ══════════════════════════ APP ═════════════════════════════════════════════

class VibeCineAndroidApp(MDApp):
    def build(self):
        self.cfg = load_config()
        self.cfg.setdefault("download_folder", paths.user_downloads_default())
        self.history = HistoryStore()
        self.engine = DownloadEngine(
            self.cfg,
            max_workers=int(self.cfg.get("max_concurrent_downloads", 1)),
            on_job_update=lambda j: self._job_updated(j),
            on_progress=lambda p: None,
            on_log=lambda m: None,
            on_queue_finished=lambda: Clock.schedule_once(self._queue_done))
        self._recorded_jobs: set[int] = set()

        self.title = APP_NAME
        # Identidade VibeCine no Android: vermelho sobre preto profundo
        self.theme_cls.theme_style = ("Dark" if self.cfg.get("theme", "dark") == "dark"
                                      else "Light")
        self.theme_cls.primary_palette = "Red"

        root = MDBoxLayout(orientation="vertical")
        self.sm = MDScreenManager()
        self.biblioteca = BibliotecaScreen(self)
        self.downloads = DownloadsScreen(self)
        self.historico = HistoricoScreen(self)
        self.config = ConfigScreen(self)
        for s in (self.biblioteca, self.downloads, self.historico, self.config):
            self.sm.add_widget(s)
        root.add_widget(self.sm)

        nav = MDNavigationBar()
        for key, label, icon in (("biblioteca", "Biblioteca", "movie-open"),
                                 ("downloads", "Downloads", "download"),
                                 ("historico", "Histórico", "history"),
                                 ("config", "Ajustes", "cog")):
            item = MDNavigationItem(
                MDNavigationItemIcon(icon=icon),
                MDNavigationItemLabel(text=label))
            item.bind(on_release=lambda *_i, k=key: setattr(self.sm, "current", k))
            nav.add_widget(item)
        root.add_widget(nav)

        self.sm.current = "biblioteca"
        Clock.schedule_interval(self._poll, 0.4)
        return root

    def _poll(self, dt):
        self.downloads.refresh()

    def _job_updated(self, job):
        def _do(*_):
            if job.status is JobStatus.DONE and job.id not in self._recorded_jobs:
                self._recorded_jobs.add(job.id)
                try:
                    size = os.path.getsize(job.output_path) if job.output_path and os.path.isfile(job.output_path) else 0
                    self.history.add(
                        title=job.title, group=job.entry.get("group", ""),
                        url=job.entry.get("url", ""), status=job.status.value,
                        out_dir=self.cfg.get("download_folder", ""),
                        output_path=job.output_path, size_bytes=size)
                except Exception:
                    pass
        Clock.schedule_once(_do)

    def _queue_done(self, *_):
        pass

    def on_stop(self):
        self.engine.shutdown()


def run():
    VibeCineAndroidApp().run()


if __name__ == "__main__":
    run()
