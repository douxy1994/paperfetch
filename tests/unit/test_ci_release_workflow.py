from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
LINUX_OFFLINE_VERIFY = REPO_ROOT / "scripts" / "verify-offline-package.sh"


class CiReleaseWorkflowTests(unittest.TestCase):
    def test_phase8_release_workflow_input_is_absent_in_this_repository(self) -> None:
        self.assertFalse(RELEASE_WORKFLOW.exists())
        self.assertTrue(CI_WORKFLOW.exists())

    def test_windows_offline_ci_uses_current_provider_status_entrypoint(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("from paper_fetch.mcp.fetch_tool import provider_status_payload", workflow)
        self.assertIn("Invoke-RuntimePythonScript -Script $providerStatusCheck", workflow)
        self.assertNotIn('& $runtimePython -X utf8 -c "import paper_fetch', workflow)
        self.assertNotIn("from paper_fetch.mcp.tools import provider_status_payload", workflow)

    def test_windows_offline_ci_uses_cloakbrowser_package_smoke(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("import cloakbrowser", workflow)
        self.assertIn('assert hasattr(cloakbrowser, "launch")', workflow)
        self.assertIn("Invoke-RuntimePythonScript -Script $cloakbrowserCheck", workflow)
        self.assertNotIn("& $runtimePython -X utf8 -c $cloakbrowserCheck", workflow)
        self.assertNotIn("playwright.sync_api", workflow)
        self.assertNotIn("ms-playwright", workflow)

    def test_windows_offline_ci_verifies_bundled_mathml_node(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("MATHML_TO_LATEX_NODE_BIN", workflow)
        self.assertIn("runtime/Lib/site-packages/playwright/driver/node.exe", workflow)
        self.assertIn("$mathmlNode --version", workflow)

    def test_offline_ci_verifies_default_browser_user_agent(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")
        linux_verify = LINUX_OFFLINE_VERIFY.read_text(encoding="utf-8")

        self.assertIn("PAPER_FETCH_BROWSER_USER_AGENT", workflow)
        self.assertIn("offline.env managed block does not enable default browser UA", workflow)
        self.assertIn("PAPER_FETCH_BROWSER_USER_AGENT", linux_verify)
        self.assertIn("Offline install did not enable default browser UA", linux_verify)

    def test_linux_offline_ci_verifies_runtime_package_layout(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Verify Linux runtime package layout", workflow)
        self.assertIn(".sh", workflow)
        self.assertIn("--install-dir \"$install_root\"", workflow)
        self.assertIn("/runtime/site-packages/paper_fetch/__init__.py", workflow)
        self.assertIn("/bin/paper-fetch", workflow)
        self.assertIn("/bin/paper-fetch-install-formula-tools", workflow)
        self.assertIn("Linux runtime package must not include source/build path", workflow)
        self.assertNotIn("tar -tzf", workflow)
        self.assertNotIn("paper-fetch-skill-offline-linux-x86_64-${{ matrix.python-tag }}.tar.gz", workflow)

    def test_macos_offline_ci_verifies_headful_install_layout_and_uploads_release_asset(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("offline-macos-install:", workflow)
        self.assertIn("runs-on: macos-latest", workflow)
        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn("Build macOS offline package", workflow)
        self.assertIn("paper-fetch-skill-offline-macos-$package_arch-cp312.tar.gz", workflow)
        self.assertIn("--preset=headful", workflow)
        self.assertIn('CLOAKBROWSER_HEADLESS="false"', workflow)
        self.assertIn("macOS runtime package must not include source/build path", workflow)
        self.assertIn("- offline-macos-install", workflow)
        self.assertIn("Upload macOS offline package", workflow)
        self.assertIn("name: paper-fetch-skill-offline-macos-cp312", workflow)
        self.assertIn("path: offline-artifacts/paper-fetch-skill-offline-macos-*-cp312.tar.gz", workflow)

    def test_release_asset_set_includes_one_macos_cp312_tarball(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("macos_assets=(release-artifacts/paper-fetch-skill-offline-macos-*-cp312.tar.gz)", workflow)
        self.assertIn("Expected exactly one macOS cp312 release asset", workflow)
        self.assertIn("paper-fetch-skill-offline-macos-arm64-cp312.tar.gz", workflow)
        self.assertIn("paper-fetch-skill-offline-macos-x86_64-cp312.tar.gz", workflow)
        self.assertIn('expected_count="$((${#expected[@]} + ${#macos_assets[@]}))"', workflow)
        self.assertIn('Expected $expected_count release assets', workflow)

    def test_macos_offline_ci_runs_installed_package_browser_smoke(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Verify macOS installed package browser smoke", workflow)
        self.assertIn("CLOAKBROWSER_BINARY_PATH=\"$browser_binary\"", workflow)
        self.assertIn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", workflow)
        self.assertIn("source \"$install_root/activate-offline.sh\"", workflow)
        self.assertIn("paper-fetch --help >/dev/null", workflow)
        self.assertIn("from paper_fetch._cloakbrowser_runtime import import_cloakbrowser", workflow)
        self.assertIn("cloakbrowser.launch(headless=True)", workflow)
        self.assertIn("data:text/html,<title>paper-fetch macOS browser smoke</title>", workflow)
        self.assertIn("\n          from pathlib import Path\n", workflow)
        self.assertIn("\n          PY\n\n      - name: Upload macOS offline package", workflow)
        self.assertNotIn("\nfrom pathlib import Path\n", workflow)

    def test_windows_offline_ci_verifies_runtime_only_package_layout(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Windows installer is missing runtime path", workflow)
        self.assertIn("runtime/Lib/site-packages/paper_fetch/__init__.py", workflow)
        self.assertIn("bin/paper-fetch.cmd", workflow)
        self.assertIn("skills/paper-fetch-skill/SKILL.md", workflow)
        self.assertIn("scripts/windows-installer-helper.ps1", workflow)
        self.assertIn("Windows runtime package must not include source/build path", workflow)
        self.assertIn("pyproject.toml", workflow)


if __name__ == "__main__":
    unittest.main()
