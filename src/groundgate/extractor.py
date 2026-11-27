"""Deterministic Markdown claim extractor (links, symbols, test assertions, URLs)."""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from groundgate.models import (
    ExtractedClaims,
    FileLinkClaim,
    TestAssertionClaim,
    UrlClaim,
)

# Matches Markdown links: [label](target)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
# Matches bare http(s) URLs not already inside (...)
_BARE_URL_RE = re.compile(r"(?<!\()https?://[^\s<>()\[\]\"'`]+")
# Matches line span suffixes: #L10 or #L10-L25
_LINE_SPAN_RE = re.compile(r"^#L(\d+)(?:-L(\d+))?$")
# Matches backticked inline code tokens
_INLINE_CODE_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{1,80})`")

# Positive test/build assertion patterns
_FRACTION_PASS_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\s+(?:tests?\s+)?(?:passed|pass|lulus)\b", re.IGNORECASE)
_COUNT_PASS_RE = re.compile(r"\b(\d+)\s+(?:tests?\s+)?(?:passed|lulus)\b", re.IGNORECASE)
_TEST_PASS_RE = re.compile(
    r"\b(?:all\s+tests?\s+(?:are\s+)?(?:pass(?:ed|ing)?|green)|"
    r"tests?\s+(?:have\s+)?passed|"
    r"(?:seluruh|semua)\s+tes\s+(?:telah\s+)?(?:dijalankan\s+dan\s+)?lulus|"
    r"0\s+failed)\b",
    re.IGNORECASE,
)
_BUILD_PASS_RE = re.compile(
    r"\b(?:build\s+(?:succeeded|passed|green)|"
    r"kompilasi\s+(?:berhasil|sukses))\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"\b(?:not\s+run|haven't\s+run|did\s+not\s+run|belum\s+dijalankan|"
    r"tidak\s+lulus|failed|gagal)\b",
    re.IGNORECASE,
)


def _strip_fenced_code_blocks(markdown: str) -> list[tuple[int, str]]:
    """Return (1-based line_num, line_text) pairs outside fenced ``` code blocks."""
    result: list[tuple[int, str]] = []
    in_fence = False
    for idx, line in enumerate(markdown.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence:
            result.append((idx, line))
    return result


def _parse_file_target(raw_target: str) -> tuple[str, int | None, int | None] | None:
    """Parse a file:// URI or local relative path with optional #Lstart-Lend."""
    if raw_target.startswith(("http://", "https://", "mailto:", "#")):
        return None

    parsed = urlparse(raw_target)
    if parsed.scheme and parsed.scheme != "file":
        return None

    path_str = unquote(parsed.path) if parsed.scheme == "file" else raw_target.split("#", 1)[0]
    if not path_str:
        return None

    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    if not fragment and "#" in raw_target:
        fragment = "#" + raw_target.split("#", 1)[1]

    start_line: int | None = None
    end_line: int | None = None
    if fragment:
        span_match = _LINE_SPAN_RE.match(fragment)
        if span_match:
            start_line = int(span_match.group(1))
            end_line = int(span_match.group(2)) if span_match.group(2) else start_line

    return path_str, start_line, end_line


def _extract_clause_symbols(line: str, label: str) -> tuple[str, ...]:
    """Extract backticked code identifiers on the same line that look like symbols."""
    symbols: list[str] = []
    for sym in _INLINE_CODE_RE.findall(line):
        # Skip if it's identical to the file link label or an obvious common keyword
        if sym == label or sym.lower() in {"true", "false", "none", "null", "self", "cls"}:
            continue
        if sym not in symbols:
            symbols.append(sym)
    return tuple(symbols)


def extract_claims(markdown: str) -> ExtractedClaims:
    """Extract all verifiable file, symbol, test/build, and URL claims from Markdown."""
    file_links: list[FileLinkClaim] = []
    test_assertions: list[TestAssertionClaim] = []
    urls: list[UrlClaim] = []
    seen_urls_on_line: set[tuple[int, str]] = set()

    for line_num, line in _strip_fenced_code_blocks(markdown):
        # 1. Markdown links
        for match in _MD_LINK_RE.finditer(line):
            label, target = match.group(1), match.group(2)
            if target.startswith(("http://", "https://")):
                cleaned = target.rstrip(".,;:!?")
                if (line_num, cleaned) not in seen_urls_on_line:
                    seen_urls_on_line.add((line_num, cleaned))
                    urls.append(UrlClaim(line=line_num, url=cleaned))
                continue

            parsed_file = _parse_file_target(target)
            if parsed_file is not None:
                path_str, start_line, end_line = parsed_file
                symbols = _extract_clause_symbols(line, label)
                file_links.append(
                    FileLinkClaim(
                        line=line_num,
                        label=label,
                        raw_target=target,
                        path=path_str,
                        start_line=start_line,
                        end_line=end_line,
                        clause_symbols=symbols,
                    )
                )

        # 2. Bare URLs
        for match in _BARE_URL_RE.finditer(line):
            cleaned = match.group(0).rstrip(".,;:!?")
            if (line_num, cleaned) not in seen_urls_on_line:
                seen_urls_on_line.add((line_num, cleaned))
                urls.append(UrlClaim(line=line_num, url=cleaned))

        # 3. Test / build assertions (skip negated statements)
        if _NEGATION_RE.search(line):
            continue

        frac_match = _FRACTION_PASS_RE.search(line)
        count_match = _COUNT_PASS_RE.search(line)
        if frac_match:
            passed = int(frac_match.group(1))
            total = int(frac_match.group(2))
            test_assertions.append(
                TestAssertionClaim(
                    line=line_num,
                    clause=line.strip(),
                    claimed_passed=passed,
                    claimed_total=total,
                    kind="test",
                )
            )
        elif count_match or _TEST_PASS_RE.search(line):
            passed = int(count_match.group(1)) if count_match else None
            test_assertions.append(
                TestAssertionClaim(
                    line=line_num,
                    clause=line.strip(),
                    claimed_passed=passed,
                    kind="test",
                )
            )
        elif _BUILD_PASS_RE.search(line):
            test_assertions.append(
                TestAssertionClaim(
                    line=line_num,
                    clause=line.strip(),
                    kind="build",
                )
            )

    return ExtractedClaims(
        file_links=file_links,
        test_assertions=test_assertions,
        urls=urls,
    )
