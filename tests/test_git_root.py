import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-git-root.sh"


def test_check_git_root_accepts_this_project():
    result = subprocess.run(
        ["sh", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_check_git_root_rejects_the_home_directory():
    result = subprocess.run(
        ["sh", str(SCRIPT)],
        cwd=Path.home(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Git root is" in result.stderr
