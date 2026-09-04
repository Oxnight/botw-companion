import struct
import unittest
from pathlib import Path


class MacOSBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.macos = cls.root / "macos"

    def test_pyinstaller_build_is_windowed_arm64_and_self_contained(self):
        spec = (self.macos / "BOTW Companion.spec").read_text(encoding="utf-8")
        entry = (self.root / "macos_entry.py").read_text(encoding="utf-8")
        self.assertIn("BUNDLE(", spec)
        self.assertIn("COLLECT(", spec)
        self.assertIn('target_arch="arm64"', spec)
        self.assertIn("console=False", spec)
        self.assertIn('"LSMinimumSystemVersion": "14.0"', spec)
        self.assertIn('version="0.40.0"', spec)
        self.assertIn('"CFBundleShortVersionString": "0.40.0"', spec)
        self.assertIn('"CFBundleVersion": "24"', spec)
        self.assertNotIn('CFBundleShortVersionString": "0.40.0-alpha.24"', spec)
        self.assertIn("JoyConDSU", spec)
        self.assertIn("libSDL3.0.dylib", spec)
        self.assertIn("sys.stdout is None", entry)
        self.assertIn("os.devnull", entry)

    def test_application_icon_is_complete(self):
        icon = (self.macos / "BOTW Companion.icns").read_bytes()
        self.assertEqual(icon[:4], b"icns")
        self.assertEqual(struct.unpack(">I", icon[4:8])[0], len(icon))
        for representation in (
            b"icp4", b"icp5", b"icp6", b"ic07", b"ic08", b"ic09",
            b"ic10", b"ic11", b"ic12", b"ic13", b"ic14",
        ):
            self.assertIn(representation, icon)

    def test_native_build_pins_sdl_and_rewrites_the_runtime_path(self):
        script = (self.root / "tools" / "build_joycon_dsu_macos.sh").read_text(encoding="utf-8")
        cmake = (self.root / "third_party" / "JoyConDSU" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("SDL3-3.4.14.tar.gz", cmake)
        self.assertIn("CMAKE_OSX_ARCHITECTURES=arm64", script)
        self.assertIn("@loader_path/libSDL3.0.dylib", script)
        self.assertIn("lipo -archs", script)
        self.assertIn("codesign --force --sign -", script)
        self.assertIn("grep -E '/opt/homebrew|/usr/local|/Users/'", script)

    def test_dmg_build_and_clean_install_are_exercised(self):
        build = (self.root / "tools" / "build_macos_app.sh").read_text(encoding="utf-8")
        validation = (self.root / "tools" / "test_macos_installation.sh").read_text(encoding="utf-8")
        self.assertIn("hdiutil create", build)
        self.assertIn("BOTW_Companion_0.40.0-alpha.24_macOS_arm64.dmg", build)
        self.assertIn("/Applications", build)
        self.assertIn('codesign --force --sign - "$PACKAGED_SDL"', build)
        self.assertIn('codesign --force --sign - "$PACKAGED_DSU"', build)
        self.assertIn('codesign --force --sign - "$APPLICATION"', build)
        self.assertNotIn("codesign --force --deep --sign", build)
        self.assertIn('manifest["executable_sha256"]', build)
        self.assertIn('manifest["sdl_sha256"]', build)
        self.assertIn("--package-self-test", validation)
        self.assertIn('PATH="/usr/bin:/bin"', validation)
        self.assertIn("--list-controllers", validation)
        self.assertIn("/api/version", validation)
        self.assertIn("/api/shutdown", validation)
        self.assertIn("codesign --verify", validation)
        self.assertIn("CFBundleShortVersionString", validation)
        self.assertIn("find \"$APPLICATION\" -type f -print0", validation)
        self.assertIn("Binaire non arm64 dans l'application", validation)

    def test_release_waits_for_windows_and_macos(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: macos-14", workflow)
        self.assertIn('test "$(uname -m)" = "arm64"', workflow)
        self.assertIn("./tools/build_macos_app.sh", workflow)
        self.assertIn("./tools/test_macos_installation.sh", workflow)
        self.assertIn("timeout-minutes: 10", workflow)
        self.assertIn("BOTW_BROWSER_TEST_TIMEOUT_MS=120000", workflow)
        self.assertIn('browser-test-$browser.log', workflow)
        self.assertIn("stop_server", workflow)
        self.assertIn("needs: [windows, macos]", workflow)
        self.assertIn("gh release create", workflow)

    def test_source_tree_has_no_clone_dependent_macos_launcher(self):
        launcher = (self.root / "botw_companion" / "macos_launcher.py").read_text(encoding="utf-8")
        manager = (self.root / "botw_companion" / "dsu" / "manager.py").read_text(encoding="utf-8")
        combined = launcher + manager
        self.assertNotIn("/Users/oxnight", combined)
        self.assertNotIn("/opt/homebrew", combined)
        self.assertNotIn(".venv", combined)
        self.assertIn("PYINSTALLER_RESET_ENVIRONMENT", launcher)


if __name__ == "__main__":
    unittest.main()
