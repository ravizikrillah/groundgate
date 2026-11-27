"""Causal-freshness verifier binding test/build claims to git write-tree hashes."""

from __future__ import annotations

from groundgate.ledger import SessionLedger
from groundgate.models import Diagnostic, TestAssertionClaim


def verify_causal_freshness(
    ledger: SessionLedger,
    current_tree_hash: str,
    claims: list[TestAssertionClaim],
) -> list[Diagnostic]:
    """Ensure every test/build pass claim matches a passing run on current_tree_hash."""
    diagnostics: list[Diagnostic] = []

    for claim in claims:
        runs = ledger.latest_commands(command_kind=claim.kind)
        if not runs:
            code = "MISSING_TEST_EVIDENCE" if claim.kind == "test" else "MISSING_BUILD_EVIDENCE"
            diagnostics.append(
                Diagnostic(
                    code=code,
                    line=claim.line,
                    claim_text=claim.clause,
                    message=f"No {claim.kind} execution recorded in session ledger.",
                    fix_hint=f"Run the {claim.kind} command via groundgate or remove the unverified claim.",
                )
            )
            continue

        latest = runs[0]
        if latest.exit_code != 0:
            diagnostics.append(
                Diagnostic(
                    code="FAILED_TEST_CLAIM" if claim.kind == "test" else "FAILED_BUILD_CLAIM",
                    line=claim.line,
                    claim_text=claim.clause,
                    message=(
                        f"Latest {claim.kind} command '{latest.command}' exited with code "
                        f"{latest.exit_code}, contradicting pass claim."
                    ),
                    fix_hint="Fix the failing command and re-run it, or report the failure accurately.",
                )
            )
            continue

        if latest.tree_hash != current_tree_hash:
            diagnostics.append(
                Diagnostic(
                    code="STALE_TEST_CLAIM" if claim.kind == "test" else "STALE_BUILD_CLAIM",
                    line=claim.line,
                    claim_text=claim.clause,
                    message=(
                        f"'{latest.command}' ran at tree {latest.tree_hash[:12]}, but workspace "
                        f"was later mutated to {current_tree_hash[:12]}."
                    ),
                    fix_hint=f"Re-run '{latest.command}' on the current tree or qualify the claim.",
                )
            )
            continue

        if claim.claimed_passed is not None and "passed" in latest.parsed_counts:
            actual_passed = latest.parsed_counts["passed"]
            if claim.claimed_passed != actual_passed:
                diagnostics.append(
                    Diagnostic(
                        code="COUNT_MISMATCH",
                        line=claim.line,
                        claim_text=claim.clause,
                        message=(
                            f"Draft claims {claim.claimed_passed} passed, but '{latest.command}' "
                            f"stdout reported {actual_passed} passed."
                        ),
                        fix_hint=f"Update the reported pass count to {actual_passed}.",
                    )
                )

        if claim.claimed_total is not None and "total" in latest.parsed_counts:
            actual_total = latest.parsed_counts["total"]
            if claim.claimed_total != actual_total:
                diagnostics.append(
                    Diagnostic(
                        code="COUNT_MISMATCH",
                        line=claim.line,
                        claim_text=claim.clause,
                        message=(
                            f"Draft claims {claim.claimed_total} total tests, but '{latest.command}' "
                            f"stdout reported {actual_total} total."
                        ),
                        fix_hint=f"Update the reported total count to {actual_total}.",
                    )
                )

    return diagnostics
