"""Filesystem, line-span, and AST symbol-in-span verifier."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from groundgate.models import Diagnostic, FileLinkClaim


def _resolve_path(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _python_symbol_spans(source: str) -> dict[str, list[tuple[int, int]]]:
    """Return mapping of Python symbol name -> list of (start_line, end_line) spans."""
    spans: dict[str, list[tuple[int, int]]] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return spans

    for node in ast.walk(tree):
        name: str | None = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    spans.setdefault(target.id, []).append(
                        (node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno)
                    )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id

        if name is not None:
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            spans.setdefault(name, []).append((node.lineno, end))

    return spans


def _spans_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def verify_file_links(repo_root: Path, claims: list[FileLinkClaim]) -> list[Diagnostic]:
    """Verify file existence, line-range bounds, and backticked symbols within span."""
    diagnostics: list[Diagnostic] = []

    for claim in claims:
        target_path = _resolve_path(repo_root, claim.path)
        if not target_path.is_file():
            diagnostics.append(
                Diagnostic(
                    code="MISSING_FILE",
                    line=claim.line,
                    claim_text=claim.raw_target,
                    message=f"Referenced file does not exist: '{claim.path}'.",
                    fix_hint="Verify the exact file path on disk or remove the broken link.",
                )
            )
            continue

        content = target_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        total_lines = len(lines)

        start = claim.start_line
        end = claim.end_line
        if start is not None and end is not None:
            if start < 1 or end < start or end > total_lines:
                diagnostics.append(
                    Diagnostic(
                        code="LINE_OUT_OF_BOUNDS",
                        line=claim.line,
                        claim_text=claim.raw_target,
                        message=(
                            f"Line span #L{start}-L{end} is out of bounds for "
                            f"'{claim.path}' (total lines: {total_lines})."
                        ),
                        fix_hint=f"Adjust line range to within 1..{total_lines}.",
                    )
                )
                continue
            span_text = "\n".join(lines[start - 1 : end])
        else:
            span_text = content

        if not claim.clause_symbols:
            continue

        py_spans = _python_symbol_spans(content) if target_path.suffix == ".py" else {}
        for symbol in claim.clause_symbols:
            sym_re = re.compile(rf"\b{re.escape(symbol)}\b")
            in_span_text = bool(sym_re.search(span_text))

            if start is not None and end is not None and symbol in py_spans:
                in_ast_span = any(
                    _spans_overlap(s, e, start, end) for s, e in py_spans[symbol]
                )
                if not in_ast_span and not in_span_text:
                    actual = py_spans[symbol][0]
                    diagnostics.append(
                        Diagnostic(
                            code="SYMBOL_NOT_IN_SPAN",
                            line=claim.line,
                            claim_text=f"`{symbol}` in {claim.raw_target}",
                            message=(
                                f"Symbol `{symbol}` is not in {claim.path}#L{start}-L{end} "
                                f"(actual definition at L{actual[0]}-L{actual[1]})."
                            ),
                            fix_hint=f"Update link span to #L{actual[0]}-L{actual[1]}.",
                        )
                    )
            elif not in_span_text:
                diagnostics.append(
                    Diagnostic(
                        code="SYMBOL_NOT_IN_SPAN",
                        line=claim.line,
                        claim_text=f"`{symbol}` in {claim.raw_target}",
                        message=(
                            f"Symbol `{symbol}` was not found in '{claim.path}'"
                            + (f" within #L{start}-L{end}." if start is not None else ".")
                        ),
                        fix_hint="Verify the exact symbol spelling and line range on disk.",
                    )
                )

    return diagnostics
