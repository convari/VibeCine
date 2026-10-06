# -*- coding: utf-8 -*-
"""Testes da política centralizada de subprocessos (sem janela CMD)."""

import subprocess
import sys
import unittest

from app.core import proc


class TestProcPolicy(unittest.TestCase):
    def test_kwargs_no_windows(self):
        if sys.platform != "win32":
            self.assertEqual(proc.hidden_kwargs_for_tests(), {})
            return
        kw = proc.hidden_kwargs_for_tests()
        self.assertIn("creationflags", kw)
        self.assertEqual(kw["creationflags"] & proc.CREATE_NO_WINDOW,
                         proc.CREATE_NO_WINDOW)
        si = kw["startupinfo"]
        self.assertTrue(si.dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(si.wShowWindow, 0)  # SW_HIDE

    def test_popen_captura_stdout_sem_janela(self):
        # Sem janela (flags) + stdout/stderr capturados normalmente.
        p = proc.popen(
            [sys.executable, "-c", "import sys; print('ok'); sys.stderr.write('warn')"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = p.communicate(timeout=15)
        self.assertIn("ok", out)
        self.assertIn("warn", err)
        self.assertEqual(p.returncode, 0)

    def test_run_capture_output(self):
        r = proc.run([sys.executable, "-c", "print('run-ok')"],
                     capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("run-ok", r.stdout)

    def test_shell_false_preservado(self):
        # comandos são sempre lista → shell=False implícito
        with self.assertRaises(FileNotFoundError):
            proc.popen(["comando_inexistente_xyz_123"])

    def test_cancelamento_compativel(self):
        p = proc.popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        p.terminate()
        p.wait(timeout=10)
        self.assertIsNotNone(p.returncode)


if __name__ == "__main__":
    unittest.main()
