"""Session-observed URL provenance verifier."""

from __future__ import annotations

from groundgate.ledger import SessionLedger
from groundgate.models import Diagnostic, UrlClaim


def verify_url_provenance(ledger: SessionLedger, claims: list[UrlClaim]) -> list[Diagnostic]:
    """Ensure every external URL in the draft appeared verbatim in session tool outputs."""
    observed = ledger.observed_urls()
    normalized_observed = {u.rstrip("/") for u in observed}

    diagnostics: list[Diagnostic] = []
    for claim in claims:
        if claim.url in observed or claim.url.rstrip("/") in normalized_observed:
            continue
        diagnostics.append(
            Diagnostic(
                code="UNOBSERVED_URL",
                line=claim.line,
                claim_text=claim.url,
                message=f"URL '{claim.url}' was never observed in any session tool output.",
                fix_hint="Remove the unverified URL or fetch/search it in the current session first.",
            )
        )
    return diagnostics
