# openclaw-trace-toolkit

Tooling for preparing OpenClaw agent session traces for evaluation and
submission: PII/secret redaction, transcript validation, and rubric-based
scoring. **Stdlib only — no dependencies**, so it runs identically anywhere
Python 3.10+ runs.

Built around failure modes that actually bite OpenClaw trace pipelines:

| Risk | Upstream issue | Mitigation here |
| --- | --- | --- |
| Exec/tool output persisted into transcripts **without secret redaction** | [openclaw#12182](https://github.com/openclaw/openclaw/issues/12182) | `redact.py` runs an extra high-entropy-token pass on tool/exec messages |
| Exporter silently skips `.jsonl.reset.*` / `.jsonl.deleted.*` transcripts | [openclaw#30220](https://github.com/openclaw/openclaw/issues/30220) | `trace_lint.py` warns when sibling transcripts exist next to the export |
| Transcripts written with loose (644) file permissions | [openclaw#7862](https://github.com/openclaw/openclaw/issues/7862) | treat redaction as mandatory before any transcript leaves the machine |

## Quickstart

```bash
# 1. Redact PII and secrets from an exported session
python3 redact.py sample_trace.jsonl -o sample_trace.redacted.jsonl --report

# 2. Validate the transcript before packaging (use --min-turns 150 for long-horizon submissions)
python3 trace_lint.py sample_trace.redacted.jsonl

# 3. Score it against a weighted rubric
python3 rubric.py rubric.json --template > scores.json   # fill in 0-5 per dimension
python3 rubric.py rubric.json --scores scores.json

# Run the test suite
python3 -m unittest discover -s tests -v
```

## What gets redacted

Emails, phone numbers, AWS/GitHub/OpenAI/Slack credentials, JWTs, bearer
tokens, `KEY=value` secret assignments (key name preserved for debuggability),
credit-card-shaped numbers, IPv4 addresses, and home-directory paths. Tool and
exec output additionally gets a generic high-entropy-token sweep, since that is
where unredacted secrets leak into transcripts in practice. Replacements are
typed placeholders (`[REDACTED:EMAIL]`) so a redacted trace stays evaluable —
you can still judge whether the agent *used* a credential correctly without
seeing it.

## What gets linted

Per-line JSON validity, role presence, empty content, consecutive same-role
turns, dangling tool calls (a `tool_calls` id with no later result message),
backwards timestamps, minimum conversation turn count, and export completeness
against sibling reset/deleted transcripts.

## Rubric design

`rubric.json` defines six weighted dimensions (task completion, instruction
adherence, tool use, reasoning quality, factual grounding, safety/privacy) on a
0–5 scale, weights summing to 1.0. Scores live in separate per-rater sheets so
inter-rater agreement can be measured across reviewers rather than baked into
the trace.

## Demo data

`sample_trace.jsonl` is a small **synthetic** transcript with planted fake
credentials/PII to demonstrate the redaction pass — it is demo fixture data,
not a real session.
