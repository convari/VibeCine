# -*- coding: utf-8 -*-
"""Núcleo do VibeCine: config, parser, URLs, extração e download.

Estes módulos não dependem de interface gráfica e são 100% testáveis.
"""

from . import (config, downloader, errors, extractor, history, m3u_parser,
               share, tools, url_router)  # noqa: F401
