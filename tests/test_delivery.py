from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.delivery import DeliveryError, build_readiness, ready_handoff_for_pr

GIT = shutil.which("git") or "/usr/bin/git"


def git(root: Path, *args: str) -> str:
    return subprocess.run([GIT, *args], cwd=root, check=True, text=True, capture_output=True).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "delivery@test")
    git(tmp_path, "config", "user.name", "Delivery Test")
    (tmp_path / "seed.txt").write_text("seed\n")
    git(tmp_path, "add", "seed.txt"); git(tmp_path, "commit", "-qm", "seed")
    return tmp_path


def test_readiness_requires_clean_committed_change(repository: Path, monkeypatch: pytest.MonkeyPatch):
    git(repository, "switch", "-qc", "codex/test_task")
    (repository / "docs").mkdir(); (repository / "docs" / "change.md").write_text("change\n")
    with pytest.raises(DeliveryError, match="clean"):
        build_readiness(base="main", verification="no-db", root=repository)


def test_pr_check_requires_linked_worktree_and_exact_head(repository: Path):
    with pytest.raises(DeliveryError, match="linked task worktree"):
        ready_handoff_for_pr(root=repository)
    linked = repository.parent / "linked"
    git(repository, "worktree", "add", "--detach", "-q", str(linked))
    git(linked, "switch", "-qc", "codex/pr_task")
    (repository / ".git" / "info" / "exclude").write_text(".memento/\n")
    receipt = linked / ".memento" / "delivery" / "readiness.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"status": "ready", "branch": "codex/pr_task", "head": git(linked, "rev-parse", "HEAD")}))
    assert ready_handoff_for_pr(root=linked) == git(linked, "rev-parse", "HEAD")
