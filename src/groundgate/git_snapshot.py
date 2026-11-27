"""Deterministic workspace tree-hash snapshotter using isolated git write-tree."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

IGNORED_DIRS = {".git", ".groundgate", ".venv", "__pycache__", "node_modules", ".pytest_cache"}


def capture_tree_hash(repo_root: Path) -> str:
    """Return a deterministic hash of the current workspace tree.

    When ``repo_root`` is inside a Git repository, uses ``git write-tree`` with
    an isolated temporary ``GIT_INDEX_FILE`` so the user's real git index is
    never modified. Falls back to a deterministic SHA-256 directory walk if
    ``repo_root`` is not a Git repository.
    """
    root = repo_root.resolve()
    if (root / ".git").exists():
        return _git_isolated_write_tree(root)
    return _sha256_tree_walk(root)


def _git_isolated_write_tree(root: Path) -> str:
    fd, tmp_index_path = tempfile.mkstemp(prefix="groundgate-idx-")
    os.close(fd)
    # Remove empty placeholder so git initializes a fresh index file cleanly.
    os.unlink(tmp_index_path)

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = tmp_index_path

    try:
        # Stage all non-ignored working-tree files into the temporary index only.
        subprocess.run(
            ["git", "add", "-A"],
            cwd=root,
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Exclude internal gate directories from the temporary index regardless of .gitignore.
        subprocess.run(
            [
                "git",
                "rm",
                "-r",
                "--cached",
                "--ignore-unmatch",
                "-q",
                ".groundgate",
                ".gatekit",
                ".replaygate",
                ".scopegate",
            ],
            cwd=root,
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc = subprocess.run(
            ["git", "write-tree"],
            cwd=root,
            env=env,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return proc.stdout.strip()
    finally:
        if os.path.exists(tmp_index_path):
            os.unlink(tmp_index_path)


def _sha256_tree_walk(root: Path) -> str:
    hasher = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        rel_dir = Path(dirpath).relative_to(root)
        for name in sorted(filenames):
            file_path = Path(dirpath) / name
            if file_path.is_symlink():
                continue
            rel_path = (rel_dir / name).as_posix()
            hasher.update(rel_path.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(file_path.read_bytes())
            hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}"
