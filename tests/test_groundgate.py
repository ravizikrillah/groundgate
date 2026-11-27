"""Comprehensive unit and integration tests for GroundGate."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from groundgate.cli import main as cli_main
from groundgate.compiler import GroundGate
from groundgate.git_snapshot import capture_tree_hash
from groundgate.ledger import SessionLedger


def _init_git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    return tmp_path


def test_isolated_git_write_tree_does_not_mutate_real_index(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    (repo / "app.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")

    # Confirm real git index has no staged files before or after capture_tree_hash
    tree1 = capture_tree_hash(repo)
    status = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""
    assert len(tree1) == 40

    # Editing file changes tree hash deterministically
    (repo / "app.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    tree2 = capture_tree_hash(repo)
    assert tree2 != tree1


def test_stale_test_claim_blocked_then_passes_after_rerun(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    app = repo / "auth.py"
    app.write_text("def validate_token(tok: str) -> bool:\n    return bool(tok)\n", encoding="utf-8")

    ledger = SessionLedger(repo)
    ledger.init()
    ledger.record_command("pytest -q", exit_code=0, stdout="4 passed in 0.05s\n")

    # Mutate file AFTER pytest ran
    app.write_text("def validate_token(tok: str) -> bool:\n    return len(tok) > 3\n", encoding="utf-8")

    draft = (
        f"Updated `validate_token` in [auth.py](file://{app}#L1-L2).\n"
        "All tests passed (4/4 passed)."
    )

    gate = GroundGate(repo)
    res_stale = gate.compile(draft)
    assert not res_stale.passed
    assert [d.code for d in res_stale.diagnostics] == ["STALE_TEST_CLAIM"]

    # Re-run pytest on current tree
    ledger.record_command("pytest -q", exit_code=0, stdout="4 passed in 0.04s\n")
    res_fresh = gate.compile(draft)
    assert res_fresh.passed, res_fresh.format_feedback()


def test_count_mismatch_and_failed_test_claim(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    ledger = SessionLedger(repo)
    ledger.init()

    # Case 1: failed test run
    ledger.record_command("pytest -q", exit_code=1, stdout="1 failed, 3 passed\n")
    gate = GroundGate(repo)
    res_fail = gate.compile("All tests passed.")
    assert not res_fail.passed
    assert res_fail.diagnostics[0].code == "FAILED_TEST_CLAIM"

    # Case 2: passing run, but inflated count in draft
    ledger.record_command("pytest -q", exit_code=0, stdout="4 passed in 0.03s\n")
    res_count = gate.compile("Verified: 12/12 passed.")
    assert not res_count.passed
    assert [d.code for d in res_count.diagnostics] == ["COUNT_MISMATCH", "COUNT_MISMATCH"]


def test_file_link_bounds_and_ast_symbol_in_span(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    svc = repo / "service.py"
    svc.write_text(
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def process_order(order_id: int) -> int:\n"
        "    return order_id * 2\n",
        encoding="utf-8",
    )

    gate = GroundGate(repo)

    # Wrong line span for process_order (actual is L4-L5, draft says L1-L2)
    bad_span_draft = f"Implemented `process_order` in [service.py](file://{svc}#L1-L2)."
    res_bad = gate.compile(bad_span_draft)
    assert not res_bad.passed
    assert res_bad.diagnostics[0].code == "SYMBOL_NOT_IN_SPAN"
    assert "L4-L5" in res_bad.diagnostics[0].message

    # Out of bounds line range
    oob_draft = f"See [service.py](file://{svc}#L1-L99)."
    res_oob = gate.compile(oob_draft)
    assert not res_oob.passed
    assert res_oob.diagnostics[0].code == "LINE_OUT_OF_BOUNDS"

    # Missing file
    missing_draft = "See [ghost.py](ghost.py#L1-L5)."
    res_missing = gate.compile(missing_draft)
    assert not res_missing.passed
    assert res_missing.diagnostics[0].code == "MISSING_FILE"

    # Correct span and symbol
    good_draft = f"Implemented `process_order` in [service.py](file://{svc}#L4-L5)."
    res_good = gate.compile(good_draft)
    assert res_good.passed, res_good.format_feedback()


def test_url_provenance_blocks_unobserved_urls(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    ledger = SessionLedger(repo)
    ledger.init()
    ledger.record_observation(
        source="search_web",
        text="Primary source: https://arxiv.org/abs/2603.10060",
    )

    gate = GroundGate(repo)
    res_bad = gate.compile(
        "See [NabaOS](https://arxiv.org/abs/2603.10060) and "
        "[Hallucinated](https://example.com/nonexistent-spec)."
    )
    assert not res_bad.passed
    assert len(res_bad.diagnostics) == 1
    assert res_bad.diagnostics[0].code == "UNOBSERVED_URL"
    assert "example.com" in res_bad.diagnostics[0].claim_text

    res_good = gate.compile("See [NabaOS](https://arxiv.org/abs/2603.10060).")
    assert res_good.passed


def test_fenced_code_blocks_are_ignored(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path)
    gate = GroundGate(repo)
    draft = (
        "Example usage:\n"
        "```markdown\n"
        "All tests passed in [fake.py](fake.py#L1-L10) via https://fake.example.com\n"
        "```\n"
    )
    res = gate.compile(draft)
    assert res.passed


def test_cli_end_to_end_flow(tmp_path: Path, capsys) -> None:
    repo = _init_git_repo(tmp_path)
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    assert cli_main(["init", "--repo", str(repo)]) == 0
    assert (
        cli_main(
            [
                "record-obs",
                "--repo",
                str(repo),
                "--source",
                "search_web",
                "--url",
                "https://docs.python.org/3/library/ast.html",
            ]
        )
        == 0
    )
    assert (
        cli_main(
            [
                "record-cmd",
                "--repo",
                str(repo),
                "--kind",
                "test",
                "--",
                "python3",
                "-c",
                "print('2 passed in 0.01s')",
            ]
        )
        == 0
    )

    draft_file = repo / ".groundgate" / "draft.md"
    draft_file.write_text(
        "Added `add` in [calc.py](calc.py#L1-L2) using "
        "[ast](https://docs.python.org/3/library/ast.html).\n"
        "2/2 tests passed.",
        encoding="utf-8",
    )
    capsys.readouterr()

    exit_code = cli_main(["verify", "--repo", str(repo), "--draft", str(draft_file), "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["stats"]["errors"] == 0
