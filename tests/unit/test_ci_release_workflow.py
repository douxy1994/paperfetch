from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class CiReleaseWorkflowTests(unittest.TestCase):
    def test_phase8_release_workflow_input_is_absent_in_this_repository(self) -> None:
        self.assertFalse(RELEASE_WORKFLOW.exists())
        self.assertTrue(CI_WORKFLOW.exists())

    def test_windows_offline_ci_uses_current_provider_status_entrypoint(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("from paper_fetch.mcp.fetch_tool import provider_status_payload", workflow)
        self.assertNotIn("from paper_fetch.mcp.tools import provider_status_payload", workflow)

    def test_windows_offline_ci_uses_cloakbrowser_package_smoke(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("import cloakbrowser", workflow)
        self.assertIn('assert hasattr(cloakbrowser, "launch")', workflow)
        self.assertNotIn("playwright.sync_api", workflow)
        self.assertNotIn("ms-playwright", workflow)

    def test_windows_offline_ci_verifies_bundled_mathml_node(self) -> None:
        workflow = CI_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("MATHML_TO_LATEX_NODE_BIN", workflow)
        self.assertIn("runtime/Lib/site-packages/playwright/driver/node.exe", workflow)
        self.assertIn("$mathmlNode --version", workflow)

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
        self.assertNotIn(".tar.gz", workflow)

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
