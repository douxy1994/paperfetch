from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class SkillInstallerTests(unittest.TestCase):
    def test_active_host_installers_are_shiped(self) -> None:
        for host in ("claude", "codex", "antigravity", "zcode", "hermes"):
            path = REPO_ROOT / "scripts" / f"install-{host}-skill.sh"
            self.assertTrue(path.is_file(), f"missing installer: {path}")

    def test_all_host_installers_are_executable(self) -> None:
        import os

        for host in ("claude", "codex", "antigravity", "zcode", "hermes"):
            path = REPO_ROOT / "scripts" / f"install-{host}-skill.sh"
            self.assertTrue(
                os.access(path, os.X_OK),
                f"{path} must be executable",
            )

    def test_shared_installer_supports_only_active_skill_hosts(self) -> None:
        common = (REPO_ROOT / "scripts" / "_skill_install_common.sh").read_text(encoding="utf-8")

        for host in ("claude", "codex", "antigravity", "zcode", "hermes"):
            self.assertIn(f"{host}) printf", common)

    def test_shared_installer_exposes_home_overrides(self) -> None:
        common = (REPO_ROOT / "scripts" / "_skill_install_common.sh").read_text(encoding="utf-8")

        self.assertIn("ZCODE_HOME", common)
        self.assertIn("HERMES_HOME", common)


if __name__ == "__main__":
    unittest.main()
