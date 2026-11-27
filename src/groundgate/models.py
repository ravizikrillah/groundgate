"""Core data models for GroundGate claims, ledger records, and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Diagnostic severity levels."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Diagnostic:
    """Structured compiler diagnostic returned when a claim fails verification."""

    code: str
    message: str
    line: int
    severity: Severity = Severity.ERROR
    claim_text: str = ""
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "line": self.line,
            "claim_text": self.claim_text,
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


@dataclass(frozen=True)
class CompileResult:
    """Result of running GroundGate over a candidate Markdown draft."""

    passed: bool
    current_tree_hash: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "current_tree_hash": self.current_tree_hash,
            "stats": self.stats,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }

    def format_feedback(self) -> str:
        """Format diagnostics as concise 1-turn self-fix feedback for an AI agent."""
        if self.passed:
            return f"PASS (tree={self.current_tree_hash[:12]}): All claims verified."
        lines = [
            f"FAIL (tree={self.current_tree_hash[:12]}): "
            f"{len(self.diagnostics)} ungrounded claim(s) blocked pre-emission:"
        ]
        for idx, diag in enumerate(self.diagnostics, start=1):
            lines.append(f"{idx}. [{diag.code}] line {diag.line}: {diag.message}")
            if diag.fix_hint:
                lines.append(f"   Fix: {diag.fix_hint}")
        return "\n".join(lines)


@dataclass(frozen=True)
class FileLinkClaim:
    """A Markdown file:// or relative file link with optional line span."""

    line: int
    label: str
    raw_target: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    clause_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class TestAssertionClaim:
    """A natural-language claim asserting test or build pass/completion."""

    line: int
    clause: str
    claimed_passed: int | None = None
    claimed_total: int | None = None
    claimed_failed: int | None = None
    kind: str = "test"  # "test" or "build"


@dataclass(frozen=True)
class UrlClaim:
    """An external http(s):// URL cited in the Markdown draft."""

    line: int
    url: str


@dataclass(frozen=True)
class ExtractedClaims:
    """All structured claims extracted from a Markdown draft."""

    file_links: list[FileLinkClaim] = field(default_factory=list)
    test_assertions: list[TestAssertionClaim] = field(default_factory=list)
    urls: list[UrlClaim] = field(default_factory=list)
