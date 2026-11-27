# GroundGate

**Deterministic Pre-Emission Markdown Claim & Causal-Freshness Compiler for AI Agents.**

AI coding and research agents frequently hallucinate in their **final Markdown response** after long sessions—claiming *"all tests passed"* even though a file was edited afterward, citing drifted line numbers or symbol names, rounding test counts, or inventing plausible documentation URLs that were never observed.

`GroundGate` sits between an AI agent's candidate Markdown draft and the user. Without calling another LLM (*zero LLM-as-a-judge*), it deterministically compiles and verifies every factual claim against actual disk state, isolated `git write-tree` snapshots, and the active session ledger.

## How It Works

```text
[AI Agent Candidate Markdown Draft]
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GroundGate Pre-Emission Compiler             │
│                                                                 │
│  1. Markdown Claim Extractor (ignores fenced code blocks)       │
│     ├─ File/Line Links: [label](file:///path#L10-L25)           │
│     ├─ Clause Symbols:  `validate_token`, `process_order`       │
│     ├─ Test/Build Claims: "all tests passed", "4/4 passed"      │
│     └─ External URLs: https://...                               │
│                                                                 │
│  2. Deterministic Verifiers (Zero LLM-as-a-Judge)               │
│     ├─ [FS + Python AST] Verify file exists, line bounds valid, │
│     │    and backticked symbols exist within #Lstart-Lend       │
│     ├─ [Causal Tree-Hash] Compare `git write-tree` at test run  │
│     │    vs `git write-tree` at emission (isolated index)       │
│     └─ [Session Ledger] Match URLs & test counts verbatim       │
│          against recorded session tool outputs                  │
└────────┬───────────────────────────────────────────┬────────────┘
         │ PASS (exit 0)                             │ FAIL (exit 2)
         ▼                                           ▼
  [Emit to User]                        [Block Draft -> 1-Turn Self-Fix]
```

### Verification Gates & Diagnostic Codes

1. **Causal-Freshness Binding (`git write-tree`)**:
   - Captures workspace snapshots using an isolated temporary `GIT_INDEX_FILE` so your real Git staging area is never touched (falls back to a deterministic SHA-256 directory walk outside Git repos).
   - Flags `STALE_TEST_CLAIM` / `STALE_BUILD_CLAIM` if files changed after the last run, `FAILED_TEST_CLAIM` / `FAILED_BUILD_CLAIM` on non-zero exit codes, `MISSING_TEST_EVIDENCE`, and `COUNT_MISMATCH` when claimed pass/total numbers differ from raw stdout.
2. **Markdown Link & AST Symbol-in-Span**:
   - Verifies `[label](file:///path#Lstart-Lend)` and relative file links exist (`MISSING_FILE`), line ranges are within bounds (`LINE_OUT_OF_BOUNDS`), and backticked symbols in the same sentence actually appear within that span (`SYMBOL_NOT_IN_SPAN`, with exact Python `ast` line-span hints).
3. **Session-Observed URL Provenance**:
   - Ensures every external `http(s)://` URL in the draft appeared verbatim in recorded session tool outputs (`UNOBSERVED_URL`).

## Installation

Requires Python 3.11+ and `uv`.

### Local Clone (Development & Tests)

```bash
cd groundgate
uv venv
uv pip install -e ".[dev]"
uv run pytest -v
```

## Quickstart

### 1. Initialize Session Ledger

```bash
uv run groundgate init --repo .
```

### 2. Record Test/Build Runs & Web Observations

Run tests or builds through `record-cmd` to bind the `git write-tree` hash, exit code, and parsed counts:

```bash
uv run groundgate record-cmd --repo . -- pytest -q
```

Record URLs observed from web search or fetch tools:

```bash
uv run groundgate record-obs --repo . --source search_web --url https://arxiv.org/abs/2603.10060
```

### 3. Verify a Candidate Markdown Draft Pre-Emission

```bash
uv run groundgate verify --repo . --draft - --json <<'EOF'
Updated `validate_token` in [auth.py](auth.py#L1-L2).
All tests passed (4/4 passed).
EOF
```

- Returns exit code `0` on `PASS`.
- Returns exit code `2` on `FAIL` with structured diagnostics and `fix_hint` for 1-turn agent self-correction.

### 4. Python API

```python
from pathlib import Path
from groundgate import GroundGate

gate = GroundGate(Path("."))
result = gate.compile(draft_markdown)
if not result.passed:
    print(result.format_feedback())
```

## Installing the Agent Skill

This repository includes an agent skill at [`skills/groundgate/SKILL.md`](skills/groundgate/SKILL.md) that teaches AI agents how to record test runs and URL observations and run `groundgate verify` before emitting a final response.

Install the skill from a local clone:

```bash
chmod +x install-skill.sh
./install-skill.sh
```

The installer copies `SKILL.md` into `~/.agents/skills/groundgate/` and, if present, `~/.gemini/antigravity-cli/skills/groundgate/` and `~/.claude/skills/groundgate/`.

## Project Layout

- `src/groundgate/compiler.py`: Main `GroundGate` pre-emission compiler orchestrating all verifiers.
- `src/groundgate/extractor.py`: Deterministic Markdown claim, link, symbol, test-assertion, and URL extractor.
- `src/groundgate/git_snapshot.py`: Isolated `git write-tree` snapshotter (`GIT_INDEX_FILE`) with SHA-256 fallback.
- `src/groundgate/ledger.py`: Append-only JSONL session trace ledger (`.groundgate/session.jsonl`) and test-output count parsers.
- `src/groundgate/verifiers/fs_ast.py`: File existence, line-span bounds, and Python AST symbol-in-span verifier.
- `src/groundgate/verifiers/causal.py`: Causal-freshness and test-count verifier.
- `src/groundgate/verifiers/provenance.py`: Session-observed URL provenance verifier.
- `src/groundgate/cli.py`: CLI entrypoint (`init`, `record-cmd`, `record-obs`, `verify`).
- `skills/groundgate/SKILL.md`: Agent skill definition.
- `install-skill.sh`: Local skill installer script.
- `tests/test_groundgate.py`: Unit and end-to-end CLI tests covering all 4 hallucination classes.

## License

MIT
