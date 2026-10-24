import builtins
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import traceback
import types
import unittest
from unittest.mock import patch


ENTRY = Path(__file__).resolve().parents[1] / "windows_entry.py"
STARTUP = "Laisse ce terminal ouvert. Ctrl+C pour arrêter."
DIAGNOSTIC = "Échec : sauvegarde — Игрок — 日本語 — 🎮"


class WindowsOutputTests(unittest.TestCase):
    def run_entry(self, callback):
        application = types.ModuleType("botw_companion.windows_app")
        application.main = callback
        with patch.dict(sys.modules, {application.__name__: application}):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(ENTRY), run_name="__main__")
        self.assertEqual(result.exception.code, 0)

    def test_cp1251_strict_reproduces_the_reported_startup_error(self):
        with io.TextIOWrapper(io.BytesIO(), encoding="cp1251", errors="strict") as output:
            with self.assertRaises(UnicodeEncodeError) as result:
                print(STARTUP, file=output)
        self.assertEqual(result.exception.start, 42)
        self.assertEqual(result.exception.object[42], "\xea")
        self.assertEqual(
            str(result.exception),
            "'charmap' codec can't encode character '\\xea' in position 42: character maps to <undefined>",
        )

    def test_unicode_output_is_ready_before_application_import(self):
        original_import = builtins.__import__
        imported = []
        output_bytes, error_bytes = io.BytesIO(), io.BytesIO()
        output = io.TextIOWrapper(output_bytes, encoding="cp1251", errors="strict")
        error = io.TextIOWrapper(error_bytes, encoding="cp1251", errors="strict")

        def import_module(name, *args, **kwargs):
            if name == "botw_companion.windows_app":
                imported.append(name)
                print(STARTUP)
                print(DIAGNOSTIC, file=sys.stderr)
            return original_import(name, *args, **kwargs)

        try:
            with patch.object(sys, "stdout", output), patch.object(sys, "stderr", error), \
                    patch.object(builtins, "__import__", side_effect=import_module):
                self.run_entry(lambda: 0)
                output.flush()
                error.flush()
            self.assertEqual(imported, ["botw_companion.windows_app"])
            self.assertEqual(output_bytes.getvalue().decode("utf-8").strip(), STARTUP)
            self.assertEqual(error_bytes.getvalue().decode("utf-8").strip(), DIAGNOSTIC)
        finally:
            output.close()
            error.close()

    def test_isolated_interpreter_does_not_need_encoding_environment_variables(self):
        script = f"""
import runpy, sys, types
assert sys.flags.ignore_environment
sys.stdout.reconfigure(encoding='cp1251', errors='strict')
sys.stderr.reconfigure(encoding='cp1251', errors='strict')
application = types.ModuleType('botw_companion.windows_app')
def main():
    print({STARTUP!r})
    print({DIAGNOSTIC!r}, file=sys.stderr)
    return 0
application.main = main
sys.modules[application.__name__] = application
runpy.run_path(sys.argv[1], run_name='__main__')
"""
        result = subprocess.run(
            [sys.executable, "-I", "-c", script, str(ENTRY)],
            env={**os.environ, "PYTHONIOENCODING": "cp1251:strict", "PYTHONUTF8": "0"},
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.decode("utf-8").strip(), STARTUP)
        self.assertEqual(result.stderr.decode("utf-8").strip(), DIAGNOSTIC)

    def test_legacy_redirected_streams_preserve_unicode_before_dispatch(self):
        for encoding in ("cp1251", "cp1252", "ascii", "utf-8"):
            with self.subTest(encoding=encoding):
                output_bytes, error_bytes = io.BytesIO(), io.BytesIO()
                output = io.TextIOWrapper(output_bytes, encoding=encoding, errors="strict")
                error = io.TextIOWrapper(error_bytes, encoding=encoding, errors="strict")

                def main():
                    print(STARTUP)
                    try:
                        raise RuntimeError(DIAGNOSTIC)
                    except RuntimeError:
                        traceback.print_exc()
                    sys.stdout.flush()
                    sys.stderr.flush()
                    return 0

                try:
                    with patch.object(sys, "stdout", output), patch.object(sys, "stderr", error):
                        self.run_entry(main)
                        self.assertIs(sys.stdout, output)
                        self.assertIs(sys.stderr, error)
                    self.assertEqual(output_bytes.getvalue().decode("utf-8").strip(), STARTUP)
                    self.assertIn(DIAGNOSTIC, error_bytes.getvalue().decode("utf-8"))
                finally:
                    output.close()
                    error.close()

    def test_unpaired_surrogate_does_not_break_diagnostics(self):
        data = io.BytesIO()
        output = io.TextIOWrapper(data, encoding="cp1251")

        def main():
            print("path: \udcff")
            return 0

        try:
            with patch.object(sys, "stdout", output):
                self.run_entry(main)
                output.flush()
            self.assertIn(b"\\udcff", data.getvalue())
        finally:
            output.close()

    def test_windowed_missing_streams_remain_writable(self):
        opened = []

        def main():
            opened.extend((sys.stdout, sys.stderr))
            print(STARTUP)
            print(DIAGNOSTIC, file=sys.stderr)
            return 0

        try:
            with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
                self.run_entry(main)
            self.assertEqual(len(opened), 2)
            self.assertTrue(all(stream.encoding == "utf-8" for stream in opened))
        finally:
            for stream in opened:
                stream.close()

    def test_custom_text_capture_is_not_replaced_or_closed(self):
        output, error = io.StringIO(), io.StringIO()

        def main():
            print(DIAGNOSTIC)
            print(DIAGNOSTIC, file=sys.stderr)
            return 0

        with patch.object(sys, "stdout", output), patch.object(sys, "stderr", error):
            self.run_entry(main)
            self.assertIs(sys.stdout, output)
            self.assertIs(sys.stderr, error)
        self.assertFalse(output.closed)
        self.assertFalse(error.closed)
        self.assertEqual(output.getvalue().strip(), DIAGNOSTIC)
        self.assertEqual(error.getvalue().strip(), DIAGNOSTIC)
