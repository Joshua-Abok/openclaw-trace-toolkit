#!/usr/bin/env python3
"""Validate OpenClaw session JSONL transcripts before packaging/submission.

Handles BOTH transcript shapes:
  - flat:   {"role": "...", "content": "...", "tool_calls": [...]}  (legacy / demo)
  - nested: {"type": "message", "message": {"role": "...", "content": ...}, ...}
            the real OpenClaw event-log format, where conversation messages are
            nested under "message" and non-conversational events (session,
            model_change, thinking_level_change, custom) sit on their own lines.

Checks:
  - every conversation line has a role and non-empty content (or tool calls)
  - role sequence sanity (no consecutive duplicate user/assistant turns)
  - no dangling tool calls (a tool call with no matching tool result)
  - timestamps are monotonically non-decreasing when present
  - minimum turn count (e.g. --min-turns 150 for long-horizon submissions)
  - export completeness: warns if sibling .jsonl.reset.* / .jsonl.deleted.*
    transcripts exist next to the source, which the exporter can silently
    skip (openclaw/openclaw#30220)

A "turn" = one user or assistant message. Tool results, model-change/session
events and other meta lines are not counted as turns.

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
# OpenClaw event types that are not conversation messages
META_EVENT_TYPES = {"session", "model_change", "thinking_level_change", "custom"}


def _content_text(content):
    """Return the plain text carried by a content field (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _tool_call_ids(content, top_level_tool_calls):
    """Collect tool-call ids opened by a message, from either shape."""
    ids = []
    # flat shape: top-level "tool_calls": [{"id": ...}, ...]
    for call in top_level_tool_calls or []:
        if isinstance(call, dict) and call.get("id"):
            ids.append(call["id"])
    # nested shape: assistant content blocks of {"type": "toolCall", "id": ...}
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("toolCall", "tool_call") and block.get("id"):
                ids.append(block["id"])
    return ids


def normalize(obj):
    """Map a raw line (either shape) to a common record, or None if it's a
    non-conversational meta event that should be skipped entirely.

    Returns dict: role, content, opened_calls (list of ids), closed_call (id or
    None), timestamp.
    """
    if not isinstance(obj, dict):
        return None

    etype = obj.get("type")

    # --- nested OpenClaw event-log shape ---
    if etype is not None or "message" in obj:
        if etype in META_EVENT_TYPES:
            return None
        if etype == "message" or isinstance(obj.get("message"), dict):
            m = obj.get("message")
            if not isinstance(m, dict):
                return {"role": "", "content": None, "opened_calls": [],
                        "closed_call": None, "timestamp": obj.get("timestamp")}
            role = str(m.get("role", "")).lower()
            if role == "toolresult":          # OpenClaw's tool-result role
                role = "tool"
            content = m.get("content")
            opened = _tool_call_ids(content, m.get("tool_calls"))
            closed = m.get("toolCallId") or m.get("tool_call_id")
            ts = obj.get("timestamp") or m.get("timestamp")
            return {"role": role, "content": content, "opened_calls": opened,
                    "closed_call": closed, "timestamp": ts}
        # an unknown typed event we don't recognise -> skip rather than warn
        return None

    # --- flat / legacy shape ---
    role = str(obj.get("role", "")).lower()
    content = obj.get("content", obj.get("text"))
    opened = _tool_call_ids(content, obj.get("tool_calls"))
    closed = obj.get("tool_call_id") or obj.get("toolCallId")
    ts = obj.get("timestamp", obj.get("ts"))
    return {"role": role, "content": content, "opened_calls": opened,
            "closed_call": closed, "timestamp": ts}


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
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {i}: invalid JSON ({exc.msg})")
            continue

        rec = normalize(obj)
        if rec is None:        # non-conversational meta event — skip
            continue

        role = rec["role"]
        if not role:
            errors.append(f"line {i}: missing role/type field")

        has_tool_calls = bool(rec["opened_calls"])
        if not _content_text(rec["content"]).strip() and not has_tool_calls and not rec["closed_call"]:
            warnings.append(f"line {i}: empty content")

        if role in CONVERSATION_ROLES:
            turns += 1
            if role == prev_role:
                warnings.append(f"line {i}: consecutive '{role}' turns")
        # tool/system messages legitimately sit between two assistant turns,
        # so any role breaks the alternation check
        if role:
            prev_role = role

        for call_id in rec["opened_calls"]:
            open_tool_calls.add(call_id)
        if rec["closed_call"]:
            open_tool_calls.discard(rec["closed_call"])

        ts = rec["timestamp"]
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
