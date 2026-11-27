---
name: groundgate
description: Use GroundGate to deterministically verify an AI agent's candidate Markdown response before emitting it to the user—catching stale test claims via git write-tree, broken file/line/AST symbol links, inflated test counts, and unobserved URLs.
---

# GroundGate Agent Workflow

Use this skill whenever you are working in a repository with GroundGate enabled, or before emitting a final Markdown summary that cites file paths, line spans, code symbols, test/build results, or external URLs.

## Running the CLI

Run `groundgate` inside your project environment (or via `uv run groundgate` / `uvx`):

```bash
groundgate <command>
```

## Core Rules

1. **Initialize a Session Ledger at Task Start**
   - At the start of a coding or research session in a repository, ensure `.groundgate/session.jsonl` exists:
     ```bash
     groundgate init --repo .
     ```
   - Use `--reset` only when starting a brand-new independent session.

2. **Record Test/Build Commands and Web Observations**
   - Run test and build commands through `groundgate record-cmd` so GroundGate binds the exact `git write-tree` hash, `exit_code`, and raw pass/fail counts:
     ```bash
     groundgate record-cmd --repo . -- pytest -q
     ```
   - Whenever you retrieve external URLs from `search_web`, `read_url`, or `curl`, record them into the session ledger:
     ```bash
     groundgate record-obs --repo . --source search_web --url https://example.com/docs
     ```

3. **Verify Your Final Markdown Draft Pre-Emission**
   - Before sending a final Markdown response to the user, pass the draft through `groundgate verify`:
     ```bash
     groundgate verify --repo . --draft - --json <<'EOF'
     Updated `validate_token` in [auth.py](file:///path/to/auth.py#L10-L20).
     All tests passed (4/4 passed).
     EOF
     ```
   - Exit code `0` means all claims are grounded. Exit code `2` means one or more claims failed verification.

4. **Perform a 1-Turn Self-Fix on Any Diagnostic**
   - **`STALE_TEST_CLAIM` / `STALE_BUILD_CLAIM`**: You edited files after running tests/build. Either re-run the command via `groundgate record-cmd` on the current tree or qualify your response honestly (do not claim tests passed on the latest edit).
   - **`FAILED_TEST_CLAIM` / `MISSING_TEST_EVIDENCE`**: Never claim tests passed when the latest run failed or no run was recorded.
   - **`COUNT_MISMATCH`**: Update your reported pass/total numbers to match the exact counts printed in raw stdout.
   - **`MISSING_FILE` / `LINE_OUT_OF_BOUNDS` / `SYMBOL_NOT_IN_SPAN`**: Re-read the file on disk and update the path, `#Lstart-Lend` span, or backticked symbol name using the `fix_hint`.
   - **`UNOBSERVED_URL`**: Remove the unverified URL or fetch/search it in the current session via `record-obs` first.

## Quick Command Reference

- Initialize ledger: `groundgate init --repo .`
- Record test/build command: `groundgate record-cmd --repo . -- <command>`
- Record observed URL/text: `groundgate record-obs --repo . --source <tool> --url <url>`
- Verify draft (text): `groundgate verify --repo . --draft <file_or_->`
- Verify draft (JSON): `groundgate verify --repo . --draft <file_or_-> --json`
