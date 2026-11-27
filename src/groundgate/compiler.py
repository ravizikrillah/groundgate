"""Main GroundGate Pre-Emission Markdown Compiler."""

from __future__ import annotations

from pathlib import Path

from groundgate.extractor import extract_claims
from groundgate.git_snapshot import capture_tree_hash
from groundgate.ledger import SessionLedger
from groundgate.models import CompileResult
from groundgate.verifiers.causal import verify_causal_freshness
from groundgate.verifiers.fs_ast import verify_file_links
from groundgate.verifiers.provenance import verify_url_provenance


class GroundGate:
    """Deterministic compiler that verifies candidate Markdown drafts pre-emission."""

    def __init__(self, repo_root: Path, ledger_path: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.ledger = SessionLedger(self.repo_root, ledger_path=ledger_path)

    def compile(self, draft_markdown: str) -> CompileResult:
        """Verify all extracted claims in ``draft_markdown`` against current state and ledger."""
        current_tree_hash = capture_tree_hash(self.repo_root)
        claims = extract_claims(draft_markdown)

        diagnostics = [
            *verify_file_links(self.repo_root, claims.file_links),
            *verify_causal_freshness(self.ledger, current_tree_hash, claims.test_assertions),
            *verify_url_provenance(self.ledger, claims.urls),
        ]

        return CompileResult(
            passed=len(diagnostics) == 0,
            current_tree_hash=current_tree_hash,
            diagnostics=diagnostics,
            stats={
                "file_links": len(claims.file_links),
                "test_assertions": len(claims.test_assertions),
                "urls": len(claims.urls),
                "errors": len(diagnostics),
            },
        )
