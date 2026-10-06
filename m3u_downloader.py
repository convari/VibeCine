#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U Downloader Pro
Baixador de conteudos M3U/IPTV e YouTube
Motor: FFmpeg + yt-dlp
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import subprocess
import queue
import urllib.request
from io import BytesIO

from app.core.config import load_config, save_config
from app.core.extractor import ExtractorError, extract_entries
from app.core.downloader import build_ytdlp_command
from app.core import proc as _proc

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# Parser, validação de URLs e ferramentas agora vivem em app.core —
# este arquivo é apenas a interface (UI legada, preservada).


# ── Janela de Configuracoes ────────────────────────────────────────────────────

class ConfigWindow(tk.Toplevel):
    def __init__(self, parent, cfg, on_save):
        super().__init__(parent)
        self.title("Configurações")
        self.resizable(False, False)
        self.cfg = cfg.copy()
        self.on_save = on_save
        self.grab_set()
        self._build()
        self.transient(parent)
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        pad = {"padx": 10, "pady": 6}
        f = ttk.Frame(self, padding=15)
        f.pack(fill=tk.BOTH, expand=True)

        # Pasta de downloads
        ttk.Label(f, text="Pasta de downloads:").grid(row=0, column=0, sticky=tk.W, **pad)
        ff = ttk.Frame(f)
        ff.grid(row=0, column=1, sticky=tk.EW, **pad)
        self.folder_var = tk.StringVar(value=self.cfg["download_folder"])
        ttk.Entry(ff, textvariable=self.folder_var, width=36).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(ff, text="...", width=3, command=self._browse).pack(side=tk.LEFT, padx=(4, 0))

        # FFmpeg
        ttk.Label(f, text="FFmpeg (caminho/comando):").grid(row=1, column=0, sticky=tk.W, **pad)
        self.ffmpeg_var = tk.StringVar(value=self.cfg["ffmpeg_path"])
        ttk.Entry(f, textvariable=self.ffmpeg_var, width=38).grid(row=1, column=1, sticky=tk.EW, **pad)

        # yt-dlp
        ttk.Label(f, text="yt-dlp (caminho/comando):").grid(row=2, column=0, sticky=tk.W, **pad)
        self.ytdlp_var = tk.StringVar(value=self.cfg["ytdlp_path"])
        ttk.Entry(f, textvariable=self.ytdlp_var, width=38).grid(row=2, column=1, sticky=tk.EW, **pad)

        # Velocidade
        ttk.Label(f, text="Velocidade de download:").grid(row=3, column=0, sticky=tk.NW, **pad)
        self.speed_var = tk.StringVar(value=self.cfg.get("speed_limit", "0"))
        speeds = [
            ("Sem limite", "0"),
            ("1 MB/s",  "1M"),
            ("5 MB/s",  "5M"),
            ("10 MB/s", "10M"),
            ("20 MB/s", "20M"),
            ("50 MB/s", "50M"),
        ]
        sf = ttk.Frame(f)
        sf.grid(row=3, column=1, sticky=tk.W, **pad)
        for idx, (lbl, val) in enumerate(speeds):
            ttk.Radiobutton(sf, text=lbl, variable=self.speed_var, value=val).grid(
                row=idx // 3, column=idx % 3, sticky=tk.W, padx=8, pady=2
            )

        # Formato
        ttk.Label(f, text="Formato de saída:").grid(row=4, column=0, sticky=tk.W, **pad)
        self.fmt_var = tk.StringVar(value=self.cfg.get("format", "original"))
        fmf = ttk.Frame(f)
        fmf.grid(row=4, column=1, sticky=tk.W, **pad)
        ttk.Radiobutton(fmf, text="Original (automático)", variable=self.fmt_var, value="original").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(fmf, text="MP3 (áudio)",           variable=self.fmt_var, value="mp3").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(fmf, text="MP4 (vídeo)",           variable=self.fmt_var, value="mp4").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(fmf, text="FullHD (1080p)",        variable=self.fmt_var, value="fullhd").pack(side=tk.LEFT, padx=5)

        # Organizar por grupo
        self.org_var = tk.BooleanVar(value=self.cfg.get("organize_by_group", True))
        ttk.Checkbutton(f, text="Organizar por grupo", variable=self.org_var).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, **pad
        )

        # Salvar (confirma como padrão)
        ttk.Button(f, text="  Salvar  (confirmar como padrão)  ",
                   command=self._save).grid(row=6, column=0, columnspan=2, pady=14)

        f.columnconfigure(1, weight=1)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get() or ".")
        if d:
            self.folder_var.set(d)

    def _save(self):
        self.cfg["download_folder"] = self.folder_var.get().strip()
        self.cfg["ffmpeg_path"]     = self.ffmpeg_var.get().strip()
        self.cfg["ytdlp_path"]      = self.ytdlp_var.get().strip()
        self.cfg["organize_by_group"] = self.org_var.get()
        self.cfg["speed_limit"]     = self.speed_var.get()
        self.cfg["format"]          = self.fmt_var.get()
        self.on_save(self.cfg)
        messagebox.showinfo("Configurações", "✔ Configurações salvas como padrão!", parent=self)
        self.destroy()


