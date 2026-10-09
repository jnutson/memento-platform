"""Readiness and draft-PR handoff contracts for the local delivery workflow."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

ROOT = Path(__file__).resolve().parents[1]
TASK_BRANCH = re.compile(r"^codex/[a-z0-9]+(?:[-_][a-z0-9]+)*$")
DEFAULT_RECEIPT = ROOT / ".memento" / "delivery" / "readiness.json"
GIT = shutil.which("git") or "/usr/bin/git"
MAKE = shutil.which("make") or "/usr/bin/make"


class DeliveryError(RuntimeError):
    """A delivery precondition failed without changing repository state."""


def _git(*args: str, root: Path = ROOT, check: bool = True) -> str:
    result = subprocess.run(
        [GIT, *args], cwd=root, text=True, capture_output=True, check=False
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise DeliveryError(detail or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def current_branch(root: Path = ROOT) -> str | None:
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD", root=root, check=False)
    return branch or None


def worktree_is_clean(root: Path = ROOT) -> bool:
    return not _git("status", "--porcelain", "--untracked-files=all", root=root)


def is_linked_worktree(root: Path = ROOT) -> bool:
    git_dir = Path(_git("rev-parse", "--git-dir", root=root))
    common_dir = Path(_git("rev-parse", "--git-common-dir", root=root))
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    if not common_dir.is_absolute():
        common_dir = root / common_dir
    return git_dir.resolve() != common_dir.resolve()


def validate_task_branch(branch: str | None) -> str:
    if branch is None:
        raise DeliveryError("detached HEAD; attach this worktree to codex/<task-name>")
    if branch == "main":
        raise DeliveryError("implementation cannot run on main")
    if not TASK_BRANCH.fullmatch(branch):
        raise DeliveryError("task branch must match codex/<task-name>")
    return branch


@dataclass(frozen=True)
class ReadinessReceipt:
    status: Literal["ready"]
    branch: str
    head: str
    base: str
    commits_ahead: int
    changed_paths: tuple[str, ...]
    verification: str
    checks: dict[str, str]
    completed_at: str


def render_handoff(receipt: ReadinessReceipt) -> str:
    checks = "\n".join(f"- {name}: {result}" for name, result in receipt.checks.items())
    return (
        "## Delivery readiness: READY\n\n"
        f"Branch: `{receipt.branch}` · HEAD: `{receipt.head}` · "
        f"commits ahead: {receipt.commits_ahead}\n\n"
        f"Verification: `{receipt.verification}`\n{checks}\n\n"
        "The operator checks the product and approves merge and deployment separately.\n"
    )


def build_readiness(
    *, base: str, verification: Literal["no-db", "full"], root: Path = ROOT
) -> ReadinessReceipt:
    branch = validate_task_branch(current_branch(root))
    if not worktree_is_clean(root):
        raise DeliveryError("worktree must be clean and all intended changes committed")
    _git("rev-parse", "--verify", base, root=root)
    head = _git("rev-parse", "HEAD", root=root)
    commits_ahead = int(_git("rev-list", "--count", f"{base}..HEAD", root=root))
    if commits_ahead < 1:
        raise DeliveryError(f"branch {branch} has no commits ahead of {base}")
    changed = tuple(
        path
        for path in _git("diff", "--name-only", f"{base}...HEAD", root=root).splitlines()
        if path
    )
    if not changed:
        raise DeliveryError("branch has no changed paths")
    if verification == "no-db" and any(
        path.startswith(("src/", "tests/", "web/")) for path in changed
    ):
        raise DeliveryError("changed paths require VERIFICATION=full")
    command = [MAKE, "verify"] if verification == "full" else [MAKE, "typecheck", "lint", "test-web", "build"]
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode:
        raise DeliveryError(f"{' '.join(command)} failed with exit code {result.returncode}")
    if not worktree_is_clean(root):
        raise DeliveryError("verification changed the worktree")
    checks = {
        "python_tests": "passed" if verification == "full" else "not_applicable_by_path",
        "typecheck": "passed",
        "lint": "passed",
        "frontend_tests": "passed",
        "build": "passed",
        "browser_e2e": "passed" if verification == "full" else "not_applicable_by_path",
        "fullstack_e2e": "passed" if verification == "full" else "not_applicable_by_path",
    }
    receipt = ReadinessReceipt(
        status="ready", branch=branch, head=head, base=base,
        commits_ahead=commits_ahead, changed_paths=changed,
        verification=" ".join(command), checks=checks,
        completed_at=datetime.now(UTC).isoformat(),
    )
    DEFAULT_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_RECEIPT.write_text(json.dumps(asdict(receipt), indent=2) + "\n", encoding="utf-8")
    (DEFAULT_RECEIPT.parent / "handoff.md").write_text(render_handoff(receipt), encoding="utf-8")
    return receipt


def ready_handoff_for_pr(*, root: Path = ROOT) -> str:
    if not is_linked_worktree(root):
        raise DeliveryError("PR handoff requires a linked task worktree")
    branch = validate_task_branch(current_branch(root))
    if not worktree_is_clean(root):
        raise DeliveryError("PR handoff requires a clean worktree")
    receipt_path = root / ".memento" / "delivery" / "readiness.json"
    if not receipt_path.is_file():
        raise DeliveryError("READY receipt is missing; run make delivery-ready")
    try:
        raw: object = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DeliveryError("READY receipt is invalid") from error
    if not isinstance(raw, dict):
        raise DeliveryError("READY receipt is invalid")
    receipt = cast(dict[str, object], raw)
    head = _git("rev-parse", "HEAD", root=root)
    if receipt.get("status") != "ready" or receipt.get("branch") != branch or receipt.get("head") != head:
        raise DeliveryError("READY receipt does not match this branch and HEAD")
    return head


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    ready = commands.add_parser("ready")
    ready.add_argument("--base", default="origin/main")
    ready.add_argument("--verification", choices=("no-db", "full"), default="no-db")
    commands.add_parser("pr-check")
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "ready":
            print(json.dumps(asdict(build_readiness(base=arguments.base, verification=arguments.verification)), indent=2))
        else:
            print(f"READY handoff {ready_handoff_for_pr()}; draft PR handoff may proceed")
    except DeliveryError as error:
        print(f"delivery: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
