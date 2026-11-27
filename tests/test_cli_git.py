import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gitgen.git_collector import parse_status

MAIN = Path(__file__).resolve().parents[1] / "main.py"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def run_cli(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MAIN), *args], cwd=repo, capture_output=True,
                          text=True, env=env or os.environ.copy())


class StatusParseTest(unittest.TestCase):
    def test_parses_branch_and_rename(self):
        branch, files = parse_status("## feature/x...origin/feature/x\n M a.py\nR  old.py -> new.py\n?? n.txt\n")
        self.assertEqual(branch, "feature/x")
        self.assertEqual([f.path for f in files], ["a.py", "new.py", "n.txt"])
        self.assertEqual(files[2].label, "신규(untracked)")


class CliGitFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "config", "user.name", "t")
        (self.repo / "app.py").write_text("print('hi')\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_changes_prints_message_and_exits_zero(self):
        result = run_cli(self.repo, "commit")
        self.assertEqual(result.returncode, 0)
        self.assertIn("변경 사항이 없습니다", result.stderr)

    def test_missing_api_key_error(self):
        (self.repo / "app.py").write_text("print('bye')\n")
        env = {k: v for k, v in os.environ.items() if k != "AI_API_KEY"}
        result = run_cli(self.repo, "commit", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.", result.stderr)

    def test_dry_run_includes_diff_and_masks_in_safe_mode(self):
        (self.repo / "app.py").write_text("TOKEN = 'abcdef123456'\nprint('bye')\n")
        result = run_cli(self.repo, "commit", "--dry-run", "--safe-mode")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[MASKED_SECRET]", result.stdout)
        self.assertNotIn("abcdef123456", result.stdout)

    def test_not_repo_root_error(self):
        sub = self.repo / "sub"
        sub.mkdir()
        result = run_cli(sub, "commit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("프로젝트 루트", result.stderr)


if __name__ == "__main__":
    unittest.main()