# ── Aplicativo Principal ───────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VibeCine - Downloader Pro")
        self.geometry("1200x720")
        self.minsize(900, 600)

        self.cfg          = load_config()
        self.entries      = []
        self.filtered     = []
        self._selected    = set()   # set of indices into self.filtered
        self._iid_map     = {}      # treeview iid -> filtered index
        self._cover_img   = None
        self._log_q       = queue.Queue()
        self._downloading = False
        self._cancel      = False
        self._loading     = False   # True while batch-inserting rows
        self._drag_active = False   # True while left button held on tree
        self._drag_check  = True    # True = mark, False = unmark (set on press)
        self._drag_seen   = set()   # iids already processed in this drag

        self._build_ui()
        self._poll_log()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill=tk.BOTH, expand=True)

        # ── Playlist bar ──
        pf = ttk.LabelFrame(root, text="Playlist", padding=8)
        pf.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(pf, text="URL do M3U / IPTV / YouTube:").pack(anchor=tk.W)
        row = ttk.Frame(pf)
        row.pack(fill=tk.X, pady=(4, 0))

        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(row, textvariable=self.url_var, font=("Arial", 10))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.url_entry.bind("<Return>", lambda _e: self._load())

        ttk.Button(row, text="CARREGAR", command=self._load,   width=12).pack(side=tk.LEFT, padx=(6, 3))
        ttk.Button(row, text="CONFIG",   command=self._config, width=8).pack(side=tk.LEFT)

        self.status_lbl = ttk.Label(pf, text="Nenhum M3U carregado", foreground="gray")
        self.status_lbl.pack(anchor=tk.W, pady=(4, 0))

        # ── Middle ──
        mid = ttk.Frame(root)
        mid.pack(fill=tk.BOTH, expand=True)

        # ── Left panel ──
        left = ttk.Frame(mid)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Filters
        ff = ttk.LabelFrame(left, text="Filtros", padding=6)
        ff.pack(fill=tk.X, pady=(0, 6))
        fi = ttk.Frame(ff)
        fi.pack(fill=tk.X)

        ttk.Label(fi, text="Buscar por título:").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(fi, text="Grupo:").grid(row=0, column=2, sticky=tk.W, padx=(12, 0))
        ttk.Label(fi, text="Tipo:").grid(row=0, column=4, sticky=tk.W, padx=(12, 0))

        self.search_var = tk.StringVar()
        ttk.Entry(fi, textvariable=self.search_var, width=22).grid(row=1, column=0, sticky=tk.EW)

        self.group_var = tk.StringVar(value="Todos")
        self.grp_cb = ttk.Combobox(fi, textvariable=self.group_var, width=22, state="readonly")
        self.grp_cb["values"] = ["Todos"]
        self.grp_cb.grid(row=1, column=2, sticky=tk.EW, padx=(12, 0))

        self.type_var = tk.StringVar(value="Todos")
        self.type_cb = ttk.Combobox(fi, textvariable=self.type_var, width=16, state="readonly")
        self.type_cb["values"] = ["Todos", "Filme", "Serie", "Radio", "Esporte", "Canal"]
        self.type_cb.grid(row=1, column=4, sticky=tk.EW, padx=(12, 0))

        bf = ttk.Frame(fi)
        bf.grid(row=1, column=6, padx=(12, 0))
        ttk.Button(bf, text="APLICAR", command=self._apply, width=10).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bf, text="LIMPAR",  command=self._clear,  width=8).pack(side=tk.LEFT)

        fi.columnconfigure(0, weight=1)
        fi.columnconfigure(2, weight=1)
        fi.columnconfigure(4, weight=1)

        # Content list — virtual Treeview (renders only visible rows)
        cf = ttk.LabelFrame(left, text="Conteúdos (clique para marcar/desmarcar)", padding=6)
        cf.pack(fill=tk.BOTH, expand=True)

        tree_frame = ttk.Frame(cf)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("sel", "type", "title"),
            show="headings",
            selectmode="none",
            yscrollcommand=vsb.set,
        )
        vsb.config(command=self.tree.yview)

        self.tree.heading("sel",   text="✓",     anchor="center")
        self.tree.heading("type",  text="Tipo",   anchor="center")
        self.tree.heading("title", text="Título", anchor="w")
        self.tree.column("sel",   width=28, minwidth=28, stretch=False, anchor="center")
        self.tree.column("type",  width=52, minwidth=52, stretch=False, anchor="center")
        self.tree.column("title", width=400, stretch=True,  anchor="w")

        TYPE_COLOR = {
            "filme":   "#1565C0",
            "serie":   "#6A1B9A",
            "radio":   "#2E7D32",
            "esporte": "#E65100",
            "youtube": "#C62828",
            "canal":   "#37474F",
        }
        for tag, fg in TYPE_COLOR.items():
            self.tree.tag_configure(tag, foreground=fg)
        self.tree.tag_configure("checked", background="#DFF0D8")

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Button-1>",        self._on_drag_start)
        self.tree.bind("<B1-Motion>",       self._on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self._on_drag_end)
        self.tree.bind("<Double-Button-1>", self._on_drag_start)

        # Bottom buttons
        bb = ttk.Frame(left)
        bb.pack(fill=tk.X, pady=(6, 0))

        ttk.Button(bb, text="TODOS",   command=self._sel_all,  width=10).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bb, text="NENHUM",  command=self._sel_none, width=10).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bb, text="INVERTER",command=self._sel_inv,  width=10).pack(side=tk.LEFT, padx=(0, 4))

        self._sel_lbl = ttk.Label(bb, text="0 selecionados", foreground="gray")
        self._sel_lbl.pack(side=tk.LEFT, padx=(10, 0))

        self.cancel_btn = ttk.Button(bb, text="CANCELAR", command=self._do_cancel,
                                     width=12, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.RIGHT, padx=(0, 4))

        self.dl_btn = ttk.Button(bb, text="BAIXAR SELECIONADOS", command=self._start_dl, width=22)
        self.dl_btn.pack(side=tk.RIGHT)

        # ── Right panel ──
        rp = ttk.Frame(mid, width=310)
        rp.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        rp.pack_propagate(False)

        # Details
        dtf = ttk.LabelFrame(rp, text="Detalhes", padding=8)
        dtf.pack(fill=tk.X)

        if PIL_AVAILABLE:
            self.cover_lbl = tk.Label(dtf, bg="#d0d0d0", width=280, height=160)
            self.cover_lbl.pack(pady=(0, 6))
            self._placeholder_cover()

        self.detail_txt = tk.Text(dtf, height=6, wrap=tk.WORD, state=tk.DISABLED,
                                  font=("Arial", 9), bg="#f5f5f5", relief=tk.FLAT,
                                  cursor="arrow")
        self.detail_txt.pack(fill=tk.X)
        self._set_detail("Selecione um item para ver detalhes.")

        # Progress
        pgf = ttk.LabelFrame(rp, text="Progresso", padding=8)
        pgf.pack(fill=tk.X, pady=(8, 0))
        self.prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(pgf, variable=self.prog_var, maximum=100).pack(fill=tk.X)
        self.prog_lbl = ttk.Label(pgf, text="Pronto")
        self.prog_lbl.pack(anchor=tk.W, pady=(4, 0))

        # Log
        lf = ttk.LabelFrame(rp, text="Log", padding=8)
        lf.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_txt = scrolledtext.ScrolledText(
            lf, height=12, font=("Courier", 8),
            state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white")
        self.log_txt.pack(fill=tk.BOTH, expand=True)
        
        # Assinatura no canto inferior direito
        assinatura = tk.Label(
            root, 
            text="Desenvolvido por: Eduardo / VibeCine", 
            font=("Arial", 8, "italic"),
            foreground="gray",
            anchor=tk.E
        )
        assinatura.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

    # ── Cover helpers ─────────────────────────────────────────────────────────

    def _placeholder_cover(self):
        if not PIL_AVAILABLE:
            return
        img = Image.new("RGB", (280, 160), color="#cccccc")
        ph = ImageTk.PhotoImage(img)
        self._cover_img = ph
        self.cover_lbl.config(image=ph, text="")

    def _set_detail(self, text):
        self.detail_txt.config(state=tk.NORMAL)
        self.detail_txt.delete("1.0", tk.END)
        self.detail_txt.insert(tk.END, text)
        self.detail_txt.config(state=tk.DISABLED)

    # ── Load playlist ─────────────────────────────────────────────────────────

    def _load(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Aviso", "Digite uma URL para carregar.")
            return
        self.status_lbl.config(text="Carregando...", foreground="blue")
        threading.Thread(target=self._fetch_entries, args=(url,), daemon=True).start()

    def _fetch_entries(self, url):
        """Carrega conteúdo via núcleo (M3U local/remoto, YouTube, sites
        suportados pelo yt-dlp e streams diretos), com erros amigáveis."""
        try:
            entries = extract_entries(
                url, self.cfg,
                log=lambda msg: self.after(0, lambda m=msg: self._log(m)),
            )
            self.after(0, lambda: self._set_entries(entries))
        except ExtractorError as exc:
            self.after(0, lambda e=exc: self._load_err(e.friendly))
        except Exception as exc:
            self.after(0, lambda e=exc: self._load_err(str(e)))

    def _set_entries(self, entries):
        n = len(entries)
        self._log(f"✔ {n:,} item(s) recebido(s) — aplicando filtros...")
        self.entries = entries
        self._refresh_group_filter()
        if n == 0:
            self.status_lbl.config(text="Nenhum item encontrado.", foreground="orange")
        self._apply()

    def _load_err(self, msg):
        self.status_lbl.config(text=f"Erro: {msg}", foreground="red")
        messagebox.showerror("Erro ao carregar", f"Não foi possível carregar:\n{msg}")

    # ── Filters ───────────────────────────────────────────────────────────────

    def _refresh_group_filter(self):
        groups = sorted({e["group"] for e in self.entries})
        self.grp_cb["values"] = ["Todos"] + groups
        self.group_var.set("Todos")

    def _apply(self):
        s = self.search_var.get().lower().strip()
        g = self.group_var.get()
        t = self.type_var.get().lower()
        self.filtered = [
            e for e in self.entries
            if (not s or s in e["title"].lower())
            and (g == "Todos" or e["group"] == g)
            and (t == "todos" or e["type"] == t)
        ]
        self._build_list()

    def _clear(self):
        self.search_var.set("")
        self.group_var.set("Todos")
        self.type_var.set("Todos")
        self._apply()

    # ── Content list ──────────────────────────────────────────────────────────

    _BATCH_SIZE = 3000

    def _build_list(self):
        self._loading = False
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self._selected = set()
        self._iid_map  = {}
        self._sel_lbl.config(text="0 selecionados")

        total = len(self.filtered)
        if total == 0:
            self._log("Nenhum item encontrado.")
            return

        self.status_lbl.config(text=f"Renderizando {total:,} item(s)...", foreground="blue")
        self._loading = True
        self.after_idle(lambda: self._insert_batch(0, total))

    def _insert_batch(self, start, total):
        if not self._loading:
            return

        end = min(start + self._BATCH_SIZE, total)
        for i in range(start, end):
            e = self.filtered[i]
            tags = (e["type"],)
            iid = self.tree.insert(
                "", "end",
                values=("☐", e["type"][:3].upper(), e["title"]),
                tags=tags,
            )
            self._iid_map[iid] = i

        if end < total:
            pct = int(end / total * 100)
            self.status_lbl.config(
                text=f"Renderizando... {pct}%  ({end:,} / {total:,})",
                foreground="blue")
            self.after(1, lambda: self._insert_batch(end, total))
        else:
            self._loading = False
            self.status_lbl.config(
                text=f"{total:,} item(s) carregado(s)", foreground="green")
            self._log(f"Exibindo {total:,} item(s).")
            self.tree.yview_moveto(0)

    def _on_drag_start(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            self._drag_active = False
            return
        idx = self._iid_map.get(iid)
        if idx is None:
            self._drag_active = False
            return
        self._drag_check  = idx not in self._selected
        self._drag_active = True
        self._drag_seen   = set()
        self._apply_drag_row(iid, idx)

    def _on_drag_motion(self, event):
        if not self._drag_active:
            return
        iid = self.tree.identify_row(event.y)
        if not iid or iid in self._drag_seen:
            return
        idx = self._iid_map.get(iid)
        if idx is None:
            return
        self._apply_drag_row(iid, idx)

    def _on_drag_end(self, _event):
        self._drag_active = False

    def _apply_drag_row(self, iid, idx):
        self._drag_seen.add(iid)
        if self._drag_check:
            self._selected.add(idx)
            tags = [t for t in self.tree.item(iid, "tags") if t != "checked"]
            tags.append("checked")
            self.tree.item(iid,
                           values=("☑", self.tree.set(iid, "type"), self.tree.set(iid, "title")),
                           tags=tuple(tags))
        else:
            self._selected.discard(idx)
            tags = [t for t in self.tree.item(iid, "tags") if t != "checked"]
            self.tree.item(iid,
                           values=("☐", self.tree.set(iid, "type"), self.tree.set(iid, "title")),
                           tags=tuple(tags))
        self._sel_lbl.config(text=f"{len(self._selected):,} selecionados")
        self._show_detail(idx)

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _show_detail(self, idx):
        if idx >= len(self.filtered):
            return
        e = self.filtered[idx]
        txt = (
            f"Título: {e['title']}\n"
            f"Grupo: {e['group']}\n"
            f"Tipo: {e['type'].capitalize()}\n"
            f"ID: {e.get('tvg_id') or '-'}\n"
            f"URL: {e['url'][:70]}{'…' if len(e['url']) > 70 else ''}"
        )
        self._set_detail(txt)
        if PIL_AVAILABLE:
            if e.get("logo"):
                threading.Thread(target=self._load_cover, args=(e["logo"],), daemon=True).start()
            else:
                self.after(0, self._placeholder_cover)

    def _load_cover(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "M3UDownloaderPro/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            img = Image.open(BytesIO(data)).convert("RGB")
            img.thumbnail((280, 160), Image.LANCZOS)
            ph = ImageTk.PhotoImage(img)
            self.after(0, lambda: self._show_cover(ph))
        except Exception:
            self.after(0, self._placeholder_cover)

    def _show_cover(self, ph):
        self._cover_img = ph
        if hasattr(self, "cover_lbl"):
            self.cover_lbl.config(image=ph)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _sel_all(self):
        self._selected = set(range(len(self.filtered)))
        self._sel_lbl.config(text=f"{len(self._selected):,} selecionados")
        self._update_checks_batch(list(self.tree.get_children()), "all", 0)

    def _sel_none(self):
        self._selected = set()
        self._sel_lbl.config(text="0 selecionados")
        self._update_checks_batch(list(self.tree.get_children()), "none", 0)

    def _sel_inv(self):
        total = len(self.filtered)
        self._selected = set(range(total)) - self._selected
        self._sel_lbl.config(text=f"{len(self._selected):,} selecionados")
        iids = list(self.tree.get_children())
        self._update_checks_batch(iids, "inv", 0)

    _UPDATE_BATCH = 5000

    def _update_checks_batch(self, iids, mode, start):
        end = min(start + self._UPDATE_BATCH, len(iids))
        for iid in iids[start:end]:
            idx = self._iid_map.get(iid)
            if idx is None:
                continue
            checked = (
                True  if mode == "all"  else
                False if mode == "none" else
                idx in self._selected
            )
            mark = "☑" if checked else "☐"
            row_tags = [t for t in self.tree.item(iid, "tags") if t != "checked"]
            if checked:
                row_tags.append("checked")
            self.tree.item(iid,
                           values=(mark, self.tree.set(iid, "type"), self.tree.set(iid, "title")),
                           tags=tuple(row_tags))
        if end < len(iids):
            self.after(1, lambda: self._update_checks_batch(iids, mode, end))

    def _get_selected(self):
        return [self.filtered[i] for i in sorted(self._selected) if i < len(self.filtered)]

    # ── Config ────────────────────────────────────────────────────────────────

    def _config(self):
        ConfigWindow(self, self.cfg, self._cfg_saved)

    def _cfg_saved(self, new_cfg):
        self.cfg = new_cfg
        save_config(new_cfg)

    # ── Download ──────────────────────────────────────────────────────────────

    def _start_dl(self):
        selected = self._get_selected()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione pelo menos um item para baixar.")
            return
        if self._downloading:
            messagebox.showwarning("Aviso", "Um download já está em andamento.")
            return
        self._downloading = True
        self._cancel = False
        self.dl_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.prog_var.set(0)
        threading.Thread(target=self._dl_thread, args=(selected,), daemon=True).start()

    def _do_cancel(self):
        self._cancel = True
        self._log("⚠ Cancelando downloads…")
        self.prog_lbl.config(text="Cancelando…")

    def _dl_thread(self, entries):
        total = len(entries)
        self._log(f"▶ Iniciando download de {total} item(s)…")
        folder = self.cfg.get("download_folder", "m3u_downloads")
        os.makedirs(folder, exist_ok=True)

        for i, entry in enumerate(entries):
            if self._cancel:
                break
            pct = (i / total) * 100
            self.after(0, lambda p=pct: self.prog_var.set(p))
            self.after(0, lambda i=i, t=total, title=entry["title"]:
                self.prog_lbl.config(text=f"[{i+1}/{t}] {title[:40]}"))
            try:
                self._dl_entry(entry, folder)
            except Exception as exc:
                self._log(f"✗ Erro em '{entry['title']}': {exc}")

        self.after(0, self._dl_done)

    def _dl_entry(self, entry, base):
        cmd, ctx = build_ytdlp_command(entry, self.cfg)
        out_dir = ctx["out_dir"]
        os.makedirs(out_dir, exist_ok=True)
        for warning in ctx["warnings"]:
            self._log(f"  ⚠ {warning}")

        self._log(f"↓ Baixando: {entry['title']}")
        proc = _proc.popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self._log(f"  {line}")
            if self._cancel:
                proc.terminate()
                break
        proc.wait()

        if self._cancel:
            self._log(f"⚠ Cancelado: {entry['title']}")
        elif proc.returncode == 0:
            self._log(f"✓ Concluído: {entry['title']}")
        else:
            self._log(f"✗ Falhou (cód {proc.returncode}): {entry['title']}")

    def _dl_done(self):
        self._downloading = False
        self._cancel = False
        self.dl_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.prog_var.set(100)
        self.prog_lbl.config(text="Download concluído!")
        self._log("✔ Processo finalizado.")

    # ── Log ───────────────────────────────────────────────────────────────────

    def _log(self, msg):
        self._log_q.put(msg)

    def _poll_log(self):
        try:
            while True:
                msg = self._log_q.get_nowait()
                self.log_txt.config(state=tk.NORMAL)
                self.log_txt.insert(tk.END, msg + "\n")
                self.log_txt.see(tk.END)
                self.log_txt.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self._poll_log)


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
