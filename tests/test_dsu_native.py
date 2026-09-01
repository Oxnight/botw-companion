import shutil
import subprocess
import os
import tempfile
import unittest
from pathlib import Path


class NativeDsuTests(unittest.TestCase):
    def compile_and_run(self, test_name, sources):
        compiler = shutil.which("cc") or shutil.which("clang")
        if compiler is None:
            self.skipTest("Aucun compilateur C disponible")

        root = Path(__file__).resolve().parents[1]
        source_root = root / "third_party" / "JoyConDSU" / "Sources" / "JoyConDSU"
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / test_name
            subprocess.run(
                [
                    compiler, "-std=c17", "-Wall", "-Wextra", "-Wpedantic",
                    "-Wconversion", "-Wshadow", "-Werror", f"-I{source_root}",
                    str(root / "tests" / "native" / f"{test_name}.c"),
                    *[str(source_root / source) for source in sources],
                    "-lm", "-lz", "-o", str(executable),
                ],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(executable)], check=True)

    def test_timestamped_motion_pipeline(self):
        self.compile_and_run("test_motion_pipeline", ["motion_pipeline.c"])

    def test_robust_calibration(self):
        self.compile_and_run("test_calibration", ["calibration.c"])

    def test_cemuhook_protocol_and_clients(self):
        if os.name == "nt":
            self.skipTest("Le test zlib natif est exécuté sur les runners POSIX")
        self.compile_and_run(
            "test_dsu_protocol", ["dsu_protocol.c", "dsu_clients.c"]
        )

    def test_internal_telemetry_math(self):
        self.compile_and_run(
            "test_telemetry", ["telemetry.c", "calibration.c"]
        )

    def test_posix_platform_adapters(self):
        if os.name == "nt":
            self.skipTest("Les adaptateurs POSIX sont exécutés sur les runners POSIX")
        self.compile_and_run(
            "test_platform_posix",
            ["platform_socket_posix.c", "platform_runtime_posix.c"],
        )

    def test_windows_platform_adapters_are_c17_syntax_valid(self):
        compiler = shutil.which("cc") or shutil.which("clang")
        if compiler is None:
            self.skipTest("Aucun compilateur C disponible")
        root = Path(__file__).resolve().parents[1]
        source_root = root / "third_party" / "JoyConDSU" / "Sources" / "JoyConDSU"
        stubs = root / "tests" / "native" / "windows_stubs"
        subprocess.run(
            [
                compiler,
                "-std=c17",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Wconversion",
                "-Wshadow",
                "-Werror",
                "-D_WIN32",
                f"-I{stubs}",
                f"-I{source_root}",
                "-fsyntax-only",
                str(source_root / "platform_socket_windows.c"),
                str(source_root / "platform_runtime_windows.c"),
                str(source_root / "dsu_clients.c"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_complete_windows_engine_is_c17_syntax_valid(self):
        compiler = shutil.which("cc") or shutil.which("clang")
        if compiler is None:
            self.skipTest("Aucun compilateur C disponible")
        root = Path(__file__).resolve().parents[1]
        source_root = root / "third_party" / "JoyConDSU" / "Sources" / "JoyConDSU"
        stubs = root / "tests" / "native" / "windows_stubs"
        sources = sorted(source_root.glob("*.c"))
        sources = [
            str(path)
            for path in sources
            if path.name not in {
                "platform_socket_posix.c",
                "platform_runtime_posix.c",
            }
        ]
        subprocess.run(
            [
                compiler,
                "-std=c17",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Wconversion",
                "-Wshadow",
                "-Werror",
                "-D_WIN32",
                f"-I{stubs}",
                f"-I{source_root}",
                "-fsyntax-only",
                *sources,
            ],
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
