#!/usr/bin/env python3
"""Redact PII and secrets from OpenClaw session JSONL transcripts.

OpenClaw persists exec/tool output into session transcripts without secret
redaction (openclaw/openclaw#12182), so tool-output messages get an extra
strict pass here in addition to the standard PII sweep.

Usage:
    python3 redact.py session.jsonl -o session.redacted.jsonl [--report]

Stdlib only. Each input line is a JSON message object; all string values are
scanned recursively and replaced with typed placeholders like [REDACTED:EMAIL].
"""

import argparse
import json
import re
import sys
from collections import Counter

# Order matters: more specific patterns first so e.g. a JWT inside a Bearer
# header is tagged once, not twice.
PATTERNS = [
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("HF_TOKEN", re.compile(r"\bhf_[A-Za-z0-9]{20,}\b")),
    ("NVIDIA_KEY", re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("BEARER", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("SECRET_ASSIGNMENT", re.compile(
        r"(?i)\b([A-Za-z0-9_]*(?:api[_-]?key|secret|token|passwd|password|auth)[A-Za-z0-9_]*)\s*[=:]\s*['\"]?[^\s'\"]{8,}")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<![\w/.-])\+?\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?![\w/.-])")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("IPV4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("HOME_PATH", re.compile(r"(?:/home|/Users)/[A-Za-z0-9._-]+")),
]

# Message types whose content originated from tool/exec execution (#12182).
TOOL_ROLES = {"tool", "tool_result", "function", "exec"}

# Long high-entropy tokens in tool output that the named patterns missed.
GENERIC_TOKEN = re.compile(r"\b(?=[A-Za-z0-9+/_-]*\d)(?=[A-Za-z0-9+/_-]*[A-Za-z])[A-Za-z0-9+/_-]{32,}\b")


def redact_text(text, counts, strict=False):
    for label, pattern in PATTERNS:
        if label == "SECRET_ASSIGNMENT":
            def keep_key(m, _label=label):
                counts[_label] += 1
                return f"{m.group(1)}=[REDACTED:{_label}]"
            text = pattern.sub(keep_key, text)
            continue

        def replace(m, _label=label):
            counts[_label] += 1
            return f"[REDACTED:{_label}]"
        text = pattern.sub(replace, text)

    if strict:
        def replace_generic(m):
            counts["GENERIC_TOKEN"] += 1
            return "[REDACTED:GENERIC_TOKEN]"
        text = GENERIC_TOKEN.sub(replace_generic, text)
    return text


def redact_value(value, counts, strict=False):
    if isinstance(value, str):
        return redact_text(value, counts, strict=strict)
    if isinstance(value, dict):
        return {k: redact_value(v, counts, strict=strict) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, counts, strict=strict) for v in value]
    return value


def is_tool_message(message):
    role = str(message.get("role", message.get("type", ""))).lower()
    return role in TOOL_ROLES or "tool_calls" in message or "tool_call_id" in message


def redact_message(message, counts):
    return redact_value(message, counts, strict=is_tool_message(message))


def redact_file(in_path, out_path):
    counts = Counter()
    n_lines = 0
    with open(in_path, encoding="utf-8") as src, open(out_path, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            message = json.loads(line)
            dst.write(json.dumps(redact_message(message, counts), ensure_ascii=False) + "\n")
            n_lines += 1
    return n_lines, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="session JSONL transcript")
    parser.add_argument("-o", "--output", required=True, help="redacted output path")
    parser.add_argument("--report", action="store_true", help="print redaction counts by category")
    args = parser.parse_args(argv)

    n_lines, counts = redact_file(args.input, args.output)
    total = sum(counts.values())
    print(f"{n_lines} messages processed, {total} redactions -> {args.output}")
    if args.report:
        for label, count in counts.most_common():
            print(f"  {label:18} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
