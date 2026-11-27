"""Append-only JSONL session trace ledger for commands, edits, and tool observations."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from groundgate.git_snapshot import capture_tree_hash

URL_RE = re.compile(r"https?://[^\s<>()\[\]\"'`]+")

# Deterministic output parsers for common test runners.
_PYTEST_PASSED_RE = re.compile(r"(\d+)\s+passed")
_PYTEST_FAILED_RE = re.compile(r"(\d+)\s+(?:failed|error(?:s)?)")
_JEST_TESTS_RE = re.compile(r"Tests:\s+(?:(\d+)\s+failed,\s+)?(\d+)\s+passed,\s+(\d+)\s+total")
_CARGO_TEST_RE = re.compile(r"test result:\s+\w+\.\s+(\d+)\s+passed;\s+(\d+)\s+failed;")
_GO_PASS_LINE_RE = re.compile(r"^(?:ok|---\s+PASS:)\s+", re.MULTILINE)
_GO_FAIL_LINE_RE = re.compile(r"^(?:FAIL|---\s+FAIL:)\s+", re.MULTILINE)

TEST_CMD_HINTS = ("pytest", "go test", "npm test", "pnpm test", "vitest", "jest", "cargo test", "unittest")
BUILD_CMD_HINTS = ("go build", "npm run build", "cargo build", "tsc", "vite build", "uv build", "make build")


def extract_urls(text: str) -> list[str]:
    """Extract normalized http(s) URLs from raw text, stripping trailing punctuation."""
    urls: list[str] = []
    for match in URL_RE.findall(text):
        cleaned = match.rstrip(".,;:!?")
        if cleaned and cleaned not in urls:
            urls.append(cleaned)
    return urls


def classify_command_kind(command_str: str) -> str:
    lowered = command_str.lower()
    if any(hint in lowered for hint in TEST_CMD_HINTS):
        return "test"
    if any(hint in lowered for hint in BUILD_CMD_HINTS):
        return "build"
    return "command"


def parse_test_counts(output: str) -> dict[str, int]:
    """Extract deterministic pass/fail/total counts from raw test runner stdout/stderr."""
    counts: dict[str, int] = {}

    if jest_match := _JEST_TESTS_RE.search(output):
        failed = int(jest_match.group(1) or 0)
        passed = int(jest_match.group(2))
        total = int(jest_match.group(3))
        return {"passed": passed, "failed": failed, "total": total}

    if cargo_match := _CARGO_TEST_RE.search(output):
        passed = int(cargo_match.group(1))
        failed = int(cargo_match.group(2))
        return {"passed": passed, "failed": failed, "total": passed + failed}

    passed_match = _PYTEST_PASSED_RE.search(output)
    failed_match = _PYTEST_FAILED_RE.search(output)
    if passed_match or failed_match:
        passed = int(passed_match.group(1)) if passed_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
        counts = {"passed": passed, "failed": failed, "total": passed + failed}
        return counts

    go_passes = len(_GO_PASS_LINE_RE.findall(output))
    go_fails = len(_GO_FAIL_LINE_RE.findall(output))
    if go_passes or go_fails:
        return {"passed": go_passes, "failed": go_fails, "total": go_passes + go_fails}

    return counts


@dataclass
class LedgerEntry:
    """Single recorded event in the GroundGate session ledger."""

    kind: str  # "command" | "observation" | "mutation"
    timestamp: float = field(default_factory=time.time)
    tree_hash: str = ""
    command: str = ""
    command_kind: str = ""
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    parsed_counts: dict[str, int] = field(default_factory=dict)
    source: str = ""
    observed_urls: list[str] = field(default_factory=list)
    observed_text: str = ""
    path: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LedgerEntry:
        return cls(**data)


class SessionLedger:
    """Manages reading and appending to ``.groundgate/session.jsonl``."""

    def __init__(self, repo_root: Path, ledger_path: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.ledger_path = ledger_path or (self.repo_root / ".groundgate" / "session.jsonl")

    def init(self, reset: bool = False) -> Path:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if reset or not self.ledger_path.exists():
            self.ledger_path.write_text("", encoding="utf-8")
        return self.ledger_path

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")
        return entry

    def record_command(
        self,
        command: str | list[str],
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        tree_hash: str | None = None,
        command_kind: str | None = None,
    ) -> LedgerEntry:
        cmd_str = command if isinstance(command, str) else " ".join(command)
        resolved_hash = tree_hash or capture_tree_hash(self.repo_root)
        combined_out = f"{stdout}\n{stderr}".strip()
        entry = LedgerEntry(
            kind="command",
            tree_hash=resolved_hash,
            command=cmd_str,
            command_kind=command_kind or classify_command_kind(cmd_str),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            parsed_counts=parse_test_counts(combined_out),
            observed_urls=extract_urls(combined_out),
        )
        return self.append(entry)

    def record_observation(
        self,
        source: str,
        text: str,
        urls: list[str] | None = None,
    ) -> LedgerEntry:
        found_urls = extract_urls(text)
        for u in urls or []:
            cleaned = u.strip().rstrip(".,;:!?")
            if cleaned and cleaned not in found_urls:
                found_urls.append(cleaned)
        entry = LedgerEntry(
            kind="observation",
            source=source,
            observed_urls=found_urls,
            observed_text=text,
        )
        return self.append(entry)

    def record_mutation(self, source: str, path: str, tree_hash: str | None = None) -> LedgerEntry:
        resolved_hash = tree_hash or capture_tree_hash(self.repo_root)
        entry = LedgerEntry(
            kind="mutation",
            source=source,
            path=path,
            tree_hash=resolved_hash,
        )
        return self.append(entry)

    def load_entries(self) -> list[LedgerEntry]:
        if not self.ledger_path.exists():
            return []
        entries: list[LedgerEntry] = []
        for raw_line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            entries.append(LedgerEntry.from_dict(json.loads(line)))
        return entries

    def observed_urls(self) -> set[str]:
        urls: set[str] = set()
        for entry in self.load_entries():
            urls.update(entry.observed_urls)
        return urls

    def latest_commands(self, command_kind: str | None = None) -> list[LedgerEntry]:
        cmds = [e for e in self.load_entries() if e.kind == "command"]
        if command_kind is not None:
            cmds = [c for c in cmds if c.command_kind == command_kind]
        return list(reversed(cmds))
