import struct
import unittest
from pathlib import Path


class WindowsPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.windows = cls.root / "windows"

    def test_pyinstaller_uses_one_folder_without_a_console(self):
        spec = (self.windows / "BOTW Companion.spec").read_text(encoding="utf-8")
        entry = (self.root / "windows_entry.py").read_text(encoding="utf-8")
        self.assertIn("COLLECT(", spec)
        self.assertIn('name="BOTW Companion"', spec)
        self.assertIn("console=False", spec)
        self.assertIn("exclude_binaries=True", spec)
        self.assertIn("BOTW Companion.ico", spec)
        self.assertNotIn("onefile", spec.casefold())
        self.assertIn("sys.stdout is None", entry)
        self.assertIn("sys.stderr is None", entry)
        self.assertIn("os.devnull", entry)

    def test_every_required_offline_resource_is_collected(self):
        spec = (self.windows / "BOTW Companion.spec").read_text(encoding="utf-8")
        self.assertIn('collect_data_files(', spec)
        self.assertIn('"botw_companion"', spec)
        self.assertIn("JoyConDSU.exe", spec)
        self.assertIn("SDL3.dll", spec)
        self.assertIn("manifest.json", spec)
        self.assertIn("SDL3-LICENSE.txt", spec)

    def test_installer_is_per_user_and_preserves_personal_data(self):
        installer = (self.windows / "BOTW Companion.iss").read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", installer)
        self.assertIn("{localappdata}\\Programs\\BOTW Companion", installer)
        self.assertIn("{group}\\BOTW Companion", installer)
        self.assertIn("{autodesktop}\\BOTW Companion", installer)
        self.assertIn("Tasks: desktopicon", installer)
        self.assertIn("UninstallDisplayIcon={app}", installer)
        self.assertNotIn("[UninstallDelete]", installer)
        self.assertNotIn("{localappdata}\\BOTW Companion\\manual", installer)

    def test_icon_contains_all_required_windows_sizes(self):
        icon = (self.windows / "BOTW Companion.ico").read_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", icon)
        self.assertEqual((reserved, kind), (0, 1))
        sizes = set()
        for index in range(count):
            width, height = struct.unpack_from("<BB", icon, 6 + index * 16)
            sizes.add((256 if width == 0 else width, 256 if height == 0 else height))
        for size in (16, 24, 32, 48, 64, 128, 256):
            self.assertIn((size, size), sizes)

    def test_build_script_validates_the_standalone_package(self):
        script = (self.root / "tools" / "build_windows_app.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('"pyinstaller==6.22.2"', script)
        self.assertIn("--package-self-test", script)
        self.assertIn("cartography_reference_fr_compiled.json", script)
        self.assertIn("JoyConDSU.exe", script)
        self.assertIn("SDL3.dll", script)
        self.assertIn("ISCC", script)
        self.assertIn('foreach ($documentName in @("LICENSE", "THIRD_PARTY_NOTICES.md"))', script)
        self.assertIn("Copy-Item -LiteralPath $documentSource", script)
        self.assertNotIn('project_root / "LICENSE"', (
            self.windows / "BOTW Companion.spec"
        ).read_text(encoding="utf-8"))

    def test_inno_setup_ci_reuses_the_runner_installation(self):
        script = (self.root / "tools" / "install_inno_setup_ci.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('${env:ProgramFiles(x86)}', script)
        self.assertIn('$env:ProgramFiles', script)
        self.assertIn('$env:GITHUB_PATH', script)
        self.assertIn('Test-Path -LiteralPath $_ -PathType Leaf', script)

    def test_local_build_produces_and_validates_application_and_installer(self):
        build = (self.root / "tools" / "build_windows_app.ps1").read_text(
            encoding="utf-8"
        )
        validation = (
            self.root / "tools" / "test_windows_installation.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("BOTW Companion.spec", build)
        self.assertIn("BOTW Companion.exe", validation)
        self.assertIn("Setup.exe", validation)
        self.assertIn("--package-self-test", validation)
        self.assertIn("--list-controllers", validation)
        self.assertIn("/api/version", validation)
        self.assertIn("/api/shutdown", validation)
        self.assertIn('$applicationLicense = Join-Path $installRoot "LICENSE"', validation)
        self.assertIn('$thirdPartyNotices = Join-Path $installRoot "THIRD_PARTY_NOTICES.md"', validation)

    def test_clean_machine_validation_removes_development_tools_from_path(self):
        script = (self.root / "tools" / "test_windows_installation.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("$env:SystemRoot\\System32;$env:SystemRoot", script)
        self.assertIn("--package-self-test", script)
        self.assertIn("/VERYSILENT", script)
        self.assertIn("donnees-a-conserver.json", script)
        self.assertNotIn("RunAs", script)

    def test_release_workflow_builds_tests_and_publishes_only_a_tag(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("windows-2022", workflow)
        self.assertIn("tools/build_windows_app.ps1", workflow)
        self.assertIn("tools/test_windows_installation.ps1", workflow)
        self.assertIn("tools/check_version_consistency.py", workflow)
        self.assertIn("refs/tags/", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("needs: [windows, macos]", workflow)

    def test_browser_suite_covers_the_complete_user_path(self):
        script = (self.root / "tools" / "browser_smoke.js").read_text(encoding="utf-8")
        markup = (self.root / "botw_companion" / "web" / "index.html").read_text(encoding="utf-8")
        for selector in (
            "#bloodMoonCountdown", "#syncStatus", "#zoomIn", "#mapReset",
            "#manualComplete", "#detailRoute", "#closeDetails", "#toggleRoute",
            "#routeSessionSelect", "/api/routes/export", "/api/routes/import",
            "#toggleDsu",
        ):
            self.assertIn(selector, script)
        self.assertIn("width: 390", script)
        self.assertIn('getByRole("complementary")', script)
        self.assertIn('getByRole("main")', script)
        self.assertNotIn('querySelector(".sidebar")', script)
        self.assertIn("conteneurs suspects", script)
        self.assertIn("Le planificateur déborde", script)
        self.assertIn("BOTW_BROWSER_TEST_TIMEOUT_MS", script)
        self.assertIn("context.setDefaultTimeout", script)
        self.assertIn("AbortController", script)
        self.assertIn("closeWithTimeout", script)
        self.assertIn('status: "progress"', script)
        self.assertIn("<aside>", markup)
        self.assertIn("<main>", markup)

    def test_narrow_layout_cannot_restore_wide_grids(self):
        styles = (self.root / "botw_companion" / "web" / "armor.css").read_text(
            encoding="utf-8"
        )
        wide_breakpoint = styles.index("@media(max-width:1000px)")
        narrow_breakpoint = styles.index("@media(max-width:600px)", wide_breakpoint)
        narrow_rules = styles[narrow_breakpoint:]
        self.assertIn("grid-template-columns: minmax(0, 1fr);", narrow_rules)
        self.assertIn("grid-template-columns: 82px minmax(0, 1fr);", narrow_rules)
        self.assertIn("header > div:first-child", narrow_rules)
        self.assertIn("overflow-wrap: anywhere;", narrow_rules)
        self.assertIn(".toolbar > *", narrow_rules)
        self.assertIn(".routeSessions", narrow_rules)
        self.assertIn(".routeHeader > button", narrow_rules)
        self.assertIn("word-break: break-word", narrow_rules)
        self.assertIn(".officialMetric label", narrow_rules)
        self.assertIn(".companionMetric label", narrow_rules)
        self.assertIn(".metric select", narrow_rules)


if __name__ == "__main__":
    unittest.main()
