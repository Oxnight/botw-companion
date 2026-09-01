import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from botw_companion.offline_runtime import (
    offline_resource_errors,
    remote_runtime_dependencies,
    windows_dsu_errors,
)


class OfflineRuntimeTests(unittest.TestCase):
    def test_every_core_resource_and_hd_tile_is_packaged(self):
        self.assertEqual(offline_resource_errors(), [])

    def test_interface_has_no_automatic_remote_dependency(self):
        self.assertEqual(remote_runtime_dependencies(), [])

    def test_windows_dsu_manifest_authenticates_both_native_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / "JoyConDSU.exe"
            library = root / "SDL3.dll"
            executable.write_bytes(b"MZ-native-engine")
            library.write_bytes(b"MZ-sdl-runtime")
            (root / "SDL3-LICENSE.txt").write_text(
                "SDL zlib license fixture", encoding="utf-8"
            )
            manifest = {
                "schema_version": 1,
                "architecture": "x64",
                "protocol": 1001,
                "port": 26760,
                "executable_sha256": hashlib.sha256(
                    executable.read_bytes()
                ).hexdigest(),
                "sdl_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
            }
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            self.assertEqual(windows_dsu_errors(root), [])
            library.write_bytes(b"MZ-corrupted")
            self.assertEqual(
                windows_dsu_errors(root),
                ["Empreinte DSU Windows invalide : SDL3.dll"],
            )


if __name__ == "__main__":
    unittest.main()
