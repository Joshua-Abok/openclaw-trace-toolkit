#!/usr/bin/env python3
"""Validate OpenClaw session JSONL transcripts before packaging/submission.

Checks:
  - every line parses as a JSON object with a role and non-empty content
  - role sequence sanity (no consecutive duplicate user/assistant turns)
  - no dangling tool calls (assistant tool_calls with no following tool result)
  - timestamps are monotonically non-decreasing when present
  - minimum turn count (e.g. --min-turns 150 for long-horizon submissions)
  - export completeness: warns if sibling .jsonl.reset.* / .jsonl.deleted.*
    transcripts exist next to the source, which the exporter can silently
    skip (openclaw/openclaw#30220)

Usage:
    python3 trace_lint.py session.jsonl [--min-turns 150]

Exit code 0 = clean, 1 = findings. Stdlib only.
"""

import argparse
import glob
import json
import os
import sys

CONVERSATION_ROLES = {"user", "assistant"}


def lint_lines(lines, min_turns=0):
    errors = []
    warnings = []
    turns = 0
    prev_role = None
    prev_ts = None
    open_tool_calls = set()

    for i, raw in enumerate(lines, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {i}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(msg, dict):
            errors.append(f"line {i}: expected JSON object, got {type(msg).__name__}")
            continue

        role = str(msg.get("role", msg.get("type", ""))).lower()
        if not role:
            errors.append(f"line {i}: missing role/type field")

        content = msg.get("content", msg.get("text"))
        has_tool_calls = bool(msg.get("tool_calls"))
        if content in (None, "", []) and not has_tool_calls:
            warnings.append(f"line {i}: empty content")

        if role in CONVERSATION_ROLES:
            turns += 1
            if role == prev_role:
                warnings.append(f"line {i}: consecutive '{role}' turns")
        # tool/system messages legitimately sit between two assistant turns,
        # so any role breaks the alternation check
        if role:
            prev_role = role

        for call in msg.get("tool_calls") or []:
            call_id = call.get("id") if isinstance(call, dict) else None
            if call_id:
                open_tool_calls.add(call_id)
        if msg.get("tool_call_id"):
            open_tool_calls.discard(msg["tool_call_id"])

        ts = msg.get("timestamp", msg.get("ts"))
        if ts is not None and prev_ts is not None and ts < prev_ts:
            errors.append(f"line {i}: timestamp goes backwards ({ts} < {prev_ts})")
        if ts is not None:
            prev_ts = ts

    for call_id in sorted(open_tool_calls):
        errors.append(f"dangling tool call with no result: {call_id}")

    if min_turns and turns < min_turns:
        errors.append(f"only {turns} user/assistant turns, minimum required is {min_turns}")

    return turns, errors, warnings


def check_export_completeness(path):
    """Flag sibling reset/deleted transcripts the exporter may have skipped (#30220)."""
    siblings = glob.glob(path + ".reset.*") + glob.glob(path + ".deleted.*")
    return [f"sibling transcript not covered by export: {os.path.basename(s)}" for s in siblings]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="session JSONL transcript")
    parser.add_argument("--min-turns", type=int, default=0,
                        help="fail if fewer user/assistant turns than this")
    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as f:
        turns, errors, warnings = lint_lines(f, min_turns=args.min_turns)
    warnings.extend(check_export_completeness(args.input))

    print(f"{args.input}: {turns} conversation turns, {len(errors)} errors, {len(warnings)} warnings")
    for e in errors:
        print(f"  ERROR   {e}")
    for w in warnings:
        print(f"  WARNING {w}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
