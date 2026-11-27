"""Command-line interface for GroundGate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from groundgate.compiler import GroundGate
from groundgate.ledger import SessionLedger


def _cmd_init(args: argparse.Namespace) -> int:
    ledger = SessionLedger(Path(args.repo))
    path = ledger.init(reset=args.reset)
    print(f"Initialized GroundGate ledger at {path}")
    return 0


def _cmd_record_cmd(args: argparse.Namespace) -> int:
    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("Error: no command specified after --", file=sys.stderr)
        return 1

    repo = Path(args.repo).resolve()
    proc = subprocess.run(cmd, cwd=repo, text=True, capture_output=True)
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    ledger = SessionLedger(repo)
    entry = ledger.record_command(
        command=cmd,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        command_kind=args.kind,
    )
    print(
        f"[groundgate] recorded {entry.command_kind} exit={entry.exit_code} "
        f"tree={entry.tree_hash[:12]} counts={entry.parsed_counts}",
        file=sys.stderr,
    )
    return proc.returncode


def _cmd_record_obs(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    text = args.text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    ledger = SessionLedger(repo)
    entry = ledger.record_observation(source=args.source, text=text, urls=args.url)
    print(f"[groundgate] recorded {len(entry.observed_urls)} URL(s) from {args.source}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if args.draft == "-":
        draft = sys.stdin.read()
    else:
        draft = Path(args.draft).read_text(encoding="utf-8")

    gate = GroundGate(repo)
    result = gate.compile(draft)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.format_feedback())

    return 0 if result.passed else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundgate",
        description="Deterministic Pre-Emission Markdown Claim & Causal-Freshness Compiler",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_init = sub.add_parser("init", help="Initialize .groundgate/session.jsonl")
    p_init.add_argument("--repo", default=".", help="Repository root path")
    p_init.add_argument("--reset", action="store_true", help="Clear existing session ledger")
    p_init.set_defaults(func=_cmd_init)

    p_cmd = sub.add_parser("record-cmd", help="Run a command and record its tree hash & output")
    p_cmd.add_argument("--repo", default=".", help="Repository root path")
    p_cmd.add_argument("--kind", choices=["test", "build", "command"], default=None)
    p_cmd.add_argument("cmd", nargs=argparse.REMAINDER, help="Command after --")
    p_cmd.set_defaults(func=_cmd_record_cmd)

    p_obs = sub.add_parser("record-obs", help="Record observed tool text/URLs into session ledger")
    p_obs.add_argument("--repo", default=".", help="Repository root path")
    p_obs.add_argument("--source", default="search_web", help="Tool source name")
    p_obs.add_argument("--text", default="", help="Raw tool output text")
    p_obs.add_argument("--file", default=None, help="File containing raw tool output")
    p_obs.add_argument("--url", action="append", default=[], help="Explicit observed URL")
    p_obs.set_defaults(func=_cmd_record_obs)

    p_verify = sub.add_parser("verify", help="Verify a Markdown draft pre-emission")
    p_verify.add_argument("--repo", default=".", help="Repository root path")
    p_verify.add_argument("--draft", default="-", help="Path to Markdown draft or '-' for stdin")
    p_verify.add_argument("--json", action="store_true", help="Output structured JSON diagnostics")
    p_verify.set_defaults(func=_cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
