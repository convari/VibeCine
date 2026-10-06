#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point do APK VibeCine (python-for-android / Buildozer).

O p4a exige main.py na raiz do source.dir. Este arquivo é usado APENAS no
build do Android — a versão Windows roda via vibcine.py (inalterada).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from android.main import run

if __name__ == "__main__":
    run()
